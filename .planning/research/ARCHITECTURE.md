# Architecture Research

**Domain:** 聊天原生 ACP Coding-Agent 插件集成（AstrBot ↔ OpenCode ACP）
**Researched:** 2026-03-29
**Confidence:** HIGH

## Standard Architecture

### System Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│                          Ingress Layer                              │
├──────────────────────────────────────────────────────────────────────┤
│  SlashCommandRouter        ToolFacade         SessionWaiterAdapter   │
│  (/oc, /oc-new...)         (call_opencode)   (权限确认/后续回复)      │
└──────────────┬──────────────────────┬──────────────────────┬────────┘
               │                      │                      │
               ├──────────────┬───────┴──────────────┬──────┤
               │              │                      │      │
┌──────────────▼────────────────────────────────────────────▼─────────┐
│                        Application Layer                             │
├──────────────────────────────────────────────────────────────────────┤
│ PromptOrchestrator                                                   │
│ - 统一 prompt turn 执行                                               │
│ - 统一会话确保 / session new|load / prompt / permission response     │
│ - 只产出标准化 RunResult / StreamEvent，不决定“发给谁、怎么发”         │
│                                                                      │
│ PolicyService         SessionService        CommandService           │
│ - 权限/确认策略        - sender↔ACP状态      - 命令级参数与用例封装     │
└──────────────┬──────────────────────────────────────────────┬─────────┘
               │                                              │
┌──────────────▼──────────────────────────────────────────────▼─────────┐
│                       Presentation Layer                              │
├──────────────────────────────────────────────────────────────────────┤
│ ChatOutputPresenter              ToolResultPresenter                 │
│ - 直出聊天消息计划                - 返回给上层 Agent 的结构化结果       │
│ - 进度/长文/TXT/长图              - summary/artifacts/state/actions   │
│ - permission 提示文案             - 不主动推送用户消息                 │
└──────────────┬──────────────────────────────────────────────┬─────────┘
               │                                              │
┌──────────────▼──────────────────────────────────────────────▼─────────┐
│                         Infrastructure Layer                          │
├──────────────────────────────────────────────────────────────────────┤
│ ACP Executor/Adapter │ Session Store │ Storage │ Config │ Security   │
│ OpenCode stdio ACP   │ per-sender    │ history │ schema │ guards     │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component             | Responsibility                                                             | Typical Implementation                                 |
| --------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------ | ------------------------------ |
| `SlashCommandRouter`  | 处理 `/oc`、`/oc-new`、`/oc-session` 等聊天入口，做参数解析与 event 绑定   | 保留在 `main.py` 的 AstrBot decorators，但只做薄路由   |
| `ToolFacade`          | 暴露 `call_opencode` 给上层 Agent，接收 tool 参数并返回结构化结果          | 单独的 tool handler，禁止直接 `send_message`           |
| `PromptOrchestrator`  | 统一执行 ACP prompt turn、流式事件消费、permission round-trip、异常归一化  | 新增 `core/orchestrator.py` 或 `core/runtime.py`       |
| `PolicyService`       | 统一 admin gate、 destructive 检测、 tool/command 两类审批策略             | 基于 `core/security.py` 扩展“调用场景”参数             |
| `SessionService`      | 管理 sender 会话、backend session、默认 agent/mode/config、待决 permission | 以 `core/session.py` 为 source of truth                |
| `ChatOutputPresenter` | 把标准化事件/result 转成 AstrBot chat send plan                            | 从 `core/output.py` 抽出 chat profile                  |
| `ToolResultPresenter` | 把同一批事件/result 转成上层 Agent 可消费的 tool payload                   | 新增 `core/tool_output.py` 或 `core/presenters.py`     |
| `ACP Executor`        | `initialize → session/new                                                  | load → session/prompt → request_permission` 的协议执行 | 继续由 `core/executor.py` 持有 |
| `Storage/Config`      | 工作目录历史、临时文件、插件配置 schema                                    | `core/storage.py` + `_conf_schema.json`                |

## Recommended Project Structure

```text
main.py                         # AstrBot 注册与薄路由
core/
├── ingress/
│   ├── commands.py             # /oc* 命令处理器
│   ├── tools.py                # llm_tool 处理器
│   └── approvals.py            # session_waiter 适配层
├── application/
│   ├── prompt_orchestrator.py  # 统一 prompt turn 编排
│   ├── command_service.py      # 命令用例
│   └── policy_service.py       # 调用场景 + 安全策略
├── presentation/
│   ├── chat_presenter.py       # slash-command 输出语义
│   ├── tool_presenter.py       # upper-agent tool 输出语义
│   └── output_models.py        # RunResult / StreamEvent / ToolResult
├── executor.py                 # ACP transport + protocol dispatch
├── session.py                  # sender/backend 会话状态
├── security.py                 # 安全策略底座
├── input.py                    # 消息/附件预处理
├── output.py                   # 兼容层，逐步收敛到 presentation/
└── storage.py                  # 历史与清理
```

### Structure Rationale

- **`ingress/`:** 按 AstrBot 宿主入口拆分，而不是按协议拆分；这样能先减肥 `main.py`，不必先动执行内核。
- **`application/`:** 放共享业务编排，确保 slash-command 与 tool 复用同一条 ACP 执行逻辑。
- **`presentation/`:** 关键分界。聊天直出与 tool 返回语义不同，但都消费同一个标准化执行结果。
- **保留 `executor.py` / `session.py` / `security.py`:** 当前边界基本合理，应复用而不是重写。

## Architectural Patterns

### Pattern 1: Shared Execution Core + Dual Presenter

**What:** 输入入口不同，但都调用同一个 `PromptOrchestrator.run()`；差异只体现在 presenter。
**When to use:** 同一后端能力要同时服务“直接用户交互”和“上层 Agent 工具调用”时。
**Trade-offs:** 需要先定义稳定的中间结果模型；但能避免把执行逻辑复制到 command/tool 两边。

**Example:**

```python
result = await orchestrator.run(
    channel="tool",  # 或 "chat"
    event=event,
    session=session,
    prompt=final_prompt,
)

if channel == "chat":
    return await chat_presenter.present(result, event, session)
return await tool_presenter.present(result, session)
```

### Pattern 2: Invocation Context as First-Class Data

**What:** 把 `chat` / `tool` / `approval_resume` 变成显式上下文，而不是到处写 if/else。
**When to use:** 权限、输出、超时、可交互性会随入口变化时。
**Trade-offs:** 模型会稍多一点；但边界清晰，后续扩展新的入口不容易污染主流程。

**Example:**

```python
@dataclass
class InvocationContext:
    channel: Literal["chat", "tool"]
    interactive: bool
    may_push_user_messages: bool
    approval_mode: Literal["waiter", "return_action"]
```

### Pattern 3: Permission as Interrupt, Not Side Effect

**What:** 把 ACP `session/request_permission` 视为一次可恢复中断；chat 流程用 `session_waiter`，tool 流程返回 `needs_user_action` 给上层 Agent。
**When to use:** ACP 后端会在 prompt turn 中间请求授权，且两种入口的交互能力不同。
**Trade-offs:** tool 流程会变成两段式调用；但这是符合 ACP 和上层 Agent 语义的，不会再出现 tool handler 偷偷后台发消息。

**Example:**

```python
if event.type == "permission_requested":
    if ctx.channel == "chat":
        choice = await approval_waiter.ask_user(event, permission)
        return await orchestrator.resume_permission(session, choice)
    return ToolResult(
        status="needs_user_action",
        action={"type": "permission", "options": permission.options},
    )
```

## Data Flow

### Request Flow

#### 1. Slash-command direct output

```text
用户 /oc
    ↓
SlashCommandRouter
    ↓
InputProcessor + PolicyService
    ↓
PromptOrchestrator
    ↓
CommandExecutor (initialize → session/new|load → session/prompt)
    ↓
ACP runtime events / permission requests / final result
    ↓
ChatOutputPresenter
    ↓
AstrBot message send plan
    ↓
用户直接看到进度、权限确认、最终结果
```

#### 2. Tool-mediated output

```text
上层 Agent 调用 call_opencode
    ↓
ToolFacade
    ↓
InputProcessor + PolicyService
    ↓
PromptOrchestrator
    ↓
CommandExecutor (同一条 ACP 执行链路)
    ↓
ACP runtime events / permission requests / final result
    ↓
ToolResultPresenter
    ↓
结构化 tool payload 返回给上层 Agent
    ↓
上层 Agent 自己组织最终回复给用户
```

### State Management

```text
SessionStore (per sender / per conversation)
    ├── work_dir
    ├── backend_session_id
    ├── default_agent / mode / config
    ├── pending_permission
    └── prompt_running

Ingress Handlers
    ↓ read/write
PromptOrchestrator
    ↓ sync state
CommandExecutor / Presenters
```

### Key Data Flows

1. **命令直出流:** runtime event 先变成聊天进度，再进入长文/TXT/长图等输出积木。
2. **工具回传流:** runtime event 被压缩成 `summary + artifacts + state + next_action`，绝不主动 `context.send_message()`。
3. **授权恢复流:** `pending_permission` 必须绑定在 `SessionService`，而不是绑定在某个 handler 局部闭包里。

## Semantics Split Recommendation

### Slash-command should be chat-native

- 应显示执行中状态、工具进度、权限确认、最终输出。
- 可以继续使用 `session_waiter` 承接授权与后续回复。
- 输出目标是“让用户觉得自己正在直接操控 Coding Agent”。

### Tool flow should be agent-native

- 默认不主动向聊天会话推送结果。
- 返回结构应至少包含：

| Field           | Purpose                                      |
| --------------- | -------------------------------------------- |
| `status`        | `completed` / `failed` / `needs_user_action` |
| `summary`       | 给上层 Agent 的简要概括                      |
| `final_text`    | 可选原始文本                                 |
| `events`        | 可选中间事件摘要                             |
| `artifacts`     | TXT、文件、路径、diff 等                     |
| `session_state` | `backend_session_id`、agent、mode、work_dir  |
| `action`        | 权限确认、继续执行、重试等下一步动作         |

推荐结果模型：

```python
@dataclass
class ToolResult:
    status: str
    summary: str
    final_text: str = ""
    events: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    session_state: dict = field(default_factory=dict)
    action: dict | None = None
```

## Brownfield Migration Strategy

### Suggested Build Order

1. **先抽中间编排层（最高优先级）**
   - 从 `main.py::_run_oc_prompt` 提炼 `PromptOrchestrator`。
   - 目标：保留现有命令行为不变，但 command/tool 都走同一核心编排。

2. **再抽双 presenter**
   - 把当前 `core/output.py` 继续作为 chat presenter 底座。
   - 新增 tool presenter，先做到“返回结构化结果，不主动推送”。

3. **最后拆 ingress**
   - 将 `/oc*` 命令与 `call_opencode_tool` 从 `main.py` 拆到 `ingress/commands.py`、`ingress/tools.py`。
   - `main.py` 只保留 AstrBot 注册、依赖装配、回调注入。

### Safe Migration Steps

| Step | Change                                                         | Why safe                           |
| ---- | -------------------------------------------------------------- | ---------------------------------- |
| 1    | 新增 `RunContext` / `RunResult` / `ToolResult` 模型            | 先加抽象，不改外部行为             |
| 2    | 提炼 `_run_oc_prompt` 到 orchestrator，`oc_handler` 仅改调用点 | slash-command 回归风险最小         |
| 3    | 让 `call_opencode_tool` 改为消费 orchestrator + tool presenter | 修正当前“后台主动发消息”的错误语义 |
| 4    | 抽离命令处理器文件                                             | 主要是代码组织调整，行为变化小     |
| 5    | 统一 permission 策略接口                                       | 避免 chat/tool 各自维护确认逻辑    |

### What not to do

- 不要先重写 `executor.py`。当前 ACP 执行链路已经稳定，问题主要在入口和输出语义。
- 不要让 tool 流程继续走后台 `context.send_message()`；这会破坏上层 Agent 的主导权。
- 不要把 slash-command 和 tool 拆成两套执行器；应该是一套执行内核、两套呈现语义。

## Scaling Considerations

| Scale        | Architecture Adjustments                                                 |
| ------------ | ------------------------------------------------------------------------ |
| 0-1k 用户    | 单插件单进程足够，重点是清理 `main.py`、稳定会话状态                     |
| 1k-100k 用户 | 优先优化会话生命周期、超时取消、临时文件清理、长输出限流                 |
| 100k+ 用户   | 再考虑把 session storage 和 job execution 外移；当前阶段没必要先拆分服务 |

### Scaling Priorities

1. **First bottleneck:** 长任务期间的会话与权限状态一致性，而不是 CPU。
2. **Second bottleneck:** 输出风控与消息分片，而不是 ACP transport 本身。

## Anti-Patterns

### Anti-Pattern 1: Tool handler 主动替上层 Agent 回复用户

**What people do:** 在 `llm_tool` 内直接 `event.send()` 或后台 `context.send_message()`。
**Why it's wrong:** 打乱上层 Agent 的规划-调用-总结链路，用户会看到“双重说话人”。
**Do this instead:** tool 只返回结构化结果；只有 chat 入口负责直接对用户发消息。

### Anti-Pattern 2: 在入口层混合执行、权限、渲染

**What people do:** 把 prompt 执行、permission wait、output plan 全塞进 `main.py`。
**Why it's wrong:** Brownfield 项目会迅速失控，任何改动都牵一发而动全身。
**Do this instead:** 入口层只做路由，编排在 orchestrator，语义在 presenters。

### Anti-Pattern 3: 用 sender state 之外的临时闭包保存中断状态

**What people do:** 在命令或工具 handler 局部变量里记 `pending_permission`。
**Why it's wrong:** 长任务、超时、重入、恢复执行时很容易丢状态。
**Do this instead:** 一律把可恢复状态落到 `SessionService/OpenCodeSession`。

## Integration Points

### External Services

| Service                      | Integration Pattern                        | Notes                                   |
| ---------------------------- | ------------------------------------------ | --------------------------------------- |
| AstrBot command/event system | decorator + `AstrMessageEvent`             | 入口层应薄化，继续遵守宿主模型          |
| AstrBot session waiter       | `session_waiter` for interactive approvals | 只适合 chat 流程；tool 流程不应强依赖它 |
| OpenCode ACP                 | `opencode acp` over stdio JSON-RPC         | HIGH confidence；官方明确支持 stdio ACP |

### Internal Boundaries

| Boundary                       | Communication                            | Notes                           |
| ------------------------------ | ---------------------------------------- | ------------------------------- |
| ingress ↔ application          | 直接方法调用 + typed context/result      | 不传 AstrBot 细节到 executor    |
| application ↔ executor         | typed request/result                     | executor 只管协议，不管聊天语义 |
| application ↔ presentation     | normalized runtime events + final result | 这里决定 chat/tool 语义分叉     |
| session/security ↔ application | direct service API                       | 两者都是跨入口共享能力          |

## Sources

- `.planning/PROJECT.md` — 项目目标、约束与现状（HIGH）
- `main.py` — 当前 `/_run_oc_prompt`、`/oc`、`call_opencode_tool` 实现（HIGH）
- `core/session.py` / `core/executor.py` / `core/output.py` — 现有边界与可复用内核（HIGH）
- `docs/references/official/opencode/acp.mdx` — OpenCode 官方 ACP 支持与能力范围（HIGH）
- `docs/references/official/acp/session-setup.mdx` — ACP `session/new|load` 与 `cwd` 语义（HIGH）
- `docs/references/official/acp/prompt-turn.mdx` — prompt turn、stream、permission 生命周期（HIGH）
- `docs/references/official/acp/tool-calls.mdx` — tool call 状态与 permission request 机制（HIGH）
- `docs/references/official/astrbot/listen-message-event.md` — AstrBot 指令/事件入口模型（HIGH）
- `docs/references/official/astrbot/session-control.md` — AstrBot 会话等待器与交互式确认（HIGH）
- `docs/references/official/astrbot/plugin-config.md` — `_conf_schema.json` 配置承接能力（HIGH）

---

_Architecture research for: AstrBot-ACP 配置与交互重构_
_Researched: 2026-03-29_
