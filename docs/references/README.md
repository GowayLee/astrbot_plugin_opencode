## 用途

`docs/references/` 是给本仓库后续开发和规划使用的参考入口，不是终端用户手册。

这里的文档只做三件事：

- 说明应该先看哪些官方资料。
- 说明这些资料和本仓库哪些代码最相关。
- 把后续 Phase 3/4 会反复查阅的协议边界集中成稳定入口。

## 阅读顺序

1. `astrbot/README.md`
   先看宿主框架怎么注册插件、读取配置、发消息和管理会话，这决定了插件入口与命令边界。
2. `acp/README.md`
   再看通用 ACP 协议的初始化、session、prompt turn、tool call 与 permission 语义，明确 client/server 分工。
3. `opencode/README.md`
   最后看 OpenCode 作为 ACP Server 的具体支持面和限制，确认本项目为何采用本地 `stdio` 链路。

## 文档地图

- `astrbot/README.md`: AstrBot 插件开发参考，聚焦 `main.py`、`_conf_schema.json`、消息发送、会话控制、存储与 AI 能力。
- `acp/README.md`: ACP 协议参考，聚焦 `initialize`、`session/new`、`session/load`、`session/prompt`、`session/update`、`session/request_permission` 等核心流程。
- `opencode/README.md`: OpenCode ACP Server 参考，聚焦 `opencode acp`、`stdio`、支持范围、已知限制以及与本仓库的关系。

## 使用原则

- 官方原文优先，仓库整理稿只做摘要与导航。
- 仓库内文档不替代规范本身，涉及细节约束时回到官方页面确认。
- 如果后续实现与官方文档有偏差，优先更新这里的导航和“本仓库相关点”，不要把这里扩写成镜像站。
