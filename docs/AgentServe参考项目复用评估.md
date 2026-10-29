# AgentServe 参考项目复用评估

状态：参考研究，不代表新增已确认需求或决定替换现有原型。需求澄清仍按用户要求暂停。

本轮已公开下载源码到 `reference/agent-serve`，核查版本为 `781975f7ca6cfff9ba6afefcd669f47a0fdd7f28`，并读取视频简介、仓库说明和项目截图。未完整观看视频，未启动项目、安装依赖、执行其脚本、调用模型或操作在线演示；以下是源码静态评估，不代表功能验收。仓库公开，不需要本次用户提供的登录凭据；凭据未用于下载，未写入文件。

来源：[视频](https://www.bilibili.com/video/BV1rPpb6kEay/)、[源码仓库](https://gitee.com/usefullc/agent-serve)。仓库包含 [LICENSE](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/LICENSE>)，标注 Apache-2.0；实际摘用时保留适用的许可与归属文件，不将本轮比较当作依赖许可的完整审查。

## 1. 结论

这个项目比上一参考项目更贴近电商客服：代码将业务查询与知识问答分流，并支持组合两者回答。最值得抽取改造的是 AI 路由与上下文处理、知识检索与版本管理、回答依据和操作留痕。会话基础与配置界面也能参考。

当前不存在已验证“整块接入即可使用”的业务模块：它以 FastAPI、SQLAlchemy、MySQL、OpenSearch 和 Vue 组织，而现有 HelpPilot 原型使用 LangGraph、Chroma 和 Streamlit。Python 代码有利于抽取迁移，但数据访问、状态、服务接口和页面仍需适配，不据此预先锁定新技术栈。

## 2. 重点复用候选

| 候选 | 源码中已核实的内容 | 适用于本项目的方式 |
| --- | --- | --- |
| AI 问题分流和上下文 | 规则与模型分类结合；business / knowledge / hybrid 分支；保留当前订单/商品标识；动态事实问题保护 | 优先抽取其判断顺序及数据校验方法，帮助 AI 区分查订单、查政策或同时查询；多订单能力另改 |
| 知识检索与回答引用 | 关键词和向量候选融合、重排、只选允许的生效版本；保留文档/版本/片段引用 | 作为政策与自由补充资料的检索候选实现；商品短备注和结构化政策答案继续按既有范围精确匹配，不强制全部切片 |
| 知识发布及版本管理 | 草稿发布、生效/失效时间、停用、历史回滚；查询时选择有效版本 | 借鉴底层版本规则和状态处理；商家前端保持简单问答及备注，不强迫理解向量化；旧政策是否可回退必须按适用性判断 |
| Prompt 与模型配置 | Prompt 按租户及 Key 维护、管理员编辑，后续请求读取；模型/RAG 配置支持草稿发布 | 可复用部分接口与页面结构；本项目需要限制两家服务商并实现商家自带 Key，当前源码不具备该完整能力 |
| AI 过程记录与处理留痕 | 记录路由、上下文来源、检索片段、工具查询、最终回答与动作结果；模型请求等字段有脱敏处理 | 分成内部 AI 排查记录与客服可读的处理摘要；对应此前 side effect 讨论，无需恢复独立任务管理模块 |
| 会话与人工接管基础 | 消息存储、AI/人工状态、人工接管、发送及手动关闭；接管用条件更新保证只成功一次 | 可借鉴底层消息及并发接管方法；定向派单、轮询资格保留、容量、离线补位和 AI 回复建议需按本项目规则实现 |
| 模拟电商业务 | 本地商品、订单、物流、退款等演示数据，以及统一业务工具入口 | 可用作独立测试租户的样例和适配器设计参考，不冒充真实平台授权/查询能力 |

## 3. 重要代码依据

- 路由与上下文：[routing.py](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/services/routing.py:155>)、[orchestrator.py](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/services/orchestrator.py:47>)。hybrid 分支会先形成业务事实，再取相关政策补充回答；它是固定路由及业务分支，不代表已实现任意自主规划。
- 检索及引用：[knowledge.py](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/services/knowledge.py:305>)、[知识回答组装](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/services/orchestrator.py:169>)。结构化业务事实从查询结果提供，知识回答保留文档、版本及片段编号。
- 发布与回滚：[knowledge.py](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/api/v1/knowledge.py:323>)、[有效版本选择](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/services/knowledge_lifecycle.py:13>)。长文切分基础函数位于 [chunks_for](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/services/knowledge.py:58>)，可作为小范围抽取候选，仍需检查条款完整性。
- Prompt：[配置接口](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/api/v1/configuration.py:67>)、[运行时读取](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/services/runtime_config.py:18>)。当前 Prompt 保存直接更新，不要将模型/RAG 的版本发布能力误写为 Prompt 已有完整版本发布和回滚。
- 过程留痕：[tracing.py](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/services/tracing.py:1>)、[Trace 模型](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/models/trace.py:7>)、[AuditLog](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/models/system.py:7>)。记录工具输入输出不等于外部业务已经完成；面向客服应显示实际动作、对象、结果与来源，不直接展示整份模型请求。
- 并发接管：[support.py](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/api/v1/support.py:34>)。当前是有范围权限的待接管队列，不是已实现本项目定向通知和超时轮询。

## 4. 不能直接照搬的边界

1. **真实淘宝接入未实现。** 视频简介明确商品、订单、支付、物流、退款为本地模拟数据，尚未接通拼多多、抖店等真实授权、同步和消息。源码 [business.py](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/providers/business.py:20>) 有 mock/通用 HTTP 工具入口，不能当成淘宝官方适配器。
2. **尚非本项目要求的多租户 SaaS。** 虽然不少表和查询含 tenant_id，身份验证在 [security.py](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/core/security.py:38>) 限定 tenant_id=1，用户对象也被限制为租户 1。不能只看到租户字段就认为多商家隔离与开通已完成。
3. **没有完整的商家自带 Key 页面配置。** [chat](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/providers/ai.py:103>) 从服务端 settings 读取地址和 Key；[配置页面](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/frontend/src/views/admin/ConfigsPage.vue:39>) 明确仅配置模型名，凭据在环境变量。需要改造为本项目按租户、按用途管理的模型配置；用户最新已撤销单 Key，改为商家自行配置相关模型及凭据，可复用或分开填写，第三用途名称待确认。
4. **多订单处理不匹配。** [routing.py](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/services/routing.py:302>) 遇到多个订单会要求一次选一个。本项目已确认一次人工事件可涉及多个订单，不能照搬其单订单交互限制。
5. **平台政策与商家政策的关系需重做。** [检索选择](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/services/knowledge.py:311>) 按账号/平台/通用范围排序，并以同标题去重选择。不能用此规则替代我们已确定的政策适用边界；平台基础资料跨租户复用、租户商家约定及商品范围还需明确实现。
6. **用户确认退款不等于客服审批。** [PendingAction](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/models/conversation.py:37>) 主要用于客户确认取消订单/申请退款，[确认执行](</Users/zhanggengyu/Documents/AI 电商智能客服/reference/agent-serve/backend/app/api/v1/customer.py:218>) 会重查资格与金额并记录结果不明。可以借鉴防重复和结果留痕，但不能将其作为我们的人工审核方案，更不能据此恢复已挂起的任务模块。
7. **完整电商后台及运营统计暂不迁入。** 商品台账、支付、库存流水等不在已确定的工作台范围；数据面板继续后置。取会话中所需的查询和展示即可。

## 5. 建议参考顺序

优先研究“问题分流＋业务事实＋按需知识”如何形成回答，再研究知识维护和回答依据排查；会话基础按现有协作约定改造。无需先迁移完整电商后台，也不因参考项目已有某页面便新增需求。

这次只保存源码参考副本与评估，未将其中模块接入现有原型，未变更已确认产品范围。后续恢复需求讨论时，可从中选择对 AI 独立解决问题真正有帮助的部分。
