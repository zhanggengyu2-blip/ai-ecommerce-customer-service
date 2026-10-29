# 本地原版页面预览

> 历史运行记录。首次推送不包含原上游 SQL 数据转储、参考工程和本机凭据，因此本文件中的原版数据库预览步骤不能直接用于新克隆环境。当前主工程按[根目录说明](../README.md)启动，无需 SQL 转储；五模块内存预览仍可直接使用。

已于 2026-10-18 启动并验证管理员、客服登录，以及会话、知识文档和 Prompt 列表读取。界面和业务处理仍是 AgentServe 原版，尚未按已确认产品定义改造。

访问：<http://127.0.0.1:6173/>。

买家页面预览使用 <http://localhost:6173/>，已于 2026-10-18 登录演示买家并展示历史聊天。两个地址使用同一套前后端；使用不同浏览器来源可分别保留管理员与买家登录，角色仍由登录账号决定。

原工程公开演示账号：

| 用途 | 账号 | 密码 |
| --- | --- | --- |
| 浏览管理、知识及配置页面 | `admin@demo.local` | `请使用本机配置的密码，不随仓库分发` |
| 浏览客服工作台 | `pdd-agent-a` | `oKfnIxDr5DgGXKgNYqA` |
| 浏览买家咨询、会话及订单入口 | `pdd-buyer-1001` | `DJjBs4DnUmUsF6TQpoo` |

## 运行方式

以下命令在 `app/` 目录执行。当前使用已配置的稳定 Python 3.12 虚拟环境；本机默认 `python3` 是旧的 3.11 测试版，不适合直接重建本次环境。

后端：

```sh
.venv/bin/python scripts/preview_backend.py
```

前端（另一个终端）：

```sh
cd frontend
/Users/zhanggengyu/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node node_modules/vite/bin/vite.js --host 127.0.0.1
```

如需重装演示依赖，使用稳定 Python 创建 `.venv` 后运行：

```sh
.venv/bin/python -m pip install -r scripts/preview-requirements.txt
```

## 演示边界

- 后端仅监听 `127.0.0.1:8001`，前端由 Vite 代理到此地址。
- 独立 SQLite 数据库位于 `var/preview/agentserve.db`。首次启动导入原工程的公开演示账号、知识、商品、订单及相关会话；已初始化时沿用，不自动覆盖。
- 不导入旧游客身份及原始模型请求日志；未接入真实淘宝或其他生产店铺。页面中的拼多多及电商管理入口属于原版演示，不改变已确认的第一版范围。
- 启动器使用模拟 AI 和业务模式，清空外部模型、检索、存储及业务接口配置，不读取上游 `.env`，不会使用真实模型 Key。页面浏览可用不等于模型或真实平台联调通过。
- 后端重启会生成新的演示会话签名密钥，已有登录需要重新登录。
