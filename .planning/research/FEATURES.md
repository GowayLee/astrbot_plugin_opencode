# Feature Research

**Domain:** 聊天原生的 ACP Coding Agent 桥接插件（AstrBot / IM slash-command / 上层 Agent tool）
**Researched:** 2026-03-29
**Confidence:** HIGH

## Feature Landscape

### Table Stakes — 管理员配置 UX

缺了这些，插件就会像“把底层协议原样扔给管理员”。

| Feature                                                                    | Why Expected                                                                                                           | Complexity | Notes                                                                                                          |
| -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- | ---------- | -------------------------------------------------------------------------------------------------------------- |
| 高层初始化配置面板（启动命令、启动参数、启动超时、默认工作目录、写入开关） | AstrBot 官方配置系统本来就支持可视化 schema、默认值、hint；管理员预期看到的是“怎么把插件跑起来”，不是 ACP 字段表       | MEDIUM     | 面板只保留产品级入口；把 `backend_type`、client capabilities、细碎输出开关等协议细节下沉到内部默认或代码常量   |
| 安全默认值 + 权限预设                                                      | OpenCode 当前权限模型就是 `allow / ask / deny`，而 ACP 也原生支持 `request_permission`；管理员预期能先用安全默认跑起来 | MEDIUM     | 默认应偏保守：文件写入、危险 bash、外部目录访问需要 ask 或显式开；不要要求管理员手写规则对象才能上线           |
| 工作目录/仓库范围约束                                                      | 聊天里调用 coding agent，如果没有目录边界，管理员很难判断插件到底会动哪里                                              | MEDIUM     | 至少要有默认工作目录、是否允许切换目录、是否允许越界访问的高层开关；细粒度规则可内部映射到 OpenCode permission |
| 配置迁移与 sane defaults                                                   | AstrBot 会根据 `_conf_schema.json` 自动补默认值、移除旧字段；管理员预期升级后不用手工修配置                            | LOW        | 这是面板重构可落地的基础能力，应该直接利用 AstrBot 现成机制                                                    |
| 最小必需的集成设置（默认 agent/默认仓库目标/默认输出策略）                 | GitHub Copilot Slack 首次使用会要求连接账号并设置 default repository；用户预期插件至少知道“默认在哪工作”               | MEDIUM     | 本项目不是 GitHub 集成，但同样需要一个明确的“默认上下文”，例如默认 workdir 与默认回复模式                      |

### Table Stakes — 直接 slash-command UX

缺了这些，用户不会觉得自己在“直接操控 Coding Agent”。

| Feature                                           | Why Expected                                                                                                 | Complexity | Notes                                                                                         |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ---------- | --------------------------------------------------------------------------------------------- |
| 一个主命令承接自然语言任务，辅以少量生命周期命令  | Slack/Discord 都把命令设计成清晰、短、可发现的入口；聊天里不适合一堆工程化子命令                             | MEDIUM     | `/oc <任务>` 应该是主入口；`/oc-new`、`/oc-end`、`/oc-session` 这类会话命令保留，但总量要克制 |
| 命令帮助、usage hint、参数可发现性                | Slack 官方明确建议提供 help action 和 usage hint；Discord 通过 description/options/autocomplete 降低记忆负担 | LOW        | 需要 `/oc help`、错误用法时给出示例、分页/筛选类命令给明确参数提示                            |
| 即时确认 + 异步进度回传                           | Slack 要求 3 秒内 ack，否则用户看到 timeout；ACP 工具调用本身也通过 `session/update` 持续回报进度            | MEDIUM     | 先回“已开始处理”，再持续回传关键进度；不要等任务结束才一次性发长文                            |
| 会话连续性与显式重置/切换                         | coding agent 使用是会话型的；GitHub Copilot 也强调 session 跟踪、steering、stop                              | MEDIUM     | 用户要能延续上下文，也要能明确 `new/end/switch`，否则聊天环境极易串任务                       |
| 输出语义分层（摘要 / 完整输出 / 文件 / 长文载体） | 聊天窗口不适合 IDE 全量日志直喷；当前仓库已验证需要摘要、全文、TXT、长图等多级输出                           | MEDIUM     | 默认先给结论与下一步，再按配置附全文/TXT；长输出必须可折叠或转附件                            |
| 交互式审批的文本化承接                            | ACP 权限请求允许 `allow_once / allow_always / reject_*`；AstrBot 有 session waiter，但很多 IM 没有按钮组件   | MEDIUM     | 必须有纯文本审批格式，如“回复 1 允许一次 / 2 始终允许 / 3 拒绝”；默认超时 fail closed         |
| 文件/引用上下文注入                               | GitHub Copilot Slack 会捕获 thread context；Discord/Slack 都强调把结构化输入送进命令                         | HIGH       | slash-command 至少要能带回复消息、附件、当前 workdir 下文件引用；否则编码任务信息不完整       |
| 错误恢复与取消                                    | 长任务必然会失败或跑偏；Copilot session 允许 stop/steer                                                      | MEDIUM     | 需要“停止当前任务”“继续补充说明”“查看最近会话状态”的最小闭环                                  |

### Table Stakes — 上层 Agent tool mediation

缺了这些，就不是“上层 Agent 调底层 Coding Agent”，而是两个 bot 同时对用户说话。

| Feature                                                          | Why Expected                                                                                                | Complexity | Notes                                                                                                           |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ---------- | --------------------------------------------------------------------------------------------------------------- |
| 工具返回结构化结果给上层 Agent，而不是直接把原始日志推给终端用户 | mediated tool use 的核心就是“上层 Agent 编排、下层 Agent 执行”；ACP/OpenCode 已经有工具调用、权限、状态对象 | HIGH       | `call_opencode_tool` 应返回摘要、状态、关键产物、可选原始日志；默认不要后台直接发消息给用户                     |
| 与 slash-command 分离的输出策略                                  | 同一执行能力可复用，但输出归属不同；PROJECT.md 已明确两条入口必须区分                                       | MEDIUM     | tool 模式优先返回 machine-readable 结果；slash-command 模式优先返回 chat-friendly 结果                          |
| 上层 Agent 可感知的运行状态与可取消性                            | ACP `session/update` 和 GitHub Copilot session tracking 都说明 agent 任务天然是长流程                       | HIGH       | 至少返回 running / waiting_permission / completed / failed / cancelled；上层 Agent 才能决定是否追问、等待或中止 |
| 权限请求可被宿主/上层 Agent 中介                                 | ACP 明确客户端可以按用户设置自动 allow/reject，也可以向用户请求 permission                                  | HIGH       | 需要一个统一 permission broker：能转成人类确认，也能按策略自动处理；不能让下层 agent 绕过宿主安全模型           |
| 可审计的产物引用（修改文件、命令摘要、会话 ID）                  | GitHub Copilot 提供 session logs、PR 链接、commit 到 session 的可追溯关系；企业环境会把审计当基础要求       | MEDIUM     | tool 返回里至少带 session ID、变更文件列表、执行摘要；必要时附原始日志句柄而非全量文本                          |
| 上下文边界控制（workdir、附件、引用消息）                        | 上层 Agent 不应把整段聊天历史不加筛选地喂给 coding agent                                                    | MEDIUM     | tool 入参要显式传任务、工作目录、附件列表、是否继承当前会话；避免隐式抓全量上下文                               |

### Differentiators (Competitive Advantage)

这些不是“没有就不能用”，但会明显拉开和普通 bot wrapper 的差距。

| Feature                                               | Value Proposition                                                                           | Complexity | Notes                                                                                     |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------- | ---------- | ----------------------------------------------------------------------------------------- |
| slash-command 与 tool 模式双语义产品化                | 大多数集成只做好一种入口；本项目同时服务终端用户直控和上层 Agent 编排                       | HIGH       | 这是本项目最核心的差异点：同一 ACP 引擎，两套清晰输出契约                                 |
| 权限审批记忆 + 会话内安全建议                         | OpenCode 的 `always`/`reject always` 已有底层能力，但聊天产品通常不会把它做成适合 IM 的体验 | HIGH       | 可把高频安全命令自动归纳成“本会话已信任 git status / 拒绝 rm \*”之类可见规则              |
| 面向聊天的进度折叠与结果压缩                          | ACP/OpenCode 会产生大量 tool updates；聊天端真正稀缺的是注意力，不是 token                  | MEDIUM     | 合并连续进度、只展示状态跃迁、把详细日志下沉到附件/TXT，是比“原样流式”更强的产品化能力    |
| 任务 steering（补充说明而不断会话）                   | GitHub Copilot 支持对运行中 session 追加 steering；聊天场景尤其需要这个能力                 | HIGH       | 比“取消后重来”更好，适合 IM 里的渐进式任务澄清                                            |
| 管理员预设模板（安全/输出/目录策略）                  | AstrBot schema 支持 template-like 组织；管理员常见需求不是自由拼装，而是快速套一个可用策略  | MEDIUM     | 例如“只读审查模式”“本地开发模式”“写入需确认模式”                                          |
| 产物导向回复（补丁/文件/TXT/长图/摘要）自动按场景选择 | 竞品往往只给 PR 链接或一段摘要；插件场景更需要在聊天里交付可消费产物                        | MEDIUM     | slash-command 可默认“摘要 + 可下载产物”；tool 模式则回结构化字段供上层 Agent 决定如何展示 |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature                                            | Why Requested          | Why Problematic                                                                                | Alternative                                                                   |
| -------------------------------------------------- | ---------------------- | ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| 在配置面板暴露完整 ACP/OpenCode 协议字段           | “高级用户想全都能配”   | 会把插件重新做成协议调试器，直接违背 PROJECT.md 的产品化目标，也让默认配置不可维护             | 面板只保留高层配置；把协议细节下沉到代码默认、隐藏配置或后续 expert-mode 文档 |
| slash-command 与 tool 各自维护一套完全独立权限体系 | 看起来更灵活           | 管理复杂度翻倍，且真实风险边界高度重合；后续几乎必然出现策略不一致                             | 共享同一安全核心，只允许在“输出归属/展示层”分流                               |
| 把每个底层能力都做成独立命令                       | 好像更“全功能”         | 命令爆炸、记忆负担重，聊天输入成本大；Discord/Slack 都鼓励短入口+结构化参数                    | 保留 1 个主命令 + 少量生命周期命令，复杂能力通过自然语言和少量参数承载        |
| 默认公开回传完整执行日志                           | 团队里有人想“透明可见” | 聊天噪音大、泄露风险高、上层 Agent 无法再组织答案；Slack 也强调 response visibility 要明确控制 | 默认摘要优先，详细日志转附件/长文/仅管理员可见                                |
| 默认永久自动批准写入/执行                          | 图省事                 | 对 coding agent 来说这是高风险默认，尤其在聊天环境下误触发概率更高                             | 默认 ask；只对低风险读操作和少量白名单命令自动放行                            |
| 隐式抓取整段群聊作为任务上下文                     | 觉得“上下文越多越聪明” | GitHub Copilot Slack 已明确提醒 thread context 会被完整捕获并存储到 PR；这有隐私和噪音双重问题 | 明确告知上下文来源，只抓当前消息、回复链或用户显式附加内容                    |

## Feature Dependencies

```text
[高层初始化配置面板]
    └──requires──> [配置迁移与 sane defaults]
    └──requires──> [安全默认值 + 权限预设]

[主命令 + 生命周期命令]
    └──requires──> [会话连续性与显式重置/切换]
    └──enhances──> [错误恢复与取消]

[即时确认 + 异步进度回传]
    └──requires──> [输出语义分层]
    └──requires──> [可审计的产物引用]

[交互式审批的文本化承接]
    └──requires──> [权限请求可被宿主/上层 Agent 中介]
    └──conflicts──> [默认永久自动批准写入/执行]

[工具返回结构化结果给上层 Agent]
    └──requires──> [与 slash-command 分离的输出策略]
    └──requires──> [上下文边界控制]
    └──enhances──> [上层 Agent 可感知的运行状态与可取消性]

[任务 steering]
    └──requires──> [会话连续性与显式重置/切换]
    └──requires──> [上层 Agent 可感知的运行状态与可取消性]
```

### Dependency Notes

- **高层初始化配置面板 requires 配置迁移与 sane defaults：** 不先做好默认值与旧字段迁移，面板收缩会直接导致升级后不可用。
- **主命令 + 生命周期命令 requires 会话连续性：** 没有稳定 session，`/oc` 就只是一次性问答，不像 coding agent。
- **即时确认 + 异步进度回传 requires 输出语义分层：** 只要任务超过几秒，聊天端就必须区分“开始了 / 进行中 / 结束了 / 详细内容在哪”。
- **交互式审批的文本化承接 requires 权限中介：** ACP 只定义 permission option，真正把它变成 IM 里的可回复流程，是宿主插件责任。
- **工具返回结构化结果给上层 Agent requires 分离输出策略：** 不先定义双入口契约，就会再次出现 tool 模式直接往前台刷屏的问题。
- **任务 steering requires 运行状态可见：** 用户或上层 Agent 只有知道当前 session 还活着，补充说明才有意义。

## MVP Definition

### Launch With (v1)

- [x] 高层初始化配置面板 — 先把管理员认知从“协议字段集合”切回“插件初始化”
- [x] 主命令 + 少量生命周期命令 — 让用户能直接在 IM 里发起、续接、重置 coding task
- [x] 即时确认 + 异步进度回传 + 输出分层 — 解决聊天端等待焦虑和长输出污染
- [x] 文本化权限审批 + 安全默认值 — 没有这一层，聊天环境风险过高
- [x] tool 模式结构化返回给上层 Agent — 这是本里程碑最关键的边界修正

### Add After Validation (v1.x)

- [ ] 任务 steering — 当真实使用中出现“任务跑偏但不想重来”的频率足够高时再加
- [ ] 管理员预设模板 — 当配置项稳定后，用模板替代手工组合
- [ ] 更细的审计视图（会话列表、变更摘要、附件化日志） — 当多管理员或团队协作需求出现时补上

### Future Consideration (v2+)

- [ ] 更强的多仓库/多工作区路由 — 目前默认工作目录 + 显式切换已够用，过早做会显著抬高复杂度
- [ ] 更富交互的按钮/UI 组件审批 — 受宿主平台差异限制大，先以纯文本方案兜底
- [ ] 高级专家模式配置面板 — 只有在高层面板验证有效后，才考虑给少数高级用户开放更多调优入口

## Feature Prioritization Matrix

| Feature                            | User Value | Implementation Cost | Priority |
| ---------------------------------- | ---------- | ------------------- | -------- |
| 高层初始化配置面板                 | HIGH       | MEDIUM              | P1       |
| 主命令 + 生命周期命令              | HIGH       | MEDIUM              | P1       |
| 即时确认 + 异步进度回传 + 输出分层 | HIGH       | MEDIUM              | P1       |
| 文本化权限审批 + 安全默认值        | HIGH       | MEDIUM              | P1       |
| tool 模式结构化返回                | HIGH       | HIGH                | P1       |
| 会话连续性与切换                   | HIGH       | MEDIUM              | P1       |
| 文件/引用上下文注入                | HIGH       | HIGH                | P2       |
| 任务 steering                      | MEDIUM     | HIGH                | P2       |
| 管理员预设模板                     | MEDIUM     | MEDIUM              | P2       |
| 细粒度审计视图                     | MEDIUM     | MEDIUM              | P2       |
| 多仓库/多工作区高级路由            | MEDIUM     | HIGH                | P3       |
| 富交互按钮审批                     | LOW        | HIGH                | P3       |

**Priority key:**

- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Competitor Feature Analysis

| Feature    | Competitor A                                                | Competitor B                                                            | Our Approach                                                            |
| ---------- | ----------------------------------------------------------- | ----------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| 聊天入口   | Slack 官方推荐短命令 + usage hint + 异步响应                | Discord 原生 slash command 强调 description/options/context/permissions | 采用一个主命令 + 少量生命周期命令，不走命令爆炸路线                     |
| 会话与进度 | GitHub Copilot 提供 session tracking、logs、steering、stop  | 一般 bot 多为一次性回答                                                 | 在聊天里保留 session continuity，但把日志折叠成更适合 IM 的状态流       |
| 权限与安全 | OpenCode 自带 allow/ask/deny 与 session 内 remember         | 很多简单 bot 只有全局开关                                               | 复用 OpenCode/ACP 权限语义，但用 AstrBot 会话控制承接文本审批           |
| 输出归属   | Copilot Slack 最终返回 summary + PR link                    | 普通 bot 常直接把运行结果发给用户                                       | slash-command 直出聊天结果；tool 模式默认返回上层 Agent，不直接前台刷屏 |
| 配置 UX    | AstrBot 提供 schema/hint/default/file/template 等可视化能力 | 很多桥接插件把 JSON 原样暴露                                            | 收缩到管理员初始化配置，不把 ACP 协议面向用户公开                       |

## Sources

- `.planning/PROJECT.md` — 本项目目标、约束、边界（HIGH）
- AstrBot 官方插件配置文档：`docs/references/official/astrbot/plugin-config.md`（HIGH）
- AstrBot 项目内总结：`docs/references/notes/astrbot-summary.md`（MEDIUM，基于官方文档提炼）
- ACP 官方 Tool Calls：`docs/references/official/acp/tool-calls.mdx`（HIGH）
- OpenCode 官方 Permissions：`docs/references/official/opencode/permissions.mdx`（HIGH）
- Slack Developer Docs — Implementing slash commands: https://api.slack.com/interactivity/slash-commands （HIGH）
- Discord Developer Docs — Application Commands: https://docs.discord.com/developers/interactions/application-commands （HIGH）
- GitHub Docs — Integrating Copilot coding agent with Slack: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/integrate-coding-agent-with-slack （MEDIUM，预览能力但足够说明当前产品方向）
- GitHub Docs — Tracking GitHub Copilot's sessions: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/track-copilot-sessions （MEDIUM）
- GitHub Docs — Configuring settings for GitHub Copilot coding agent: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/coding-agent/configuring-agent-settings （MEDIUM）

---

_Feature research for: 聊天原生 ACP coding-agent bridge plugin_
_Researched: 2026-03-29_
