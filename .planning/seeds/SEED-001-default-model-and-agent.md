---
id: SEED-001
status: dormant
planted: 2026-03-30T00:29:30+08:00
planted_during: milestone v1.0 / Phase 3 准备阶段
trigger_when: ACP基础功能完善后
scope: Medium
---

# SEED-001: 完善 ACP 基础功能后，支持设置默认模型与默认 agent

## Why This Matters

当前 slash-command 已经支持通过 `/oc-agent` 和 `/oc-mode` 管理默认偏好，但交互仍偏命令式，默认行为入口也不够完整。等 ACP 基础功能稳定后，再补上默认模型与默认 agent，可以减少重复输入，让 slash-command 的日常使用更顺手。

## When to Surface

**Trigger:** ACP基础功能完善后

This seed should be presented during `/gsd-new-milestone` when the milestone
scope matches any of these conditions:

- 里程碑开始从 ACP 协议打通、会话稳定性修复，转向 slash-command 交互体验与默认行为设计。
- 计划新增或重构默认偏好入口，尤其涉及默认 agent、mode/config option，或需要明确“默认模型”如何映射到 ACP/OpenCode 配置时。

## Scope Estimate

**Medium** — 这更像一个独立 phase，而不是单点改动。它既可能涉及命令入口与提示文案，也可能涉及 session 默认值、ACP payload 组装，以及“模型”在当前架构里是单独概念还是 mode/config option 的产品澄清。

## Breadcrumbs

Related code and decisions found in the current codebase:

- `.planning/STATE.md` - 当前 focus 已转向 Phase 3「直接聊天交互体验」，适合在 ACP 基础打稳后补默认行为体验。
- `.planning/ROADMAP.md` - Phase 3 明确要让 slash-command 更像直接操控 Coding Agent，和该想法直接相关。
- `.planning/phases/02.1-astrbot-phase-2/02.1-HUMAN-UAT.md` - 记录了 `default_agent`、`default_mode` 等字段已从 WebUI 面板移除，说明默认偏好目前更偏运行时能力而非面板配置。
- `main.py` - `_ensure_runtime_defaults()` 已补 `default_agent` / `default_mode` 默认值；`/oc-agent`、`/oc-mode` 已提供查看和设置入口。
- `core/executor.py` - 新建 ACP session 时会把 `session.default_agent`、`session.default_mode`、`session.default_config_options` 带入 payload，是未来默认行为真正落地的位置。
- `README.md` - 已把 `/oc-agent`、`/oc-mode` 纳入用户文档，说明默认偏好能力已经有基础，但仍可继续提升体验。
- `tests/test_main_commands.py` - 已覆盖 `/oc-agent`、`/oc-mode` 与默认偏好更新行为，后续扩展默认模型时可沿着现有测试模式补充。

## Notes

- 当前仓库里已有“默认 agent”和“默认 mode”，但没有明确的“默认模型”概念；后续实现前需要先澄清它是独立配置、ACP config option，还是 OpenCode agent/mode 体系的一部分。
- 这个想法更适合在 ACP 基础能力、会话稳定性和 runtime state 消费都完成后再做，否则容易一边补体验一边继续改底层契约。
