# AI 电商智能客服

面向单店客服接待的 AI 应用开发项目。当前版本完成了店铺与账号隔离、持久化聊天、人工接续，以及真实模型配置、知识发布、检索回答和调用追踪。它是开发阶段的可运行版本，尚未完成第一版全部功能，也没有生产规模或业务收益验证。

## 当前范围

- 客户使用本项目聊天入口咨询；客服可接入、回复、完结并查看独立接待历史。
- 店铺配置对话、向量化及重排序模型，服务端验证并加密保存 Key。
- 知识支持分类、纯文本上传、分段预览、发布、有效期、停启用及恢复上一版。
- 回答使用有效知识并显示来源；依据不足、需要真实业务查询或办理时转人工。
- 调用记录保留模型步骤、耗时、重试及已知 Token；摘要及其重试不计入会话总量。

当前使用数据库保存向量，由后端完成小规模检索；任务采用数据库租约和本机后台线程。OpenSearch、独立任务队列、回复辅助、摘要生成、工单及定时补位尚未完成。淘宝消息接收、订单查询及相关授权／同步不在本版接入范围内。

## 从干净目录启动

以下命令在项目根目录执行，适用于 macOS／Linux。使用 Python 3.12、Node.js 24 和 pnpm 11；后端依赖快照基于本机已验证的 Python 3.12 环境。

```bash
python3.12 -m venv app/.venv
app/.venv/bin/python -m pip install -r app/backend/requirements.lock.txt
pnpm --dir app/frontend install --frozen-lockfile
app/.venv/bin/python app/scripts/foundation_backend.py
```

另开终端运行前端：

```bash
cd app/frontend
VITE_API_TARGET=http://127.0.0.1:8002 pnpm dev --host 127.0.0.1 --port 6174
```

- 工作台：<http://127.0.0.1:6174/?mode=live>
- 客户入口：<http://127.0.0.1:6174/?mode=customer&store=qinghe>
- 接口文档：<http://127.0.0.1:8002/docs>

首次启动自动迁移 SQLite 并创建开发店铺、随机客服密码和加密主密钥，保存在被忽略的 `app/var/foundation/`。账号和密码见该目录的 `local-login.txt`；重复启动保留数据。无需导入上游 SQL、复制旧数据库或先启动 MySQL、Redis、OpenSearch。

仓库不携带作者的模型 Key、聊天数据和已发布知识。首次运行后，在“模型配置”填写自己的 Key 并保存，在“知识管理”发布测试知识，然后开启 AI 自动接待。可以先体验人工接待；真实模型调用可能产生供应商费用。`configure_local_models.py` 是原本机导入工具，依赖未随仓库分发的参考目录，不是新环境启动步骤。

`app/.env.example` 保留上游模式的字段示例，不含可用凭据；当前推荐启动器会自动配置新模式。`app/README.md` 中的上游部署说明和旧预览不等于本版本的启动步骤。

## 验证

下面的 SQLite 检查使用临时数据库和受控模型响应，不调用付费模型，也不修改现有聊天库：

```bash
PYTHONPATH=app/backend JWT_SECRET=foundation-tests-distinct-local-key-2026 app/.venv/bin/python -m unittest discover -s app/backend/tests -v
pnpm --dir app/frontend build
```

MySQL 检查、真实模型联调与已知限制见[模型与知识交付说明](app/MODELS_KNOWLEDGE.md)。报告和截图位于 `output/` 中已筛选的目录；它们是开发环境验证证据，不代表生产效果评测。

## 阅读顺序与来源

1. [产品文档入口](docs/README.md)：需求、设计、验收和实施进度。
2. [基础改造交付](app/FOUNDATION.md)：身份、接待、持久化和迁移。
3. [模型与知识交付](app/MODELS_KNOWLEDGE.md)：真实模型、知识处理、追踪与限制。
4. [首次推送准备记录](docs/首次推送准备.md)。

本项目基于 AgentServe 修改，保留了[上游许可证](app/LICENSE)，来源与改造范围见[第三方来源说明](THIRD_PARTY_NOTICES.md)。`reference/`、旧 HelpPilot 的本机运行记录与启动器不随本仓库分发。部分历史评估文档保留本机参考源码的位置，当前启动方式及功能范围以本说明和交付文档为准。
