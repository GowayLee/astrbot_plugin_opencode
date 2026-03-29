# AstrBot-ACP 配置与交互重构

## What This Is

这是一个基于 ACP 协议的 AstrBot 插件重构项目，目标是在保留本地 `stdio` ACP 执行链路的前提下，重新整理插件的配置模型与交互模型。它既要支持用户通过 slash-command 直接间接操控底层 Coding Agent，也要支持 AstrBot 内置 Agent 通过 tools 调用 ACP 能力，但两种入口的输出语义与用户体验需要明确区分。

## Core Value

让 AstrBot 以自然、可控、低配置负担的方式接入 ACP Coding Agent，而不是把整套底层协议细节直接暴露给管理员和最终用户。

## Requirements

### Validated

- ✓ AstrBot 插件可以通过本地 `stdio` 启动 ACP 后端并完成初始化、会话创建、消息执行与会话恢复 — existing
- ✓ 插件已经提供一组 slash-command 来管理任务执行、工作目录、会话、文件发送、agent 与 mode 偏好 — existing
- ✓ 插件已经具备基础安全前置检查、运行时权限确认、工作目录历史记录和临时文件清理能力 — existing
- ✓ 插件已经支持将 ACP 能力作为 AstrBot LLM tool 暴露给上层 Agent 调用 — existing
- ✓ 插件已经实现配置驱动的输出链路，包括摘要、全文、TXT、长图与进度事件折叠 — existing
- ✓ 已验证 slash-command 与 tool 共用同一套执行内核，同时保持会话生命周期与输出语义可预期 — Validated in Phase 02: 会话内核与生命周期统一

### Active

- [ ] 重新设计 AstrBot 配置面板，使其从“协议字段集合”收敛为“管理员初始化配置”
- [ ] 收缩配置项，仅保留本地 ACP 启动命令、少量启动参数、启动超时、默认工作目录与文件写入开关等高层配置
- [ ] 下沉或移除 `backend_type`、`acp_client_capabilities`、默认 agent/mode/config、tool 元描述以及细碎输出配置等不适合面板暴露的字段
- [ ] 重新定义 slash-command 交互，让用户在 IM 中尽可能获得“正在直接操控 Coding Agent”的体验
- [ ] 重新定义 agent tool 输出链路，使 ACP 输出优先返回给 AstrBot 上层 Agent，再由上层 Agent 组织回复用户
- [ ] 为后续重构 `main.py` 和命令/工具编排边界建立更清晰的模块职责划分

### Out of Scope

- 远程 ACP 服务器连接 — 本轮明确保持本地 `stdio` 方案，不扩展远程传输层
- 将 slash-command 与 agent tool 拆成两套复杂权限系统 — 会显著提高配置复杂度，不符合当前目标
- 在配置面板中暴露整套 ACP 协议能力声明或细粒度调试开关 — 违背“产品化配置”方向

## Context

当前代码库已经完成从旧执行模型向 ACP-only 的收敛，核心执行链路稳定，代码结构采用 `main.py` + `core/` managers 的组织方式。现阶段最突出的问题不是“能不能用”，而是 AstrBot 侧配置面板和交互抽象过于底层：管理员看到的配置过多、过散，像是直接在配置 ACP 协议而不是配置一个插件产品。

用户明确希望这个插件承担两种角色：一是让终端用户通过 slash-command 在 IM 中直接与底层 Coding Agent 交互；二是让 AstrBot 内置 Agent 作为上层 Agent，通过 tool 间接操控底层 Coding Agent。这意味着两条入口在实现上可以复用 ACP 执行能力，但在输出归属和交互感受上必须区分：slash-command 需要尽量直出原始执行体验，tool 调用则应把结果先交给上层 Agent 消化。

代码库映射显示，当前 `main.py` 仍然承担大量命令编排、状态渲染、权限确认和后台执行逻辑；`call_opencode_tool` 目前直接后台推送消息给用户，这与目标中的“tool 输出先回到上层 Agent”不一致。与此同时，`_conf_schema.json` 仍然保留了较多协议级和实现细节级配置，后续需要把面板重新整理为更少、更稳的高层配置项。

## Current State

Phase 02 已完成并通过验证：共享执行内核、会话延续、历史会话恢复与 `/oc-new`、`/oc-end`、`/oc-session` 的生命周期语义已经收敛到一致行为，后续重点转向配置面板同步与真实宿主环境联调。

## Constraints

- **Transport**: 保持本地 `stdio` ACP 执行模型 — 本轮不引入远程 ACP 连接或新的传输抽象
- **Host Compatibility**: 需要继续符合 AstrBot 插件配置模型与命令/LLM tool 接入方式 — 不能脱离当前宿主框架约束
- **Brownfield**: 必须在现有 ACP-only 代码基础上迭代 — 不能用推倒重写换取结构整洁
- **UX Direction**: slash-command 需要尽量模拟 Coding Agent 的使用体验 — 配置和输出设计都要服务这个目标
- **Safety Scope**: 面板层只保留高层能力开关，当前已明确优先保留“文件写入”开关 — 避免重新引入大量细粒度安全配置

## Key Decisions

| Decision                                                           | Rationale                                              | Outcome   |
| ------------------------------------------------------------------ | ------------------------------------------------------ | --------- |
| 保持本地 `stdio` ACP 执行链路                                      | 当前执行层可用，远程连接会显著扩大改造范围             | — Pending |
| 配置面板定位为管理员初始化面板                                     | 当前配置过于协议化，不符合产品化使用方式               | — Pending |
| slash-command 与 agent tool 共用基础权限模型                       | 双权限体系会抬高复杂度，且很多能力天然耦合             | — Pending |
| 面板只保留少量高层配置                                             | 减少认知负担，避免把 ACP 协议细节直接暴露给管理员      | — Pending |
| slash-command 尽量覆盖 ACP 能力，但体验要更像直接控制 Coding Agent | 这是插件的直接用户价值之一                             | — Pending |
| agent tool 调用结果应优先返回给 AstrBot 上层 Agent                 | 这样才符合“上层 Agent 控制底层 Coding Agent”的架构语义 | — Pending |

---

_Last updated: 2026-03-29 after Phase 02 completion_
