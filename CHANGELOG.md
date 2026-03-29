# Changelog

插件的版本更新历史

## [Unreleased]

### Breaking Changes

- 插件执行模型改为 ACP-only，唯一后端为 `acp_opencode`，统一通过 `opencode acp` 启动。
- 移除旧的 local CLI / remote HTTP 连接方式，不再保留对应配置项与用户文档说明。
- 移除 `/oc-shell` 命令，后续交互统一收敛到 ACP 会话与工具权限流。

### Changed

- 插件元数据身份统一到 `astrbot_plugin_opencode / OpenCode Bridge`，修复 `metadata.yaml` 仍残留 `astrbot_plugin_acp_client / ACP Client` 导致宿主可能继续复用旧插件实例或旧配置快照的问题。
- README、插件描述和用户可见说明已全部改写为 ACP-first 叙事，补充 `/oc-agent`、`/oc-mode`、权限确认流和会话绑定语义。
- 配置说明同步为当前 WebUI 实际保留的高层字段，仅保留 `only_admin`、ACP 启动参数、默认工作目录、代理、文件写入开关、清理周期与确认超时。
- 新增“面板同步排查基线”：明确 AstrBot 通过插件目录中的 `metadata.yaml` 识别插件，通过同目录 `_conf_schema.json` 生成配置面板，并把配置实体写入 `data/config/<plugin_name>_config.json`。
- 升级说明补充旧面板排查路径，优先检查旧插件副本、旧插件 ID/显示名和宿主缓存是否仍在生效，避免把宿主加载问题误判为 schema 回退。
- 新增真实宿主联调检查单，明确升级后应在 WebUI 中看到 `OpenCode Bridge`、版本 `1.3.1` 与 9 个当前 schema 字段。

## [1.3.0] - 2026-02-25

### Changed

- 执行结果输出配置增强：新增 `merge_forward_enabled` 开关（默认关闭）。关闭后将按顺序逐条发送命中的积木；其中 `full_text` 会单独以一次合并转发发送，兼顾可读性与防刷屏。
- 长文本阈值策略增强：新增 `smart_trigger_ai_summary`、`smart_trigger_txt_file`、`smart_trigger_long_image` 三个智能触发开关（默认开启）。开启时对应积木仅在超过阈值时出现；关闭时只要积木被勾选就总是出现。
- 输出发送路径统一为“发送计划”模式，`/oc`、`/oc-shell` 与 LLM 工具后台推送在非合并模式下支持顺序分条发送并增加轻量发送间隔，降低风控风险。
- `/oc-send` 交互增强：无参数时可递归分页列出当前工作区文件，并支持 `--page`、`--find` 浏览；支持按阿拉伯数字序号/范围（如 `1,3-5`）快速发送一个或多个文件。
- `/oc-send` 新增相对路径多文件发送，同时保持绝对路径发送的向后兼容能力；批量发送时会汇总未发送项并给出原因。
- 针对超大目录增加防护：文件列表扫描上限与分页输出，避免在工作目录选到根目录时产生超长回复或扫描过慢问题。

## [1.2.0] - 2026-02-24

### Added

- 新增双连接模式配置：
  - `connection_mode`：支持 `local`（本地）/ `remote`（服务器）两种模式切换。
  - `remote_server_url`、`remote_username`、`remote_password`、`remote_timeout`：用于远程 OpenCode Server 连接。
- 新增远程模式执行能力：在 `remote` 模式下，通过 HTTP API 连接 OpenCode Server，支持会话创建、消息发送与会话列表查询。

### Changed

- 执行器升级为模式感知：`/oc`、`/oc-session` 自动根据连接模式路由到本地 CLI 或远程 API。
- 插件初始化流程增加连接健康检查并输出模式信息，便于排障。
- `/oc-shell` 明确为仅本地模式可用；在远程模式下返回清晰提示，避免误操作。
- README 增补双模式配置与行为说明，提升配置可读性。
- 新增 remote 模式输入保护：当任务中包含本机路径/本地缓存资源引用时，自动拦截并给出引导，避免把本地文件路径误传给远端执行。
- 远程模式下执行状态与 `/oc-new` 提示文案明确区分“本地缓存目录”与“本地模式工作目录”，减少目录语义误解。

### Compatibility

- 默认模式仍为 `local`，现有本地部署用户无需改配置即可保持原有行为。

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
