## 文档定位

这是一份面向本仓库开发的 ACP 导航与摘要，帮助后续实现者快速确认协议主流程、对象边界和 client 侧职责。

它不是 ACP 规范镜像；涉及字段级别含义、消息结构和能力协商细节时，应回到官方页面确认。

## 官方来源

ACP 官方协议入口与相关页面：

- 总索引: <https://agentclientprotocol.com/llms.txt>
- 协议概览: <https://agentclientprotocol.com/protocol/overview>
- 初始化: <https://agentclientprotocol.com/protocol/initialization>
- Session 建立: <https://agentclientprotocol.com/protocol/session-setup>
- Prompt Turn: <https://agentclientprotocol.com/protocol/prompt-turn>
- Tool Calls: <https://agentclientprotocol.com/protocol/tool-calls>
- File System: <https://agentclientprotocol.com/protocol/file-system>
- Terminals: <https://agentclientprotocol.com/protocol/terminals>
- Content: <https://agentclientprotocol.com/protocol/content>
- Session Modes: <https://agentclientprotocol.com/protocol/session-modes>
- Slash Commands: <https://agentclientprotocol.com/protocol/slash-commands>
- Agent Plan: <https://agentclientprotocol.com/protocol/agent-plan>
- Schema: <https://agentclientprotocol.com/protocol/schema>

## 协议主流程

ACP 的主时序可以先按下面的骨架理解：

`initialize -> session/new | session/load -> session/prompt -> session/update / session/request_permission / session/cancel`

对应到本仓库常见开发场景：

- `initialize`: client 先声明能力与 clientInfo，协商协议能力。
- `session/new`: 创建新 session，并在 payload 中设置工作目录与初始上下文。
- `session/load`: 在服务端支持 `loadSession` 的前提下恢复既有 session。
- `session/prompt`: 把用户任务送入当前 session，驱动一次 prompt turn。
- `session/update`: 服务端以通知形式持续回传执行状态、工具进度、diff、terminal 输出等信息。
- `session/request_permission`: 当执行需要宿主确认时，由 server 发起 permission 请求，client 再回传决策。
- `session/cancel`: 中止当前 session 中正在运行的任务。

## 对本仓库最关键的对象与边界

### 1. 初始化与能力协商

- `initialize` 不是可选装饰，它决定了 server 是否知道 client 支持哪些能力。
- 本仓库在 `core/acp_client.py` 中维护 `initialize` 请求、请求 ID 跟踪和通知分发。
- 若后续依赖 `loadSession` 或更多 client capability，必须先确认能力协商结果。

### 2. Session 边界

- `cwd` 是 session 级边界，不是单条 prompt 的随意附带字段。
- 路径应使用绝对路径，这对本地文件访问和权限边界都很关键。
- `session/new` 与 `session/load` 的区别必须明确：前者新建上下文，后者尝试恢复已有上下文。

### 3. Prompt Turn 与事件回传

- `session/prompt` 用来发起一次任务轮次。
- 真正的过程感通常来自后续 `session/update` 通知，而不是一次同步响应。
- 后续实现若要改进执行中反馈，应优先基于 update 事件建模，而不是发明协议外旁路。

### 4. Permission 与 Tool Call

- `session/request_permission` 是 server 向 client 请求用户或宿主确认的标准机制。
- permission 决策属于 client 侧职责，不能假定 server 自己知道宿主的安全策略。
- `tool-calls` 页面定义了 `tool_call`、状态更新、diff、terminal、content 等表达方式，是后续工具回传设计的关键依据。

### 5. 结构化对象与 schema

- `content`、`schema`、`file-system`、`terminals`、`slash-commands` 等页面共同定义了 ACP 中可交换对象的基本形态。
- 如果后续需要把 tool 结果结构化回传给上层 Agent，应先在这些页面里确认字段模型和状态枚举。

## 与本仓库实现的对应观察

- `core/acp_client.py` 是本仓库的 ACP client 核心，负责 `initialize`、`session/new`、`session/load`、`session/prompt`、`session/cancel` 等请求封装。
- `core/acp_adapter.py` 负责把 OpenCode 的 ACP payload 映射成插件内部可消费的对象，也体现了 `/undo`、`/redo` 之类命令的支持状态整理方式。
- `core/acp_models.py` 记录了 `ACPSessionState`、permission request、command、config option 等共享模型。
- 这些实现文件只是当前仓库的适配参考，不是规范本身；当实现与官方文档不一致时，应以官方协议为准。
