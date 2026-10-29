#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT/var/run"
LOG_DIR="$ROOT/var/log"
ACTION_SERVICE="${1:-}"
ACTION="${2:-}"

usage() {
  echo "Usage: bash scripts/service.sh {backend|frontend|opensearch} {start|stop|status}" >&2
  exit 2
}

[[ "$ACTION_SERVICE" =~ ^(backend|frontend|opensearch)$ ]] || usage
[[ "$ACTION" =~ ^(start|stop|status)$ ]] || usage
mkdir -p "$RUN_DIR" "$LOG_DIR"

pid_file="$RUN_DIR/$ACTION_SERVICE.pid"
log_file="$LOG_DIR/$ACTION_SERVICE.log"
port=""
case "$ACTION_SERVICE" in
  backend) port=8001 ;;
  frontend) port=6173 ;;
  opensearch) port=9200 ;;
esac

opensearch_home="${OPENSEARCH_HOME:-/data/soft/opensearch-3.8.0}"
backend_python="$ROOT/.venv/bin/python"

port_open() {
  (echo >"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1
}

service_cwd() {
  case "$ACTION_SERVICE" in
    backend) printf '%s' "$ROOT/backend" ;;
    frontend) printf '%s' "$ROOT/frontend" ;;
    opensearch) printf '%s' "$opensearch_home" ;;
  esac
}

pid_is_ours() {
  local pid="$1" cwd command pgid
  [[ -r "/proc/$pid/cmdline" && -e "/proc/$pid/cwd" ]] || return 1
  cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
  command="$(tr '\0' ' ' <"/proc/$pid/cmdline" 2>/dev/null || true)"
  pgid="$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')"
  [[ "$pgid" == "$pid" && "$cwd" == "$(service_cwd)" ]] || return 1
  case "$ACTION_SERVICE" in
    backend) [[ "$command" == *"uvicorn"* && "$command" == *"app.main:app"* ]] ;;
    frontend) [[ "$command" == *"vite"* || "$command" == *"pnpm"* || "$command" == *"npm"* ]] ;;
    opensearch) [[ "$command" == *"opensearch"* || "$command" == *"org.opensearch"* ]] ;;
  esac
}

read_running_pid() {
  [[ -f "$pid_file" ]] || return 1
  local pid
  pid="$(cat "$pid_file")"
  [[ "$pid" =~ ^[0-9]+$ ]] || { echo "Invalid PID file: $pid_file" >&2; return 2; }
  if ! kill -0 "$pid" 2>/dev/null; then
    rm -f "$pid_file"
    return 1
  fi
  if ! pid_is_ours "$pid"; then
    echo "PID $pid no longer matches the recorded $ACTION_SERVICE process; refusing to signal it." >&2
    return 2
  fi
  printf '%s' "$pid"
}

check_opensearch_install() {
  if [[ ! -d "$opensearch_home" ]]; then
    echo "OpenSearch installation not found: $opensearch_home" >&2
    echo 'Install OpenSearch 3.8.0 there or set OPENSEARCH_HOME to its installation directory.' >&2
    return 1
  fi
  if [[ ! -x "$opensearch_home/bin/opensearch" ]]; then
    echo "OpenSearch launcher not found or not executable: $opensearch_home/bin/opensearch" >&2
    return 1
  fi
}

prepare_opensearch_user() {
  local service_user="${OPENSEARCH_USER:-opensearch}" service_group
  command -v runuser >/dev/null 2>&1 || {
    echo 'The runuser command is required to start OpenSearch as a non-root user.' >&2
    return 1
  }
  if ! id "$service_user" >/dev/null 2>&1; then
    if ! command -v useradd >/dev/null 2>&1; then
      echo 'The useradd command is required to create the OpenSearch service user.' >&2
      return 1
    fi
    useradd --system --user-group --no-create-home --home-dir /nonexistent \
      --shell /sbin/nologin "$service_user"
    echo "Created OpenSearch system user: $service_user" >&2
  fi
  service_group="$(id -gn "$service_user")"

  if [[ "$ACTION" == start ]]; then
    # The service user needs read/traverse access to the distribution, including
    # config/jvm.options.d, while the installation remains owned by its installer.
    chgrp "$service_group" "$opensearch_home"
    chmod g+rx "$opensearch_home"
    local install_dir
    for install_dir in bin config lib modules plugins jdk; do
      if [[ -e "$opensearch_home/$install_dir" ]]; then
        chgrp -R "$service_group" "$opensearch_home/$install_dir"
        chmod -R g+rX "$opensearch_home/$install_dir"
      fi
    done

    # OpenSearch writes persistent index data and runtime logs to these directories.
    install -d -o "$service_user" -g "$service_group" \
      "$opensearch_home/data" "$opensearch_home/logs"
    chown -R "$service_user:$service_group" "$opensearch_home/data" "$opensearch_home/logs"
  fi

  # The service script records its PID and output log under the project root.
  chown -R "$service_user:$service_group" "$RUN_DIR" "$LOG_DIR"
  printf '%s' "$service_user"
}

status() {
  local pid
  if pid="$(read_running_pid)"; then
    echo "$ACTION_SERVICE RUNNING (pid $pid, port $port)"
    if [[ "$ACTION_SERVICE" == opensearch ]] && command -v curl >/dev/null 2>&1; then
      curl --fail --silent --show-error --max-time 3 http://127.0.0.1:9200/ 2>/dev/null || true
    fi
    return 0
  else
    case "$?" in 2) return 2 ;; esac
  fi
  if port_open "$port"; then
    echo "$ACTION_SERVICE is not managed by this script, but port $port is occupied." >&2
    return 1
  fi
  echo "$ACTION_SERVICE STOPPED"
}

start() {
  local pid
  if pid="$(read_running_pid)"; then
    echo "$ACTION_SERVICE is already running (pid $pid)."
    return 0
  else
    case "$?" in 2) return 2 ;; esac
  fi
  if port_open "$port"; then
    echo "Port $port is already occupied; refusing to start $ACTION_SERVICE." >&2
    return 1
  fi
  if [[ "$ACTION_SERVICE" == opensearch ]] && port_open 9300; then
    echo 'Port 9300 is already occupied; refusing to start OpenSearch.' >&2
    return 1
  fi

  case "$ACTION_SERVICE" in
    backend)
      [[ -x "$backend_python" ]] || { echo "Python environment not found: $backend_python" >&2; return 1; }
      setsid bash -c 'cd "$1"; shift; exec "$@"' _ "$ROOT/backend" "$backend_python" \
        -m uvicorn app.main:app --host 127.0.0.1 --port 8001 >>"$log_file" 2>&1 </dev/null &
      ;;
    frontend)
      [[ -d "$ROOT/frontend/node_modules" ]] || { echo 'Frontend dependencies are missing; run pnpm install in frontend/.' >&2; return 1; }
      if command -v pnpm >/dev/null 2>&1; then
        setsid bash -c 'cd "$1"; shift; exec "$@"' _ "$ROOT/frontend" pnpm \
          run dev --host 0.0.0.0 --port 6173 --strictPort >>"$log_file" 2>&1 </dev/null &
      elif command -v npm >/dev/null 2>&1; then
        setsid bash -c 'cd "$1"; shift; exec "$@"' _ "$ROOT/frontend" npm \
          run dev -- --host 0.0.0.0 --port 6173 --strictPort >>"$log_file" 2>&1 </dev/null &
      else
        echo 'Neither pnpm nor npm was found on PATH.' >&2
        return 1
      fi
      ;;
    opensearch)
      check_opensearch_install || return 1
      local java_home=""
      [[ ! -x "$opensearch_home/jdk/bin/java" ]] || java_home="$opensearch_home/jdk"
      if [[ -z "$java_home" && -z "${JAVA_HOME:-}" ]] && ! command -v java >/dev/null 2>&1; then
        echo "No bundled JDK at $opensearch_home/jdk and no Java found on PATH." >&2
        return 1
      fi
      if [[ -n "$java_home" ]]; then
        setsid bash -c 'cd "$1"; shift; exec "$@"' _ "$opensearch_home" \
          env OPENSEARCH_JAVA_HOME="$java_home" "$opensearch_home/bin/opensearch" \
          -Ecluster.name=agentserve-local -Enode.name=agentserve-linux \
          -Enetwork.host=127.0.0.1 -Ehttp.port=9200 -Etransport.port=9300 \
          -Ediscovery.type=single-node -Eplugins.security.disabled=true >>"$log_file" 2>&1 </dev/null &
      else
        setsid bash -c 'cd "$1"; shift; exec "$@"' _ "$opensearch_home" "$opensearch_home/bin/opensearch" \
          -Ecluster.name=agentserve-local -Enode.name=agentserve-linux \
          -Enetwork.host=127.0.0.1 -Ehttp.port=9200 -Etransport.port=9300 \
          -Ediscovery.type=single-node -Eplugins.security.disabled=true >>"$log_file" 2>&1 </dev/null &
      fi
      ;;
  esac

  pid=$!
  printf '%s\n' "$pid" >"$pid_file"
  for _ in $(seq 1 60); do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "$ACTION_SERVICE exited during startup; inspect $log_file" >&2
      rm -f "$pid_file"
      return 1
    fi
    if port_open "$port"; then
      echo "$ACTION_SERVICE started (pid $pid, port $port); log: $log_file"
      return 0
    fi
    sleep 1
  done
  echo "$ACTION_SERVICE is still starting or failed readiness; inspect $log_file" >&2
  return 1
}

stop() {
  local pid read_status
  if pid="$(read_running_pid)"; then
    :
  else
    read_status=$?
    [[ "$read_status" -ne 2 ]] || return 2
    if port_open "$port"; then
      echo "Port $port is occupied by an untracked process; refusing to stop it." >&2
      return 1
    fi
    echo "$ACTION_SERVICE is already stopped."
    return 0
  fi
  kill -TERM -- "-$pid"
  for _ in $(seq 1 20); do
    if ! kill -0 -- "-$pid" 2>/dev/null; then
      rm -f "$pid_file"
      echo "$ACTION_SERVICE stopped."
      return 0
    fi
    sleep 1
  done
  kill -KILL -- "-$pid" 2>/dev/null || true
  rm -f "$pid_file"
  echo "$ACTION_SERVICE stopped (forced after timeout)."
}

if [[ "$ACTION_SERVICE" == opensearch ]]; then
  check_opensearch_install || exit 1
  if [[ "$EUID" -eq 0 ]]; then
    service_user="$(prepare_opensearch_user)" || exit 1
    echo "Running OpenSearch service command as $service_user."
    exec runuser -u "$service_user" -- env OPENSEARCH_HOME="$opensearch_home" \
      bash "$ROOT/scripts/service.sh" opensearch "$ACTION"
  fi
fi

case "$ACTION" in
  start) start ;;
  stop) stop ;;
  status) status ;;
esac
