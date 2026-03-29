---
created: 2026-03-29T17:52:14.207Z
title: 梳理 /oc-mode 在 ACP 与 OpenCode 中的含义
area: general
files:
  - main.py:968-1032
  - docs/references/acp/README.md:20-21
  - docs/references/opencode/README.md:12-49
---

## Problem

当前仓库已经暴露了 `/oc-mode` 命令，并在 `main.py` 中同时处理 `modes` 与 `configOptions(category=mode)` 两类后端返回值，但这个 mode 到底代表什么还不清楚。现在至少存在三层语义需要对齐：插件里 `/oc-mode` 想让管理员切换的是什么、ACP `Session Modes` 规范中的 mode 是什么、OpenCode 作为 ACP Server 时实际把哪些能力暴露成 mode 或 config option。这个边界如果不先弄清楚，后续继续做 mode 展示、默认值持久化、文案解释或能力映射时，很容易把协议语义、OpenCode 特有能力和插件侧 UX 混在一起。

## Solution

先对照 ACP 官方 `Session Modes` 规范与仓库中的参考文档，明确 mode 在协议层的职责；再回到 `main.py` 当前 `/oc-mode` 的实现，梳理它是如何在 `modes` 与 `configOptions` 间做回退和写回的。最后补一份映射结论：`/oc-mode` 当前实际控制的是哪一层配置、ACP 中对应的对象/能力是什么、OpenCode 上下文里 mode 与 agent、permission、tool/config 的关系分别是什么；如发现现有命令名或展示文案会误导，再给出后续调整建议。
