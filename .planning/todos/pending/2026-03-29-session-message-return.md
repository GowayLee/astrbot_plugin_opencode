---
created: 2026-03-29T15:10:00.000Z
title: 设计并实现 session 消息回传
area: general
files:
  - session
---

## Problem

当前已经实际验证可以成功创建对话，但 session 相关的消息回传链路看起来还没有落地。这会导致会话虽然建立成功，后续消息无法按预期回流到 AstrBot 侧，影响 session 模式的可用性与后续联调判断。

## Solution

在后续单独起一个 phase，先明确 session 消息回传的职责边界、事件来源、状态同步方式和 AstrBot 侧展示/消费路径，再基于设计实现完整的回传链路与联调验证。
