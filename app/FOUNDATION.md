# 后端基础改造交付说明

更新：2026-10-21。阶段：店铺／账号与持久接待主链路已实现并完成本机联调。本文件保留基础阶段交付记录；后续真实模型与知识进展见[模型与知识交付](./MODELS_KNOWLEDGE.md)，不代表第一版完整功能已验收。

## 1. 已经可以做什么

客户从本项目聊天入口进入本店身份，消息存入数据库；本店客服上线后接入、回复并完结。客户的聊天入口不变，每次完结后的新问题或客服重新发起都会产生独立接待，旧消息和旧接待可查。刷新页面及重启后端不会重置这些数据。

- 店铺归属由登录身份决定；不同店铺无法互相读取入口、接待、消息或客服。
- 本店客服统一 CUSTOMER_SERVICE 身份，共享本店数据；只有当前负责人可以回复、完结接待。
- 新端登录替换旧端；旧令牌不能回复、续心跳、改账号或退出新端登录。停用客服使该账号的令牌立即失效。
- 手动离线不影响已有接待，但不能接入或重开；新接入还需最近 30 秒内的有效心跳。
- 消息绑定客户入口、接待、发送人及客户端唯一编号。同编号同内容重试返回原消息，不重复落库；不同内容返回 409。
- 多客服同时接入只成功一人。重开使用请求编号去重，同编号重试返回同一新接待；已有活动接待时拒绝另建。
- 客户结束请求绑定明确接待编号，旧请求不会结束后来新建的接待。刷新已完结的聊天只读取历史，不创建空接待。
- 工作台按稳定客户入口分页；消息按游标连续读取；历史按每次接待查询，保留真实发送客服及时间。

## 2. 体验入口

先保持后端 8002 和前端 6174 运行，再打开：

| 用途 | 本机地址 |
| --- | --- |
| 真实客服工作台 | [打开工作台](http://127.0.0.1:6174/?mode=live) |
| 客户聊天入口 | [打开青禾服饰聊天](http://127.0.0.1:6174/?mode=customer&store=qinghe) |
| 原五模块内存预览 | [原预览](http://127.0.0.1:6173/?preview=workbench) |
| 已实施 API 交互文档 | [本机接口](http://127.0.0.1:8002/docs) |

新工作台账号为 `qinghe-service`，随机密码在本机 [local-login.txt](./var/foundation/local-login.txt)。该文件只包含本机登录信息，不含后台签名密钥。`local-access.json` 保存开发运行密钥与初始化信息，`var/` 不进入版本管理。

客户凭据按店铺保存在当前浏览器。同一浏览器再次打开同店入口会恢复原身份；另一个浏览器可模拟另一位客户。客服登录令牌按页签保存，新登录会使前一端失效。

建议体验：客服登录后切换在线 → 客户发送问题 → 工作台接入并回复 → 客户查看回复 → 完结 → 查看历史 → 客户继续咨询或客服重新发起。不要把原演示页的数据与真实工作台的数据混合判断。

## 3. 启动与数据位置

在项目根目录运行后端：

```bash
app/.venv/bin/python app/scripts/foundation_backend.py
```

另开终端启动前端（已有 Node.js 环境）：

```bash
cd app/frontend
VITE_API_TARGET=http://127.0.0.1:8002 npm run dev -- --host 127.0.0.1 --port 6174
```

脚本首次建立 `app/var/foundation/service.db`、随机登录信息和一家本机开发店铺；再次启动保留现有记录，不重新导入演示消息。只初始化可加 `--initialize-only`。默认仅绑定本机地址。

仍是同一个 FastAPI 工程及同一个 Vue 工程。后端由 `FOUNDATION_ENABLED=true` 启用新模式，挂载受店铺身份约束的基础接口；false 保留原模式以兼容旧预览。两套路由不同时挂载。新模式不开放旧的演示登录、内部客户签发、旧电商或 WebSocket 路由。原五模块预览继续使用内存数据；真实入口复用工作台组件，通过独立数据服务读取新接口。

当前刷新方式：文本消息、工作台列表每 3 秒查询，客服每 10 秒发送心跳。不是 WebSocket 实时推送。本阶段前端遍历分页后提供本地筛选；大量客户下的按需加载与历史性能优化需后续联调。

## 4. 数据结构及迁移

实际新增 `chat_thread`（稳定聊天入口）、`reception_request`（重开请求及其结果）；扩展 tenant、channel_account、user、conversation、message。原表与原字段保留。SQLAlchemy 数据模型与 Alembic 迁移分别维护，不用启动建表代替升级。

| 版本 | 内容 |
| --- | --- |
| `20261021_01` | 冻结改造前的 27 张表结构，作为迁移基线 |
| `20261021_02` | 新增入口／重开请求，扩展店铺绑定、有效端、接待版本、摘要预留和消息去重字段 |

SQLite 旧库必须显式选择 `upgrade(engine, adopt_legacy=True)`。工具核对列、类型、空值、主键、唯一约束、外键与索引；不识别的结构停止，不强行盖章。升级前使用 SQLite 备份接口生成同目录 `.backup-*` 文件，升级后检查外键。已经位于当前版本时只核对，不反复生成备份。迁移不提供自动删列降级，失败恢复使用已验证备份。

为保留旧数据，店铺映射及旧消息的新增归属字段暂允许为空；新模式写入始终由服务端赋值并校验。单租户单店、客户入口及消息去重有唯一约束；冗余归属和活动接待指针在事务中检查。完整组合外键和历史归属回填仍在后续迁移范围。

原预览有 4 个平台账号，不能推断如何拆成独立店铺。本轮只在数据库副本上验证升级，原预览数据库未直接迁移或重置。副本升级前后 8 个用户、23 次接待、239 条消息、4 个平台账号均保留，外键检查无错误。未映射账号会阻止新模式启动，不静默分配店铺、合并聊天或推算历史人工事实。

已有 MySQL 数据库的基线认领与归属回填需要独立核对；当前工具不会自动认领无版本 MySQL 旧库。本轮 MySQL 验证使用新建隔离数据库，不能当作正式历史数据迁移已完成。

## 5. 已实施接口

错误格式为 `detail.code`／`detail.message`；分页默认 25、最多 100。统一错误 request_id 随后续追踪层补齐。完整字段以运行中的 `/docs` 与代码为准。

| 范围 | 接口 |
| --- | --- |
| 登录 | `POST /api/auth/login`、`GET /api/auth/me`、`POST /api/auth/logout` |
| 在线与连接 | `PUT /api/agent/presence`、`POST /api/agent/heartbeat` |
| 店铺及客服 | `GET /api/admin/store`、`GET /api/admin/users/page`、`POST /api/admin/users`、`PATCH /api/admin/users/{id}` |
| 客户身份与入口 | `POST /api/auth/guest-session`、`POST /api/customer/chat`、`GET /api/customer/threads/{id}` |
| 客户消息与结束 | `GET／POST /api/customer/threads/{id}/messages`、`POST /api/customer/threads/{id}/end` |
| 工作台列表与消息 | `GET /api/agent/threads`、`GET /api/agent/threads/{id}/messages`、`GET /api/agent/conversations/{id}/messages` |
| 接入／回复／完结／重开 | `POST /api/agent/conversations/{id}/claim`、`messages`、`close`、`reopen` |
| 历史 | `GET /api/admin/conversations`、`GET /api/admin/conversations/{id}`、`GET /api/admin/conversations/{id}/messages` |

发送使用 `client_message_id`；状态变更使用 `expected_epoch`；重开额外传请求体 `request_id`。同一个去重编号不得换参数复用。客户结束额外绑定 `conversation_id`。客户端不可传入任意角色或店铺编号来改变身份归属。

## 6. 验证结果

| 检查 | 结果与证据 |
| --- | --- |
| SQLite | [12 项通过](../output/foundation-2026-10-21/sqlite-tests.txt)：身份隔离、有效端与停用、访客恢复、接待／完结／重开、去重、分页、并发、过期版本与心跳、损坏指针拒绝、旧结构及数据保留 |
| MySQL Community 8.4.11 | [10 项 API 集成检查通过](../output/foundation-2026-10-21/mysql-tests.txt)：真实迁移、事务、唯一约束、并发接入／消息去重／重开，不用 SQLite 结果代替 |
| 旧预览副本 | 结构认领、备份、增量升级、数据及外键审计通过；未知结构和未映射店铺拒绝进入新模式 |
| 前端 | `vue-tsc --noEmit` 类型检查及 [Vite 构建](../output/foundation-2026-10-21/frontend-build.txt)通过 |
| 浏览器 | 客户发送、人工接入回复、完结、新建独立接待、历史查看及重启后恢复；[历史截图](../output/foundation-2026-10-21/history.png) |

自动检查代码位于 `backend/tests/test_foundation.py`。从项目根目录执行 SQLite 检查：

```bash
PYTHONPATH=app/backend JWT_SECRET=foundation-tests-distinct-local-key-2026 app/.venv/bin/python -m unittest discover -s app/backend/tests -v
```

对一个专用 MySQL 测试实例执行：

```bash
app/.venv/bin/python app/scripts/test_foundation_mysql.py --host 127.0.0.1 --port 3306 --user root
```

该检查会创建随机命名的 `foundation_tests_*` 数据库，完成后删除自己创建的库；连接账号需要对应权限。本轮临时 MySQL 容器在检查完成后移除，不作为应用运行依赖。测试框架出现 httpx 兼容弃用提示，检查仍通过，本轮未因此升级依赖。

## 7. 后续阶段

后续已接通真实 AI、模型密钥保护、知识发布与检索、自动回答及调用追踪，见[模型与知识交付](./MODELS_KNOWLEDGE.md)。开启自动接待后新咨询进入 AI；原人工接待保持不变。内部回复建议、WebSocket、定时补位、头像／图片、工单、本地电商接口适配与完整分析仍待后续。

摘要当前为 NONE 和空文本，没有摘要任务，也没有伪造 Token。后续摘要及重试单独追踪，**不计入会话 Token 总量，不影响接待用量完整性**。淘宝消息接收、订单查询及服务于这两项的授权、回调、远程同步本版暂不接入。

模型配置、发布知识、真实回答与追踪现已贯通，提交回答前会复核接待版本与有效知识。下一步建议继续实现人工回复辅助，再补计时、安抚及断线接管。
