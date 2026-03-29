# Pitfalls Research

**Domain:** 聊天原生 ACP Coding Agent 插件集成（AstrBot × OpenCode，本地 stdio）
**Researched:** 2026-03-29
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: 把“简化配置”做成“隐藏关键运行语义”

**What goes wrong:**
为了把 WebUI 面板做简单，直接删掉协议字段，却没有补上“插件自己的高层语义”。结果管理员看起来少配了很多东西，但实际上不知道插件会用哪个工作目录、默认权限策略是什么、slash-command 和 tool 调用是否共享会话，后续一出问题就只能读源码排查。

**Why it happens:**
团队把“减少字段数量”误当成“产品化完成”。但 ACP 里 `cwd`、session、permission、configOptions 都是有明确协议语义的，不能只靠“藏起来”解决复杂度。

**How to avoid:**

- 面板只暴露高层配置，但必须同步定义对应的运行时契约：`默认工作目录`、`是否允许写入`、`slash/tool 是否共用安全门`、`新会话默认行为`。
- 每删掉一个低层字段，都要补一条“内部固定策略”并写进设计文档。
- 规划阶段先产出一张“保留字段 → 内部映射 → 用户可见影响”表，再动 `_conf_schema.json`。

**Warning signs:**

- 需求讨论里频繁出现“这个就先写死吧”“管理员应该不用知道”。
- 同一个配置项在 README、schema、运行时代码里描述不一致。
- 管理员无法回答“新会话默认会怎么跑”。

**Phase to address:**
Phase 1 — 配置面板与运行时契约收敛

---

### Pitfall 2: 把 slash-command 和上层 Agent tool 当成同一种产品入口

**What goes wrong:**
两条入口复用同一执行链路后，输出也被混在一起：slash-command 本应直出 agent 过程，却被上层 Agent 二次包装；tool 调用本应先回给上层 Agent，却又直接往聊天里推流，导致重复回复、上下文错位、用户看不懂“到底是谁在说话”。

**Why it happens:**
实现层看到的是同一个 ACP `session/prompt`，就误以为 UX 层也应该完全统一；但项目目标已经明确区分“用户直接操控 Coding Agent”和“上层 Agent 间接调用底层 Agent”。

**How to avoid:**

- 在 roadmap 第一阶段就明确两条输出契约：
  - slash-command：聊天用户是直接接收者，可展示 plan/tool/progress/permission。
  - tool 调用：AstrBot 上层 Agent 是直接接收者，插件默认不主动向终端用户推送执行正文。
- 将“结果对象”和“发送策略”拆开；执行器只产出结构化事件，通道层决定是否发给用户。
- 为每个入口单独定义成功态、失败态、取消态、权限请求态。

**Warning signs:**

- 同一个执行结果同时进入 `event.send(...)` 和 tool return。
- PR/设计稿里出现“两个入口先共用同一套输出，后面再区分”。
- 日志里很难判断一条消息来自 slash 还是 tool。

**Phase to address:**
Phase 1 — 入口语义与输出归属定稿

---

### Pitfall 3: 用宿主进程状态代替 ACP session 真相

**What goes wrong:**
开发者把 sender 级缓存、AstrBot 会话控制、ACP session ID、工作目录偏好混成一个概念。短期看能跑，长期会出现会话串线：切目录后旧 session 仍被复用、绑定历史 session 但工作目录没对齐、权限确认落到错误会话上。

**Why it happens:**
聊天插件天然有“用户会话”概念，但 ACP 规范里 `cwd` 是 session 级参数，`session/new` / `session/load` / `session/prompt` 有严格生命周期，不能靠聊天层状态猜测。

**How to avoid:**

- 规划阶段就拆四类状态：`AstrBot sender scope`、`ACP session binding`、`next-session defaults`、`pending permission request`。
- 明确每个 slash-command 修改的是哪一层状态，禁止“一条命令改三层”。
- 设计恢复/切换流程时先画状态机，而不是先写 handler。

**Warning signs:**

- `work_dir`、`backend_session_id`、`selected_agent`、`pending_permission` 放在同一个无约束 dict 里随手改。
- `/oc-new`、`/oc-end`、`/oc-session` 的语义文案解释不清。
- 历史会话绑定后，当前目录/偏好/权限残留行为无法预测。

**Phase to address:**
Phase 2 — 会话状态模型与命令边界重构

---

### Pitfall 4: 只做前置安全检查，误以为后端 permission 会自动兜底

**What goes wrong:**
插件以为“有 OpenCode permission 就够了”，于是放松 AstrBot 侧前置门禁；或者反过来，把所有高风险都塞进前置关键词拦截，结果 ACP 的 `session/request_permission` 又来一轮，变成双重确认噪音。两种情况都会让安全和体验一起变差。

**Why it happens:**
OpenCode 权限默认比很多人想的更宽松：多数权限默认 `allow`，只有 `doom_loop` / `external_directory` 默认 `ask`。如果不做分层设计，就会在“过松”和“过吵”之间反复横跳。

**How to avoid:**

- 明确安全分层：
  1. 宿主级：管理员可用性、文件写入总开关、路径安全。
  2. 会话级：ACP permission request。
  3. 后端级：OpenCode permission 规则。
- 规划里为每类风险指定唯一主判定层，避免同一风险重复弹窗。
- “文件写入开关”不能只改 UI，要落实到 tool 结果拦截或 permission 回应策略。

**Warning signs:**

- 设计稿中没有列出“哪些风险由哪一层负责”。
- 测试时同一写操作被问两次以上。
- 团队成员说不清“关闭文件写入后，ACP permission 请求应该怎么处理”。

**Phase to address:**
Phase 3 — 安全模型与权限确认流重构

---

### Pitfall 5: 把 ACP 流式事件压扁成“最后一段文本”

**What goes wrong:**
为了减少刷屏，插件只保留最终文本，丢掉 `plan`、`tool_call`、`tool_call_update`、`request_permission`、`cancel` 等中间事件。结果 slash-command 体验看起来像一次性问答，不像 Coding Agent；一旦执行卡住，用户也不知道卡在哪。

**Why it happens:**
聊天产品常见思路是“尽量少发消息”，但 ACP 的核心价值恰恰是过程可见。把过程全吞掉，会直接损失 agent 感。

**How to avoid:**

- 先定义“必须可见的事件最小集”：开始、计划、工具执行、权限请求、完成/取消/失败。
- 做事件折叠而不是事件删除：允许合并展示，但不能在架构上丢失事件类型。
- slash-command 与 tool 调用采用不同渲染层，避免为了 tool 的简洁性牺牲 direct-user 模式的可观测性。

**Warning signs:**

- 代码里只有一个 `final_text` 聚合字段，没有事件流对象。
- 产品讨论把“流式更新”只理解为打字机效果。
- 用户遇到卡住时只能看到“执行中”，看不到当前工具或等待权限状态。

**Phase to address:**
Phase 2 — 事件模型抽象；Phase 4 — 聊天渲染优化

---

### Pitfall 6: 命令重构时承诺了 ACP/终端完全等价

**What goes wrong:**
slash-command UX 为了“像直接操控 Coding Agent”，对外宣称与终端版完全一致，后面用户马上会踩到 ACP 已知限制、宿主聊天限制、以及插件主动收敛后的差异，最终变成大量例外规则和补丁文案。

**Why it happens:**
“完全等价”很有吸引力，但 OpenCode 官方已明确：ACP 下虽然大部分功能可用，`/undo`、`/redo` 等内建 slash command 仍有缺口；再加上 AstrBot 聊天场景本身并不是终端 UI。

**How to avoid:**

- 产品文案改成“尽量接近直接操控 Coding Agent”，不是“100% 等价 TUI”。
- 在 roadmap 里单独列“能力对齐清单”：支持、降级支持、不支持。
- 重构命令前先决定哪些能力由插件 own，哪些只是透传后端，不混写在同一张命令表里。

**Warning signs:**

- README/需求中出现“所有 OpenCode slash command 都应该可用”。
- 命令设计开始依赖 ACP 未保证的行为。
- 为兼容个别命令不断加特判分支。

**Phase to address:**
Phase 1 — 能力边界声明；Phase 4 — 文档与迁移说明

---

### Pitfall 7: Brownfield 重构时先拆 `main.py`，后补契约测试

**What goes wrong:**
团队先按“代码洁癖”拆模块，但没有先锁定命令语义、状态迁移、权限确认、输出归属。最后出现结构更美但行为回归，尤其是在无自动化测试的插件环境里，很容易把 `/oc-new`、`/oc-session`、tool 调用等边缘链路悄悄改坏。

**Why it happens:**
现状确实是 `main.py` 过重，工程师自然想先重构结构；但这是 brownfield 插件，行为稳定性比模块形状更重要。

**How to avoid:**

- 先写“行为契约清单”，再拆模块：命令输入、状态变化、预期输出、异常分支。
- 以手工验证脚本替代缺失的自动化测试，纳入 roadmap 完成定义。
- 先抽边界接口（session service、output router、permission coordinator），不要一开始大搬家。

**Warning signs:**

- PR 描述只写“重构代码结构”，不写用户可见行为是否保持。
- 无法列出 5~8 条必须回归验证的聊天流程。
- 模块拆分后文档、schema、README 没同步更新。

**Phase to address:**
Phase 0 / 启动前置任务 — 行为基线与手工验证清单；Phase 2 — 渐进式模块抽离

---

## Technical Debt Patterns

| Shortcut                                                        | Immediate Benefit | Long-term Cost                   | When Acceptable                      |
| --------------------------------------------------------------- | ----------------- | -------------------------------- | ------------------------------------ |
| 先保留旧 `_conf_schema.json` 大部分字段，只在文案上说“别管它们” | 改动小            | 面板继续协议化，后面很难真正收敛 | 仅可作为 1 个迭代内过渡              |
| slash-command 和 tool 共用同一个“发消息函数”                    | 复用快            | 输出归属永远缠在一起             | 不建议；最多用于临时兼容层           |
| 继续在 `main.py` 里堆 if/else，把新语义先跑通                   | 上线快            | 命令边界越来越不可验证           | 仅在 Phase 1 早期做短期过桥          |
| 用关键词判断“写操作”而不看实际 ACP 工具类型                     | 实现简单          | 误报/漏报都高，安全策略失真      | 只能作为第一层粗筛，不能作为最终判定 |

## Integration Gotchas

| Integration           | Common Mistake                                          | Correct Approach                                                      |
| --------------------- | ------------------------------------------------------- | --------------------------------------------------------------------- |
| ACP session lifecycle | 以为切工作目录只要改子进程 cwd                          | `cwd` 是 session 级参数，必须通过 `session/new` / `session/load` 建模 |
| OpenCode permissions  | 误以为后端默认很保守                                    | 按官方默认设计二层/三层防线，不假设后端替插件兜底                     |
| AstrBot 会话控制      | 把 AstrBot 会话控制器直接等同于 ACP 会话                | AstrBot 只负责宿主聊天交互，ACP session 仍需独立状态管理              |
| Agent/config 选择     | 把 OpenCode agent、ACP mode、configOptions 混成一个字段 | 分别存储；`configOptions` 优先于旧 `modes`，agent 保持独立            |

## Performance Traps

| Trap                                   | Symptoms                          | Prevention                                     | When It Breaks                   |
| -------------------------------------- | --------------------------------- | ---------------------------------------------- | -------------------------------- |
| 每个流式 update 都直接发一条聊天消息   | 群聊刷屏、消息乱序、风控/频率限制 | 做事件聚合与节流，但保留事件语义               | 一旦进入长任务或高频 tool update |
| 历史会话加载时同步重放全部内容到用户侧 | 绑定旧会话时刷出大量旧消息        | 会话恢复与用户可见回放分离，默认只恢复内部状态 | 会话稍长就明显恶化               |
| 工具调用和最终文本走同一重格式化链     | CPU/渲染开销高，输出重复          | 中间事件轻量渲染，重格式化只用于最终可交付文本 | 长文本、长图、摘要同时开启时     |

## Security Mistakes

| Mistake                                        | Risk                               | Prevention                                                      |
| ---------------------------------------------- | ---------------------------------- | --------------------------------------------------------------- |
| 把“文件写入开关”只做成 UI 提示，不真正阻断执行 | 用户以为禁写，实际上仍可改文件     | 将其落到 permission 响应或执行前拦截的硬逻辑                    |
| 关闭路径安全后仍保留 `/oc-send` 的自由文件发送 | 宿主敏感文件误发                   | 明确 `/oc-send` 与 ACP 内部文件访问是两套边界，并给出高风险提示 |
| 允许 tool 调用直接向终端用户推送原始执行结果   | 上层 Agent 隐私/系统提示泄漏给用户 | tool 输出默认只回给上层 Agent，由上层 Agent 决定对用户说什么    |

## UX Pitfalls

| Pitfall                                                       | User Impact                                  | Better Approach                                          |
| ------------------------------------------------------------- | -------------------------------------------- | -------------------------------------------------------- |
| `/oc-new`、`/oc-end`、`/oc-session` 语义过近                  | 用户不知道是“换目录”“断开会话”还是“绑定历史” | 每条命令只做一件事，并在回复里明确“改了什么/没改什么”    |
| 配置面板仍出现 `backend_type`、`client_capabilities` 等底层词 | 管理员不敢改、也不知道该不该改               | 只保留高层初始化项，把低层细节固化到内部实现             |
| tool 调用时也向用户展示完整 plan/tool_call                    | 用户看到上层 Agent 的中间思考噪音            | direct-user 模式展示过程；upper-agent 模式只返结构化结果 |

## "Looks Done But Isn't" Checklist

- [ ] **配置收敛：** 不只是删字段，还要验证 README、schema、默认值、运行时行为完全一致。
- [ ] **输出分流：** 验证 slash-command 不走上层 Agent 话术，tool 调用不直接刷用户聊天。
- [ ] **会话切换：** 验证 `/oc-new`、`/oc-end`、`/oc-session` 对 `work_dir`、session 绑定、pending permission 的影响各自正确。
- [ ] **禁写模式：** 验证普通写文件、批量修改、外部目录写入都能被一致拦截。
- [ ] **权限确认：** 验证超时、取消、无效输入、allow always 都不会串到别的会话。
- [ ] **历史会话恢复：** 验证恢复后不会把旧消息重新刷给用户，且后续 prompt 仍延续上下文。

## Recovery Strategies

| Pitfall            | Recovery Cost | Recovery Steps                                                                                           |
| ------------------ | ------------- | -------------------------------------------------------------------------------------------------------- |
| 输出归属混乱       | HIGH          | 先冻结新功能；抽离 output router；给 slash/tool 补独立返回类型；回归所有命令链路                         |
| 会话状态串线       | HIGH          | 清点状态字段；补状态机；把 sender 默认值与 live session 解绑；手工回归 `/oc-new` `/oc-end` `/oc-session` |
| 双重确认或安全缺口 | MEDIUM        | 列风险分层表；统一主判定层；补禁写/超时/拒绝路径验证                                                     |
| 配置面板简化过度   | MEDIUM        | 回补必要高层配置说明；为内部固定策略补文档和迁移提示                                                     |

## Pitfall-to-Phase Mapping

| Pitfall                     | Prevention Phase  | Verification                                                       |
| --------------------------- | ----------------- | ------------------------------------------------------------------ |
| 简化配置但隐藏关键语义      | Phase 1           | 面板字段减少后，仍能用文档回答“默认工作目录/权限/新会话行为是什么” |
| slash 与 tool 输出混流      | Phase 1           | 同一任务不会同时出现 direct-user 推送和 tool return 双重回复       |
| 宿主状态与 ACP session 混淆 | Phase 2           | `/oc-new` `/oc-end` `/oc-session` 的状态变化可逐项列清并手工验证   |
| 安全分层失真                | Phase 3           | 写操作、外部路径、权限超时都只有一个主拦截点且行为一致             |
| 流式事件被压扁              | Phase 2 / Phase 4 | 用户能看到最小必要过程事件，且不会被高频 update 刷屏               |
| 过度承诺 ACP/TUI 等价       | Phase 1 / Phase 4 | README 与命令帮助中明确列出支持/降级/不支持能力                    |
| 先大拆 `main.py` 再补验证   | Phase 0 / Phase 2 | 每次结构调整都有对应行为清单与手工回归记录                         |

## Sources

- `.planning/PROJECT.md` — 本项目目标、边界与后续里程碑上下文（HIGH）
- `docs/references/official/acp/session-setup.mdx` — ACP 官方快照：`cwd`、`session/new`、`session/load`（HIGH）
- `docs/references/official/acp/prompt-turn.mdx` — ACP 官方快照：`session/update`、取消、流式生命周期（HIGH）
- `docs/references/official/acp/tool-calls.mdx` — ACP 官方快照：tool_call、permission request（HIGH）
- `docs/references/official/acp/session-config-options.mdx` — ACP 官方快照：`configOptions` 优先于 `modes`（HIGH）
- `https://opencode.ai/docs/acp` — OpenCode 官方文档：ACP 支持范围与 `/undo`、`/redo` 限制（HIGH，抓取于 2026-03-29）
- `https://opencode.ai/docs/permissions` — OpenCode 官方文档：permission 默认值、`external_directory`、agent 权限覆盖（HIGH，抓取于 2026-03-29）
- `docs/references/official/astrbot/session-control.md` — AstrBot 官方快照：宿主会话控制语义（HIGH）
- `docs/references/notes/opencode-summary.md` — 基于官方资料整理的项目内实现笔记，用于交叉验证设计风险（MEDIUM）
- `README.md`、`_conf_schema.json` — 当前插件公开语义与现存配置面板暴露面（HIGH）

---

_Pitfalls research for: AstrBot-ACP 配置与交互重构_
_Researched: 2026-03-29_
