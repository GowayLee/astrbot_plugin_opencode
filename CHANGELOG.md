# Changelog

插件的版本更新历史

## [1.1.0] - 2025-02-03

### Fixed

- **修复 LLM 工具调用超时问题**：当 AI 通过 `call_opencode` 函数工具调用 OpenCode 时，由于 AstrBot 框架对 LLM 工具有 60 秒默认超时限制，长时间运行的任务会被强制终止且无法返回结果。
  - 现改为后台异步执行模式：工具立即返回，OpenCode 在后台运行，完成后通过主动推送将结果发送给用户。
  - 支持任意时长的任务执行（不再受 60 秒限制）。

### Changed

- `call_opencode_tool` 函数重构：
  - 消息发送从 `yield` 改为 `await event.send()`，直接发送而非通过框架代理。
  - 新增 `_execute_opencode_background` 方法处理后台执行和结果推送。
  - 工具不再返回内容，避免 AI 额外回复。

## [1.0.0] - 2025-02-01

### Added

- 初始版本发布
