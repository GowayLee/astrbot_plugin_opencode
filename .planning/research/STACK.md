# Technology Stack

**Project:** AstrBot-ACP 配置与交互重构
**Researched:** 2026-03-29

## Recommended Stack

这次里程碑不是重做插件，而是在现有 AstrBot ACP 插件上，把“能跑”整理成“像产品”。因此推荐栈要遵守两个原则：

1. **继续站在 AstrBot 插件 + 本地 `opencode acp` 上迭代**，不要引入第二套宿主或第二条传输链路。
2. **把复杂度放进运行时内部，不放进配置面板**。管理员配置的是“插件产品”，不是 ACP 协议本身。

### Core Framework

| Technology                    | Version              | Purpose                                     | Why                                                                                                                                                                                  | Confidence                                                                                            |
| ----------------------------- | -------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- | ---- |
| Python                        | 3.11+                | 插件运行时、ACP client core                 | 2025 的 Python agent/协议适配实现里，`asyncio` 已经足够成熟，`TaskGroup`、更稳定的 subprocess/stream 处理也更适合长连接式 stdio JSON-RPC。没必要为本地 ACP 再引入 Node sidecar。     | MEDIUM                                                                                                |
| AstrBot 插件 API              | 宿主当前 v4.x 兼容面 | 命令入口、LLM tool 暴露、配置注入、会话等待 | 当前宿主能力已经覆盖本里程碑要的东西：`_conf_schema.json` 做管理面板，`filter.command` 做 slash-command，`session_waiter` 做权限确认/追问。继续沿用最稳。                            | HIGH                                                                                                  |
| OpenCode CLI (`opencode acp`) | >= 1.1.1             | 本地 ACP agent backend                      | OpenCode 官方已把 ACP 作为一等入口，且明确通过 `opencode acp` 以 **JSON-RPC over stdio** 运行；同时其权限模型已收敛到 `permission`，这和当前“高层开关 + 协议内 permission”方向一致。 | HIGH                                                                                                  |
| ACP 协议                      | Protocol v1          | Agent-client 标准语义层                     | 当前标准流程已经很明确：`initialize -> session/new                                                                                                                                   | load -> session/prompt`，并且 `configOptions`已取代`modes` 成为优先方案。插件应该围绕这个稳定面建模。 | HIGH |

### State / Persistence

| Technology                                      | Version          | Purpose                                                      | Why                                                                                                                                                              | Confidence |
| ----------------------------------------------- | ---------------- | ------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| AstrBot `data/config/...` + `_conf_schema.json` | 宿主内建         | 管理员初始化配置                                             | 这是 AstrBot 官方标准配置面。适合保留少量高层项：`acp_command`、`acp_args`、`startup_timeout`、`default_workdir`、`allow_file_write`。不该继续暴露协议字段集合。 | HIGH       |
| 插件 data 目录下的 JSON 持久化                  | 当前项目现有模式 | sender 级会话状态、目录历史、轻量缓存                        | 本项目是单插件、本地子进程中介，不需要引入数据库。会话状态规模小、结构清晰、可迁移，JSON 足够，而且更容易和现有 `core/storage.py`、`core/session.py` 接起来。    | HIGH       |
| 进程内 session registry                         | 运行时           | 维护 sender -> ACP session / subprocess / pending permission | ACP 是连接态协议；权限请求、流式 update、prompt cancel 都需要活跃内存态。不要试图只靠磁盘配置回放运行中状态。                                                    | HIGH       |

### Infrastructure

| Technology                                                      | Version        | Purpose                                         | Why                                                                                                                                                             | Confidence |
| --------------------------------------------------------------- | -------------- | ----------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| `asyncio.create_subprocess_exec` + 行分隔 JSON-RPC              | Python stdlib  | 本地 stdio ACP transport                        | ACP 官方 transports 文档明确推荐 stdio；OpenCode 官方 ACP 接入文档也明确是子进程 + stdio。这里应直接用标准库实现，不要再包一层 HTTP/WebSocket。                 | HIGH       |
| `stderr` 独立日志采集                                           | Python stdlib  | 诊断 OpenCode 子进程问题                        | ACP 规定 agent 可向 `stderr` 写日志、不得污染 `stdout`。因此 `stdout` 必须只进协议解析器，`stderr` 走日志/调试通道，不能混用。                                  | HIGH       |
| 单独的输出适配层（Direct Chat Presenter / Tool Result Adapter） | 项目内实现模式 | 分离 slash-command 与上层 Agent tool 的结果归属 | 这是本里程碑最重要的产品语义：**直控命令**应该尽量呈现 Coding Agent 原生体验；**tool 调用**应该把结构化结果优先返回给上层 Agent，而不是插件自己直接向用户刷屏。 | HIGH       |

### Supporting Libraries

| Library                                | Version  | Purpose                                                              | When to Use                                                                                                                          | Confidence |
| -------------------------------------- | -------- | -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ---------- |
| Pydantic                               | 2.x      | ACP JSON-RPC envelope、session update、permission request 的边界校验 | 仅用于 **ACP 边界层和内部规范化事件**，避免全项目 dict 乱飞、字段拼写错误和协议升级时静默坏掉。不要把它扩散到 AstrBot 全部业务对象。 | MEDIUM     |
| `typing` / `TypedDict` / `dataclasses` | stdlib   | 内部状态对象、轻量 DTO                                               | 如果不想增加依赖，最少也要把“原始 ACP 消息”和“插件内部事件”分类型。适合 manager 层之间的数据契约。                                   | HIGH       |
| AstrBot `session_waiter`               | 宿主内建 | 协议内 permission request 的文本确认                                 | ACP 的 `session/request_permission` 是一等能力；AstrBot 已有等待式会话控制。这里直接复用，比再造按钮状态机更稳，也更跨平台。         | HIGH       |

## Recommended Implementation Approach

### 1. 保持“本地 stdio ACP + Python 异步 client core”

推荐实现：

- 一个 **ACP Transport**：只负责拉起 `opencode acp`、读写 JSON-RPC、处理请求 ID、分流 `stdout/stderr`
- 一个 **ACP Session Client**：只负责 `initialize`、`session/new|load`、`session/prompt`、`session/set_config_option`、`session/cancel`
- 一个 **Session Runtime Store**：按 sender 保存当前 workdir、ACP session id、进程句柄、待处理 permission、当前 configOptions 快照

这样做的原因不是“更优雅”，而是 ACP 本身已经把 transport、session、prompt turn 分层了，插件如果继续把它们揉进 `main.py`，后面做配置收缩和输出分流会越来越难。

### 2. 配置面板只保留“管理员初始化项”，不要暴露协议原语

推荐公开配置：

- `acp_command`：默认 `opencode`
- `acp_args`：默认 `["acp"]`
- `startup_timeout_seconds`
- `default_workdir`
- `allow_file_write`
- （可选）`permission_reply_timeout_seconds`

推荐下沉到代码内部或隐藏迁移项：

- `backend_type`
- `acp_client_capabilities`
- 默认 `mode` / 默认 `configOptions` 的原始对象
- tool 元描述细节
- 摘要/TXT/长图这类细粒度输出编排开关

原因：

- ACP 官方已经把 **clientCapabilities 视为初始化协商信息**，它应该由插件根据能力自动生成，而不是让管理员手填。
- ACP 官方已经把 **`configOptions` 视为 session 内动态选择器**，它更像运行时状态，不像静态面板配置。
- 本里程碑目标是“低配置负担”，不是“把 ACP 全量暴露到 WebUI”。

### 3. 输出路径必须一开始就分成两条

**A. Slash-command 直控路径**

- 输入：用户命令/消息
- 输出：面向用户的直接渲染
- 呈现内容：计划、进度、工具执行摘要、最终答复、必要确认

**B. 上层 Agent tool 路径**

- 输入：AstrBot 上层 Agent 通过 tool 调用
- 输出：结构化结果对象返回给上层 Agent
- 呈现内容：默认不由插件直接推送最终消息；只在异常/权限/宿主要求时做最小提示

建议内部统一成一种规范化事件流，例如：

`ACP update -> NormalizedEvent -> Presenter / ToolAdapter`

这样后面无论要折叠 tool_call、压缩 plan、还是只把最终 summary 交给上层 Agent，都不会再把输出逻辑和协议解析绑死。

### 4. 运行时优先消费 `configOptions`，不要再围绕 `modes` 设计 UX

ACP 官方已明确：**`configOptions` 是优先方案，`modes` 将被移除**。因此：

- slash-command 若要支持“模式/模型/思考强度”切换，应读 `configOptions`
- 管理面板不应继续绑定某个 backend 私有 `mode` 字段
- 内部状态应该保存完整 `configOptions` 快照，而不是单独散存 `mode`

这能避免后面协议升级时再做一轮迁移。

### 5. 权限语义采用“双层门控”，但只保留一套对外配置

推荐模式：

1. **插件前置门**：管理员开关，例如 `allow_file_write`
2. **ACP 协议内门**：`session/request_permission`

也就是：

- 面板只暴露少数高层策略
- 实际逐次批准依然遵守 OpenCode/ACP 的运行时 permission 语义

这样既不会回到“全靠关键词猜危险操作”，也不会逼管理员配置一整套底层 permission map。

## Alternatives Considered

| Category      | Recommended                       | Alternative                                                    | Why Not                                                                                |
| ------------- | --------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| ACP transport | 本地 stdio subprocess             | Remote HTTP / WebSocket ACP                                    | ACP 官方 HTTP 仍处 draft；本里程碑也明确保持本地 `stdio`。现在引入远程传输只会扩大面。 |
| 协议建模      | typed ACP client core             | 在 manager 间直接传裸 dict                                     | 初期快，后期最容易把 permission、tool updates、configOptions 搞乱。                    |
| 配置模型      | 少量高层面板项                    | 面板暴露 `clientCapabilities` / `configOptions` / backend 字段 | 违背产品化配置目标，也会把运行时协商信息错误固化成静态配置。                           |
| 输出策略      | 命令直出 + tool 回传上层 Agent    | tool 也直接推消息给终端用户                                    | 会破坏“上层 Agent 调下层 Coding Agent”的责任边界，用户也会看到双重人格式输出。         |
| 状态存储      | JSON + 进程内 registry            | Redis / SQLite / 消息队列                                      | 这是插件中介层，不是高并发分布式服务；引入后维护成本高于收益。                         |
| 权限模型      | 高层开关 + ACP permission request | 重新发明第二套完整权限系统                                     | 配置会爆炸，而且容易和 OpenCode 官方 permission 语义冲突。                             |

## What NOT to Introduce

1. **不要引入新的远程 backend 抽象**：这轮不是为 multi-backend 平台设计，先把本地 stdio ACP 做稳。
2. **不要把 `_conf_schema.json` 变成 ACP 调试面板**：协议协商信息应由代码生成，不应由管理员维护。
3. **不要让 tool 调用直接复用 slash-command 输出管线**：两者可共享执行内核，但不能共享“最终发给谁”的语义。
4. **不要把 `modes` 当长期接口继续扩展**：新交互和状态都应围绕 `configOptions`。
5. **不要引入数据库、队列或事件总线中间件**：当前规模下这是纯增复杂度。
6. **不要引入前端按钮依赖型 permission UX**：AstrBot 多平台环境里，纯文本选项 + `session_waiter` 更稳。

## Installation

```bash
# Core (only if新增协议边界校验)
pip install "pydantic>=2.8,<3"

# No extra transport dependency needed
# Keep subprocess + asyncio in stdlib
```

## Sources

- ACP 官方协议仓库（HIGH）: https://github.com/agentclientprotocol/agent-client-protocol
- OpenCode ACP Support（HIGH, last updated Mar 29 2026）: https://opencode.ai/docs/acp/
- OpenCode Permissions（HIGH, last updated Mar 29 2026）: https://opencode.ai/docs/permissions/
- OpenCode Agents（HIGH, last updated Mar 29 2026）: https://opencode.ai/docs/agents/
- AstrBot 插件配置官方文档源码（MEDIUM）: https://github.com/AstrBotDevs/AstrBot/blob/a40a5fe18c6bd7eeb7d0373e2203150a844a51ef/docs/zh/dev/star/guides/plugin-config.md
- AstrBot 会话控制官方文档源码（MEDIUM）: https://github.com/AstrBotDevs/AstrBot/blob/a40a5fe18c6bd7eeb7d0373e2203150a844a51ef/docs/zh/dev/star/guides/session-control.md
- 本仓库内官方快照参考（HIGH）:
  - `docs/references/official/acp/initialization.mdx`
  - `docs/references/official/acp/session-setup.mdx`
  - `docs/references/official/acp/prompt-turn.mdx`
  - `docs/references/official/acp/session-config-options.mdx`
  - `docs/references/official/acp/transports.mdx`
  - `docs/references/official/opencode/acp.mdx`
