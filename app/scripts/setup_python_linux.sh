#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
project_root="$(cd -- "$script_dir/.." && pwd)"
requirements="$project_root/backend/requirements.txt"
venv_path="$project_root/.venv"
python_path="$venv_path/bin/python"
export PIP_INDEX_URL="${PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"

if [[ ! -f "$requirements" ]]; then
  echo "Requirements file not found: $requirements" >&2
  exit 1
fi

if [[ ! -x "$python_path" ]]; then
  if ! command -v python >/dev/null 2>&1; then
    echo 'Python 3 was not found. Install Python 3 and its venv package first.' >&2
    exit 1
  fi
  python -m venv "$venv_path"
fi

"$python_path" -m pip install -r "$requirements" --index-url "$PIP_INDEX_URL" --only-binary :all:
echo "Python environment ready: $venv_path"
