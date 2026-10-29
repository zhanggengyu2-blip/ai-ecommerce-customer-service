# 第三方来源与改造范围

## AgentServe 主工程

- 上游项目：<https://gitee.com/usefullc/agent-serve>
- 建立主工程副本时的来源提交：`781975f7ca6cfff9ba6afefcd669f47a0fdd7f28`。
- 本仓库中的位置：`app/`。
- 原始 Apache License 2.0 全文保留于 [app/LICENSE](app/LICENSE)。
- 来源记录见 [app/BASELINE.md](app/BASELINE.md)。上游原有后台、电商演示、模型与追踪代码不能全部计作本项目原创。

本地改造主要包括中文产品需求与交互设计、五模块交互预览、店铺与账号边界、持久接待和消息去重、迁移、新工作台和客户入口、店铺模型配置及凭据保护、知识版本发布／检索、自动回答与人工接续保护，以及对应检查和交付文档。已实现和未完成部分以当前根 README 及交付说明为准。

## HelpPilot 参考工程

- 参考项目：<https://github.com/poysa213/HelpPilot>。
- 本地参考版本：`3767824fb90b89a8b19fc4169d912645aaf6fe0b`。
- 参考副本、其依赖、模型缓存、配置和 Git 历史位于本机 `reference/HelpPilot/`，不包含在本仓库提交范围。
- 本机原型的运行记录与启动器不随本仓库分发；历史评估仅作参考，不等于当前主工程的已实现功能。

前后端第三方依赖按各自发布的许可证分发，依赖声明与版本记录位于 `app/backend/` 和 `app/frontend/`。
