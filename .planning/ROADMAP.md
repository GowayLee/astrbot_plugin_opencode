# Roadmap: AstrBot-ACP 配置与交互重构

## Overview

这次路线图围绕 19 个 v1 需求展开：先完成管理员可用的高层配置与兼容迁移，再收敛会话/执行状态边界，随后补齐 slash-command 的直接操控体验，最后落定 tool 回传与统一安全策略，让插件真正呈现为一个可配置、可直控、可被上层 Agent 稳定编排的产品。

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: 配置收敛与兼容迁移** - 把面板收敛成管理员初始化配置，并保证升级后可平滑继续使用。
- [ ] **Phase 2: 会话内核与生命周期统一** - 收敛会话延续、切换、重置与共享执行内核的状态边界。
- [ ] **Phase 3: 直接聊天交互体验** - 让 slash-command 更像直接操控 Coding Agent，并具备即时反馈与过程感。
- [ ] **Phase 4: Tool 回传与统一安全策略** - 让 tool 结果回到上层 Agent，并把高层安全策略统一落到两条入口。

## Phase Details

### Phase 1: 配置收敛与兼容迁移

**Goal**: 管理员可以用少量高层配置完成插件初始化，并在升级后继续稳定使用插件。
**Depends on**: Nothing (first phase)
**Requirements**: CONF-01, CONF-02, CONF-03, CONF-04, CONF-05
**Success Criteria** (what must be TRUE):

1. 管理员可以在 AstrBot 配置面板完成插件初始化，而不需要理解 ACP 协议级字段。
2. 管理员可以直接设置本地 ACP 启动命令、少量启动参数、启动超时、默认工作目录和文件写入开关。
3. 已安装实例升级到新配置结构后，仍可在不手工补齐大量旧字段的前提下继续使用核心能力。

**Plans:** 1 plan

Plans:

- [ ] 01-01-PLAN.md — 重设计配置面板 + 实现迁移与消费端适配

### Phase 2: 会话内核与生命周期统一

**Goal**: 用户与上层 Agent 都能建立在同一套执行内核之上，并获得一致、可预期的会话行为。
**Depends on**: Phase 1
**Requirements**: SESS-01, SESS-02, SESS-03
**Success Criteria** (what must be TRUE):

1. 同一聊天身份连续提交任务时，可以延续既有 ACP 会话而不意外丢失上下文。
2. 用户执行 `/oc-new`、`/oc-end`、`/oc-session` 后，会话创建、结束、切换的结果与提示保持一致且可预期。
3. slash-command 与 tool 调用基于同一套执行内核运行，但不会出现会话状态串线或输出语义混淆。

**Plans:** 1/2 plans executed

Plans:

- [ ] 02-01-PLAN.md — 统一 slash-command 与 tool 的共享会话执行内核
- [ ] 02-02-PLAN.md — 固化 /oc-new、/oc-end、/oc-session 的生命周期语义

### Phase 02.1: AstrBot 实际加载环境中的配置面板同步与联调验证：先解决配置面板仍显示旧繁琐配置的问题，再回到 Phase 2 的真实运行环境验证 (INSERTED)

**Goal**: 确认 AstrBot 宿主实际加载的是哪份插件元数据与配置 schema，修复导致旧配置面板持续显示的根因，并完成一轮真实环境联调闭环。
**Requirements**: CONF-01, CONF-02, CONF-03, CONF-04, CONF-05
**Depends on:** Phase 2
**Success Criteria** (what must be TRUE):

1. 可以明确说明 AstrBot 实际加载的是哪份插件目录、`metadata.yaml` 与 `_conf_schema.json`，不再靠猜测排查。
2. WebUI 配置面板展示的字段与仓库当前精简后的 schema 一致，不再残留旧的协议级配置项。
3. 如果问题来自插件标识、宿主缓存或升级路径，仓库里有对应修复或升级说明，后续可复现处理。
4. 完成 Phase 2.1 后，可以带着已验证的宿主环境回到 Phase 2 的真实运行链路验证。

**Plans:** 1/1 plans complete

Plans:

- [x] 02.1-01-PLAN.md — 定位宿主加载链路并修复配置面板未同步的根因

### Phase 02.2: 调研补全Astrbot插件开发文档、ACP协议、OpenCode ACP Server规格 (INSERTED)

**Goal:** 补全docs/references目录中的关键文档，为后续开发提供准确的协议与规格参考。
**Requirements**: TBD
**Depends on:** Phase 2
**Plans:** 2 plans

Plans:

- [ ] 02.2-01-PLAN.md — 建立 AstrBot 与 ACP 两份开发参考基线
- [ ] 02.2-02-PLAN.md — 补齐 OpenCode 参考并收口 docs/references 统一索引

### Phase 3: 直接聊天交互体验

**Goal**: 用户在 IM 中可以像直接操控 Coding Agent 一样发起任务、跟踪过程并完成必要确认。
**Depends on**: Phase 2
**Requirements**: CHAT-01, CHAT-02, CHAT-03, CHAT-04, CHAT-05, SAFE-02
**Success Criteria** (what must be TRUE):

1. 用户可以通过一个主 slash-command 直接提交自然语言任务给底层 Coding Agent。
2. 任务开始后，用户可以立即看到“已接收/已开始”反馈，而不必等到最终结果。
3. 执行过程中，用户可以在 IM 中看到关键进度、权限确认和结束状态，而不是只收到最终长文本。
4. 用户可以明确地新建、结束或切换会话，并通过这些命令控制当前上下文边界。
5. 当命令参数缺失、用法错误或触发受控操作时，用户可以得到清晰帮助提示，并通过纯文本完成确认；超时或拒绝时默认失败关闭。

**Plans**: TBD

### Phase 4: Tool 回传与统一安全策略

**Goal**: AstrBot 上层 Agent 可以稳定编排底层 Coding Agent，并让 chat/tool 两条入口遵守同一套高层安全策略。
**Depends on**: Phase 3
**Requirements**: TOOL-01, TOOL-02, TOOL-03, SAFE-01, SAFE-03
**Success Criteria** (what must be TRUE):

1. AstrBot 上层 Agent 可以通过插件 tool 驱动底层 Coding Agent，而插件不会直接代替上层 Agent 向用户发送最终结果。
2. tool 调用完成后，上层 Agent 可以拿到结构化结果，其中至少包含执行状态、摘要、会话标识和关键产物引用。
3. 当 tool 调用等待权限确认、执行失败、被拒绝或被取消时，上层 Agent 可以收到对应的结构化状态，而不是模糊文本。
4. 当管理员关闭文件写入能力时，写入类操作会被实际阻止，并且这种阻止在相关入口上表现一致。
5. slash-command 与 tool 调用遵守同一套高层安全策略与 permission 中介逻辑，不会出现一条链路绕过另一条链路的情况。

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 2.1 → 2.2 → 3 → 4

| Phase                           | Plans Complete | Status      | Completed  |
| ------------------------------- | -------------- | ----------- | ---------- |
| 1. 配置收敛与兼容迁移           | 1/1            | Implemented | 2026-03-29 |
| 2. 会话内核与生命周期统一       | 2/2            | Complete    | 2026-03-29 |
| 2.1. 配置面板同步与联调验证     | 1/1            | Complete    | 2026-03-29 |
| 2.2. 调研补全开发文档与协议规格 | 0/2            | Planned     | -          |
| 3. 直接聊天交互体验             | 0/TBD          | Not started | -          |
| 4. Tool 回传与统一安全策略      | 0/TBD          | Not started | -          |
