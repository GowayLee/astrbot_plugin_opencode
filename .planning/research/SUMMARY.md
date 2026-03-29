# Project Research Summary

**Project:** AstrBot-ACP 配置与交互重构
**Domain:** 聊天原生 ACP Coding Agent 桥接插件重构
**Researched:** 2026-03-29
**Confidence:** HIGH

## Executive Summary

这是一个 brownfield 的 AstrBot 插件产品化重构，不是重做执行内核。研究结论非常一致：专家做这类产品时，不会再扩展第二套后端或传输层，而是保留本地 `opencode acp` + stdio JSON-RPC 作为唯一执行链路，把主要精力放在“配置收敛、会话语义、权限中介、输出分流”四件事上。目标不是把 ACP 暴露得更完整，而是把它包装成一个管理员能配置、用户能直接使用、上层 Agent 能稳定编排的插件产品。

推荐路线也很明确：一套共享执行核心，分别服务 slash-command 直控路径和 tool 回传路径；配置面板只保留少量高层初始化项；运行时状态围绕 `configOptions`、ACP session 和 pending permission 建模；权限采用“宿主高层开关 + ACP 运行时确认”的双层门控。这样既能保住 Coding Agent 的过程感，又能避免当前 tool 调用直接刷屏、配置项过度协议化、会话状态串线这些核心问题。

主要风险同样集中且可控：第一，若把“简化配置”做成“隐藏关键语义”，后续会变成不可维护的黑盒；第二，若 slash-command 与 tool 输出不彻底分流，用户会看到双重说话人；第三，若会话状态和权限中断不先建模，重构 `main.py` 时极易回归。缓解方式不是先大拆代码，而是先锁定运行时契约、结果模型、阶段化迁移顺序，再做渐进式重构与手工回归。

## Key Findings

### Recommended Stack

这轮不是换技术栈，而是让现有栈的边界更清晰。最稳的方案是继续使用 Python 3.11+、AstrBot v4.x 插件能力、OpenCode CLI `opencode acp` 和 ACP Protocol v1；其中 transport 维持本地 stdio，状态持久化继续用插件 data 目录下的 JSON，运行中的 sender/session/permission 状态保留在内存 registry。

实现上最重要的不是新增依赖，而是补齐类型化边界：至少要把 ACP 原始消息、标准化事件、工具返回结果分开建模。Pydantic 2.x 只建议用于 ACP 边界校验，不建议扩散到整个插件业务层。

**Core technologies:**

- Python 3.11+：插件运行时与 ACP client core — `asyncio`、subprocess、长任务处理已足够成熟。
- AstrBot 插件 API（v4.x 兼容面）：命令入口、配置注入、会话等待 — 宿主已覆盖本里程碑所需能力。
- OpenCode CLI `opencode acp` >= 1.1.1：本地 ACP backend — 官方已将 ACP 作为一等入口，权限语义也已稳定。
- ACP Protocol v1：标准语义层 — `initialize / session / prompt / permission / configOptions` 路径明确，适合围绕其建模。
- JSON 持久化 + 进程内 session registry：轻量状态管理 — 当前插件规模下比数据库或队列更合适。

### Expected Features

研究显示，v1 必须优先解决“像产品一样可用”而不是“把所有能力都露出来”。管理员侧要收敛到高层初始化配置；用户侧要有主命令、会话延续、异步进度、文本化审批；上层 Agent 侧要拿到结构化结果而不是前台刷屏。

**Must have (table stakes):**

- 高层初始化配置面板 — 只保留启动命令、启动参数、超时、默认工作目录、写入开关等产品级配置。
- 主命令 + 少量生命周期命令 — `/oc` 为主入口，辅以 `new/end/session` 这类显式会话控制。
- 即时确认 + 异步进度回传 + 输出分层 — 先回应“已开始”，再回传关键状态，长输出转摘要/TXT/长文载体。
- 文本化权限审批 + 安全默认值 — 在 IM 环境里以纯文本承接 `request_permission`，默认 fail closed。
- tool 模式结构化返回给上层 Agent — 返回 summary / artifacts / state / action，不主动对用户刷正文。
- 会话连续性与显式重置/切换 — 让聊天里的 Coding Agent 真正具备 session 语义。

**Should have (competitive):**

- slash-command 与 tool 模式双语义产品化 — 同一执行内核，两套清晰输出契约。
- 进度折叠与结果压缩 — 保留过程感，但避免群聊刷屏。
- 任务 steering — 在会话仍存活时补充说明，而不是每次取消重来。
- 管理员预设模板 — 如只读审查模式、写入需确认模式。
- 产物导向回复 — 根据场景自动交付摘要、文件、TXT、长图等可消费结果。

**Defer (v2+):**

- 多仓库/多工作区高级路由 — 当前默认工作目录 + 显式切换已够用。
- 富交互按钮式审批 — 宿主平台差异太大，先用纯文本方案兜底。
- 高级 expert-mode 配置面板 — 应在高层配置验证稳定后再考虑开放。

### Architecture Approach

最优架构不是“命令一套、工具一套”，而是 Shared Execution Core + Dual Presenter：所有入口统一进入 `PromptOrchestrator`，由它负责 session/new|load、prompt turn、permission round-trip、异常归一化，再交给 chat presenter 或 tool presenter 分别决定如何呈现。这样既能复用当前 `executor.py` / `session.py` / `security.py` 的成熟内核，又能修正当前入口层、执行层、渲染层混在一起的问题。

**Major components:**

1. `PromptOrchestrator` — 统一 prompt turn 执行、流式事件消费、权限恢复与结果归一化。
2. `SessionService` / SessionStore — 管理 sender 范围状态、ACP session 绑定、pending permission 与默认配置快照。
3. `PolicyService` — 统一 chat/tool 两类入口的安全策略与审批逻辑。
4. `ChatOutputPresenter` — 面向 slash-command 输出进度、确认、摘要与附件计划。
5. `ToolResultPresenter` — 面向上层 Agent 返回结构化 `ToolResult`，默认不主动发消息。
6. `ACP Executor` — 专注 stdio JSON-RPC transport 与 ACP 协议分发，不掺杂聊天语义。

### Critical Pitfalls

**优先规避的不是“代码不够优雅”，而是语义错位。** 研究里最危险的问题集中在配置语义、入口分流、会话状态、安全分层和事件模型五个面上。

1. **把简化配置做成隐藏语义** — 删字段时必须补齐默认工作目录、写入策略、新会话行为等明确运行时契约。
2. **slash-command 与 tool 输出混流** — 从第一阶段起就定义两套结果契约，执行器只产出结构化事件，不直接决定发给谁。
3. **宿主状态与 ACP session 混淆** — 拆开 sender scope、ACP session binding、next-session defaults、pending permission 四类状态。
4. **只做前置安全检查或只信后端 permission** — 采用宿主开关 + 会话级 permission + 后端规则的分层设计，并给每类风险指定唯一主判定层。
5. **把流式事件压扁成最终文本** — 保留最小必要事件集并做折叠展示，而不是直接丢失 plan/tool/progress/permission 语义。

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 0: 行为基线与重构护栏

**Rationale:** 这是无自动化测试的 brownfield 插件；不先锁定行为契约，后续任何重构都高风险。  
**Delivers:** 命令行为清单、手工验证脚本、支持/降级/不支持能力表。  
**Addresses:** 配置迁移与 sane defaults、错误恢复与取消的回归基线。  
**Avoids:** “先大拆 `main.py` 再补验证”、过度承诺与终端完全等价。

### Phase 1: 配置收敛与双入口语义定稿

**Rationale:** 配置与输出契约是后续所有实现的上位约束，必须先定。  
**Delivers:** 精简后的 `_conf_schema.json`、高层初始化配置、slash/tool 两条输出契约、能力边界文案。  
**Addresses:** 高层初始化配置面板、文本化权限审批的入口定义、tool 模式结构化返回的目标契约。  
**Avoids:** 简化配置但隐藏关键语义、slash 与 tool 输出混流、过度承诺 ACP/TUI 等价。

### Phase 2: 执行编排层与会话状态模型重构

**Rationale:** 先统一执行核心和状态边界，再谈 presenter 或 UX 优化，依赖关系最清晰。  
**Delivers:** `PromptOrchestrator`、`RunContext/RunResult`、明确的 session state 分层、`/oc-new` `/oc-end` `/oc-session` 语义收敛。  
**Uses:** Python 3.11+ `asyncio`、ACP Protocol v1、现有 `executor.py` / `session.py`。  
**Implements:** Shared Execution Core、Invocation Context、Permission as Interrupt。  
**Avoids:** 宿主状态与 ACP session 混淆、流式事件被压扁、入口层继续混合执行/渲染/权限。

### Phase 3: 安全模型与权限中介统一

**Rationale:** 只有在状态与执行编排稳定后，才能准确把禁写、外部目录、会话内审批落到唯一主判定层。  
**Delivers:** 宿主高层开关与 ACP permission 的映射策略、统一 permission broker、禁写/超时/拒绝路径一致行为。  
**Addresses:** 安全默认值 + 权限预设、交互式审批文本化承接、上下文边界控制。  
**Avoids:** 双重确认噪音、UI 上显示禁写但运行时未真正阻断、tool 调用绕过宿主安全模型。

### Phase 4: 双 Presenter 落地与聊天体验优化

**Rationale:** 在执行与安全基础稳定后，再做 chat/tool 结果分流和进度折叠，回归面最小。  
**Delivers:** `ChatOutputPresenter`、`ToolResultPresenter`、事件折叠策略、产物导向回复、长输出治理。  
**Addresses:** 即时确认 + 异步进度回传 + 输出分层、tool 模式结构化返回、产物导向回复。  
**Avoids:** tool handler 直接替上层 Agent 发话、每个 update 都刷一条消息、最终文本吞掉全部过程事件。

### Phase 5: 增量增强与验证后扩展

**Rationale:** steering、模板、审计视图都建立在前四阶段稳定之上，不应抢跑。  
**Delivers:** 任务 steering、管理员模板、细粒度审计视图；视验证结果决定是否推进 v2 项。  
**Addresses:** 差异化能力与运营效率提升。  
**Avoids:** 过早做多仓库路由、富交互审批、expert-mode 面板导致复杂度反弹。

### Phase Ordering Rationale

- 先定契约，再抽内核，再统一安全，最后做呈现优化；这是 brownfield 最稳的顺序。
- 配置收敛和输出分流必须先于代码组织调整，否则架构改完仍会保留错误产品语义。
- 会话状态模型是权限中断、任务续接、steering 的共同前置依赖，不能后补。
- chat/tool 共用一套执行核心，但必须后接两套 presenter；这正是 roadmap 的主分组逻辑。
- 所有阶段都应附带手工回归清单，尤其覆盖 `/oc-new`、`/oc-end`、`/oc-session`、tool 调用、权限超时和禁写模式。

### Research Flags

Phases likely needing deeper research during planning:

- **Phase 3：** 需要进一步核对 OpenCode permission 默认值、代理级覆盖与插件高层开关的最终映射细节。
- **Phase 5：** steering、审计视图、多工作区等增强项需要依据真实使用数据决定范围，当前不宜过度设计。

Phases with standard patterns (skip research-phase):

- **Phase 1：** AstrBot `_conf_schema.json`、配置迁移、帮助提示都有成熟宿主模式。
- **Phase 2：** ACP session / prompt / permission 生命周期文档充分，编排层抽象有明确标准面。
- **Phase 4：** 双 presenter 和事件折叠属于本项目内工程实现问题，研究方向已足够明确。

## Confidence Assessment

| Area         | Confidence | Notes                                                                            |
| ------------ | ---------- | -------------------------------------------------------------------------------- |
| Stack        | HIGH       | 关键结论基本都由 ACP、OpenCode、AstrBot 官方资料支撑，替代方案也有明确否决理由。 |
| Features     | HIGH       | 结合官方平台交互规范与当前项目目标，v1/v1.x/v2 的边界较清楚。                    |
| Architecture | HIGH       | 既有现仓实现可交叉验证，又有 ACP 生命周期标准作锚点，迁移顺序也较务实。          |
| Pitfalls     | HIGH       | 风险点与当前代码现状高度贴合，且多数可映射到具体阶段和验证项。                   |

**Overall confidence:** HIGH

### Gaps to Address

- **OpenCode permission 映射细节：** 研究已明确分层原则，但具体到每类高风险操作如何映射为 ask/deny/auto-allow，仍需 Phase 3 设计时逐项落表。
- **tool 返回结构最终 schema：** 已有推荐字段集合，但需要结合 AstrBot 上层 Agent 的实际消费方式做一次契约定稿。
- **当前命令语义基线文档缺口：** 研究指出 `/oc-new`、`/oc-end`、`/oc-session` 容易串义，规划前应补一版精确定义与手工回归脚本。
- **能力对齐清单尚未成文：** 需要把“支持 / 降级支持 / 不支持”的 OpenCode ACP 能力明确写进 README 与帮助文案。

## Sources

### Primary (HIGH confidence)

- ACP 官方协议仓库 / 本仓官方快照 — initialization、session setup、prompt turn、tool calls、configOptions、transports。
- OpenCode 官方文档 — ACP 支持、permissions、agents、已知能力边界。
- AstrBot 官方文档与仓库源码快照 — plugin config、session control、listen-message-event。
- 本仓 `.planning/PROJECT.md`、`main.py`、`core/session.py`、`core/executor.py`、`core/output.py` — 当前实现现状与迁移约束。

### Secondary (MEDIUM confidence)

- Slack slash command 文档 — 命令帮助、快速 ack、异步响应的交互期望。
- Discord application commands 文档 — 发现性、参数提示、权限与上下文设计参考。
- GitHub Copilot for Slack / session tracking / agent settings 文档 — 会话跟踪、steering、结果交付的产品方向参考。
- 项目内整理笔记 `docs/references/notes/*.md` — 用于交叉验证 OpenCode 与 AstrBot 结论。

### Tertiary (LOW confidence)

- 暂无关键结论依赖低置信单一来源。

---

_Research completed: 2026-03-29_
_Ready for roadmap: yes_
