# 服务启停脚本

统一管理脚本支持 `backend`、`frontend`、`opensearch` 三项服务，并可分别执行 `start`、`stop`、`status`。

## Linux

在项目根目录运行：

```bash
bash scripts/service.sh backend start
bash scripts/service.sh frontend start
bash scripts/service.sh opensearch start

bash scripts/service.sh backend status
bash scripts/service.sh frontend stop
```

OpenSearch 默认目录为 `/data/soft/opensearch-3.8.0`。如安装在其他位置，可通过 `OPENSEARCH_HOME` 指定：

```bash
OPENSEARCH_HOME=/opt/opensearch-3.8.0 bash scripts/service.sh opensearch start
```

## Windows PowerShell

在项目根目录运行：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\service.ps1 backend start
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\service.ps1 frontend start
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\service.ps1 opensearch start

powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\service.ps1 backend status
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\service.ps1 frontend stop
```

OpenSearch 默认目录为 `D:\soft\opensearch-3.8.0`。如安装在其他位置，可在当前 PowerShell 会话设置 `OPENSEARCH_HOME`：

```powershell
$env:OPENSEARCH_HOME = 'E:\tools\opensearch-3.8.0'
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\service.ps1 opensearch start
```

Linux 下前端监听 `0.0.0.0:6173`，可通过 `http://服务器公网IP:6173` 访问；后端 `8001`、OpenSearch `9200` 和 Transport `9300` 仍仅监听本机。前端 Vite 代理会把 API 请求转发到本机后端。请在云服务器安全组和系统防火墙中开放 TCP `6173`。

Linux 下以 root 执行 OpenSearch 的 `start`、`stop` 或 `status` 时，脚本会自动创建默认系统用户 `opensearch`（可用 `OPENSEARCH_USER` 更改），授予该用户读取程序和配置文件的组权限，并将 OpenSearch 的 `data`、`logs` 以及项目的 `var/run`、`var/log` 目录交给该用户管理，再以该用户运行服务。OpenSearch 本身不会以 root 启动。

当前公网访问使用 Vite 开发服务器，适合演示或临时访问；生产长期运行建议构建前端并由正式 Web 服务托管。Windows 脚本仍绑定本机地址。日志写入 `var/log/`，PID 记录写入 `var/run/`。`stop` 只会停止由对应脚本启动并记录的进程。若 OpenSearch 目录或启动器不存在，脚本会提示默认路径及 `OPENSEARCH_HOME` 覆盖方式。
