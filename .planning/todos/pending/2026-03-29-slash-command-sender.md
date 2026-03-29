---
created: 2026-03-29T16:35:43.987Z
title: 简化 slash-command 与 sender 状态提示
area: general
files:
  - main.py:210-259
  - core/session.py:13-207
---

## Problem

当前 slash-command 相关的运行中/生命周期提示，以及会话与 sender 状态展示，已经分散在 `main.py` 的多个渲染路径里。随着 `/oc`、`/oc-new`、`/oc-end`、`/oc-session` 等命令继续演进，这些提示文案和状态字段很容易越堆越多，导致聊天界面噪音增加，也让“当前是哪类状态、针对哪个 sender、和 backend session 是否已绑定”变得不够直观。

## Solution

收敛 slash-command 与 sender 状态提示的职责边界，优先统一哪些状态必须展示、哪些只在必要时展示，并减少重复字段与冗长文案。实现上可从 `main.py` 的状态渲染函数入手，结合 `core/session.py` 的 sender/session 状态模型，梳理一套更简洁的提示策略，确保会话绑定、默认配置、当前 mode/agent 等信息在需要时仍然可见。
