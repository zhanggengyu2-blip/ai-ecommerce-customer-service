# 模型配置与知识检索交付说明

更新：2026-10-21。接在[后端基础改造](./FOUNDATION.md)之后，现已接通真实模型、知识发布、检索、自动回答与调用追踪。第一版其余功能继续按实施清单推进。

## 1. 当前可以体验

| 入口 | 用途 |
| --- | --- |
| [模型配置](http://127.0.0.1:6174/?mode=live#models) | 三类模型与 Key 校验、保存，AI 自动接待开关，Top K 与 Score |
| [知识管理](http://127.0.0.1:6174/?mode=live#knowledge) | 知识库分类、纯文本正文、分段预览、发布、用途、有效期、停启用及恢复上一版 |
| [召回测试](http://127.0.0.1:6174/?mode=live#recall) | 使用本店有效知识与正式检索设置，查看真实相关度和来源，不发客户消息 |
| [调用记录](http://127.0.0.1:6174/?mode=live#traces) | 查看每次模型请求、检索候选、阈值、来源、结果与供应商报告的用量 |
| [客户入口](http://127.0.0.1:6174/?mode=customer&store=qinghe) | 新咨询由 AI 接待；可以查看来源、请求人工、结束后再次咨询 |

已复用此前提供的 Key，按青禾店铺加密保存并完成真实调用校验。当前选用：对话 `deepseek-flash`、向量化 `text-embedding-v4`（1024 维）、重排 `qwen3.7-text-rerank`。Key 不返回明文、不进入请求追踪；前端只显示有无配置及末四位提示。换服务商时必须提供对应服务商的 Key，不能把原服务商凭据直接带过去。

开发库内有一篇 **“示例·知识检索验证”**，分类为“联调示例（可停用）”。这是明确标注的验证资料，不代表店铺售后政策。客户发送“联调验证口令是什么？”，已通过真实模型返回 `QH-2026-AI`，并展示对应知识来源。该篇已经从浏览器完成一次再次发布，保留了上一版本。

AI 自动接待当前已开启。此前人工负责的接待保持人工状态；完结后再次咨询才创建新的 AI 接待。需要订单、库存、物流或退款事实及办理动作的问题，在当前阶段转人工，不编造本地业务结果。

## 2. 实际处理链路

客户消息在同一事务中保存并创建去重任务 → 后台读取本店模型与有效知识 → 对话模型理解诉求并选择知识元信息 → 词法候选与真实向量候选合并 → 真实重排 → 应用相关度阈值及 Top K → 对话模型生成有来源的结构化回答 → 程序复核状态、配置及知识有效性 → 保存回答、引用和追踪 → 页面查询更新。

- 模型只提交结构化建议，程序核对片段编号、店铺和接待范围；不会开放自由业务写工具。
- 模型按当前接待的真实消息取上下文，不自动混入同客户其他接待或未发送草稿。
- 知识分类与用途仅帮助选择候选；选择为空或无合格结果时可扩大到本店全部有效知识，不能选到其他店。
- Score 使用本次重排返回的 0–1 相关度，不套用 RRF 融合分数，也不作为跨问题的绝对置信度。缺分数或重排失败不能绕过阈值。
- 向量分支失败可保留词法候选，仍必须通过重排及阈值；没有依据时转人工。
- 人工接入、客户结束、转人工、新消息到来、关闭自动接待会使不再适用的结果失效。配置或引用知识变化时重新准备；过期结果不会继续发给客户。

本阶段用数据库保存向量，在后端计算小规模语义检索，结合词法候选及 RRF，再调用真实重排。**尚未接通 OpenSearch**，不把这一实现声称为最终检索容量方案。前端仍每 3 秒查询消息，WebSocket 后续接入。

## 3. 配置与发布怎样安全生效

模型配置继续使用 config_version。一次提交时服务端真实校验变更项；客户端自报“已验证”不被接受。Key 采用 cryptography 的 Fernet 认证加密，读取时校验店铺、用途及验证指纹；所有调用显式携带当前店铺配置，不使用其他店或环境全局 Key 兜底。服务地址来自后端适配清单，客户端不能任意指定 URL。

开发加密主密钥保存在 `app/var/foundation/model-encryption.key`，权限 0600，独立于数据库和业务配置。正常重启保留该文件；部署时可通过 `MODEL_ENCRYPTION_KEY` 注入。缺失或不匹配时明确报错，不悄悄切换凭据。

切换向量化模型或维度时，创建 PREPARING 配置和向量重建任务。旧配置与旧向量继续可用；当前、计划生效及可恢复版本准备成功后，在短事务内检查资料版本并原子切换。准备期间知识发生变化会重新核对、重做；失败保留原配置，不混用相同维度但不同模型的向量。

知识发布保存候选版本，后台生成用途、分段和真实向量，成功后才设置为 PUBLISHED。失败记录仍可编辑重试，原发布版本及引用片段保留。当前不修改已发布切片来冒充新版本；历史引用保留当时的来源文本。

知识入口每次一个 UTF-8 纯文本文件，不超过 2 MB，支持 MD、Markdown、TXT、CSV、TSV、JSON、YAML、YML、XML、LOG；也可以直接提交正文。上传先解析到编辑区，不直接发布。服务端检查扩展名、编码、NUL、大小；预览与正式发布使用同一分段逻辑，不要求先预览才能发布。单次最多 500 个切片，超限明确报错，不静默截断。

分段默认 500 字、重叠 50 字；允许 100–4000、重叠小于长度。未来版本生效前保留原有效版本；最新已生效版本到期后不自动回找旧内容。恢复只取上一已发布版本并保留它自己的原有效时间，过期内容恢复后仍不能回答。

## 4. 后台任务与用量

本阶段新增 ai_generation 和 knowledge_job，以数据库任务与租约运行；本机后端自动启动一个后台线程。任务保存后不依赖浏览器继续打开，重启后可以接管过期租约。租约为 180 秒，每完成一个模型步骤续期；网络错误单次最多重试一次，任务占用恢复最多三轮。知识发布业务失败保留候选，由用户修订后重新发布。模型请求期间不占用接待写锁，提交结果前再锁定并复核。

当前不是 Celery／Redis 调度，也未完成高并发容量验证；外部队列、独立 Worker、OpenSearch 及定时接管属于后续部署与业务阶段。30 秒心跳检查仍仅影响新接入资格，未宣称实现 AI 断线补位、5 分钟自动完结或 300 秒安抚。

追踪区分 `question`、`config_check`、`ingestion`、`recall_test` 等。会话 Token 仅累计该次接待的 `question`／`assist`／`comfort` 模型请求，包括其中实际发生的重试；**摘要及摘要重试、配置检查、知识处理、召回测试不计入会话总量**。摘要仍未接后台生成，不伪造文本或用量。

供应商未报告 Token、请求超时或追踪存储缺失时，显示已知总量及不完整状态，不将缺失记作已确认的零。摘要缺少用量不影响接待用量的完整性判断。

## 5. 数据与接口

迁移 `20261021_03`：新增 knowledge_category、ai_generation、knowledge_job；扩展 document 的分类与版本、document_version 的用途和分段设置、chunk 的向量空间、message 的追踪与 AI 消息去重；独立任务的追踪允许不关联客户接待。已有独立开发库在备份后升级，旧聊天保留。

| 范围 | 主要接口 |
| --- | --- |
| 模型 | GET／PUT `/api/admin/settings/models`；POST `/api/admin/settings/models/check` |
| 检索与开关 | GET／PUT `/api/admin/settings/retrieval`、`/api/admin/settings/reception` |
| 分类 | GET／POST `/api/admin/knowledge-categories`；PATCH／DELETE `/{id}` |
| 知识 | GET `/api/admin/documents`、`/{id}`；POST `/publish`；PATCH `/{id}`；POST `/{id}/restore-previous` |
| 正文与预览 | POST `/api/admin/knowledge/upload-text`、`/api/admin/knowledge/previews` |
| 处理进度 | GET `/api/admin/knowledge/jobs/{id}` |
| 召回测试 | POST `/api/admin/recall-tests` |
| 追踪与用量 | GET `/api/admin/traces`、`/{trace_id}`；GET `/api/agent/conversations/{id}/usage` |
| 客户请求人工 | POST `/api/customer/threads/{id}/handoff`，绑定 conversation_id 和 expected_epoch |

错误包含 `detail.code`、`message`、`request_id`；参数错误给出字段信息，不回显被拒绝的 Key。具体字段及返回见[本机接口文档](http://127.0.0.1:8002/docs)。

## 6. 验证与后续

- SQLite：[24 项通过](../output/models-knowledge-2026-10-21/sqlite-tests.txt)，含基础迁移、旧记录、隔离、密钥、发布、有效期、向量切换、租约恢复、过期结果、缺失追踪与摘要排除口径。
- MySQL 8.4：[22 项接口检查](../output/models-knowledge-2026-10-21/mysql-tests.txt)，使用独立随机数据库与受控模型响应，验证迁移、事务及相同业务边界，不用模拟结果冒充真实模型质量。
- 真实服务：三类配置实调通过；示例用途生成、向量发布、浏览器再次发布、召回、客户回答及来源展示通过。本次示例客户问答记录 4 次模型请求，共 852 个供应商报告 Token；独立召回测试的 497 个 Token 未加到该接待。
- 前端：类型检查和[构建](../output/models-knowledge-2026-10-21/frontend-build.txt)通过；截图见[召回结果](../output/models-knowledge-2026-10-21/recall.png)、[客户回答](../output/models-knowledge-2026-10-21/customer-answer.png)、[调用记录](../output/models-knowledge-2026-10-21/trace.png)。

启动仍使用 `app/.venv/bin/python app/scripts/foundation_backend.py`，前端仍为 6174；重复启动保留数据、Key 和配置。仅本机首次导入此前已提供的凭据时使用 `app/scripts/configure_local_models.py --entry-code qinghe`；`--seed-demo` 只创建明确标注的联调示例，不覆盖已有配置或知识。

建议下一步接入人工回复辅助与接待计时：复用本阶段模型、有效知识及结果失效保护，区分未发送建议和客户消息，再完成断线补位与安抚。工单、本地电商查询适配、完整统计、头像／图片、摘要任务仍待后续。淘宝消息接收和订单查询继续排除在本版接入范围外。

## 官方适配依据

- [DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：结构化回复与非思考模式。
- [百炼同步向量接口](https://help.aliyun.com/zh/model-studio/text-embedding-synchronous-api)：模型、批量及维度，实际返回逐项校验。
- [百炼文本排序](https://help.aliyun.com/zh/model-studio/text-rerank-api)：原生 HTTP 请求结构、相关度及用量。
- [百炼兼容 Chat](https://help.aliyun.com/zh/model-studio/qwen-api-via-openai-chat-completions)：受控服务地址及调用方式。
