## 文档定位

这是一份面向本仓库开发者的 AstrBot 插件开发参考手册，用来快速定位宿主框架能力与本仓库实现入口。

它不替代 AstrBot 官方文档；当你要确认真实 API、参数格式或生命周期细节时，仍应回到官方原文。

## 官方来源

AstrBot 官方插件开发指南目录：

- 根入口: <https://github.com/AstrBotDevs/AstrBot/tree/master/docs/zh/dev/star/guides>
- 最小插件与注册: `simple.md`
- 配置面板与 schema: `plugin-config.md`
- 会话控制: `session-control.md`
- 消息发送: `send-message.md`
- 监听消息事件: `listen-message-event.md`
- AI 能力接入: `ai.md`
- 存储能力: `storage.md`
- 环境变量与运行时补充: `env.md`
- HTML 转图片: `html-to-pic.md`
- 其他补充能力: `other.md`

## 本仓库最相关的开发主题

### 1. 插件入口与注册

- 本仓库的宿主入口在 `main.py`。
- `OpenCodePlugin` 通过 `@register(...)` 注册到 AstrBot，并在初始化时组装 `SessionManager`、`StorageManager`、`SecurityChecker`、`InputProcessor`、`CommandExecutor`、`OutputProcessor`。
- 这部分最对应 AstrBot 官方的 `simple.md` 与插件基础生命周期说明。

### 2. 配置 schema 与面板约束

- 本仓库把 AstrBot 面板配置契约收敛在 `_conf_schema.json`。
- 运行时虽然会在 `main.py` 中补齐默认值，但配置字段本身仍应以 `_conf_schema.json` 为准。
- 这部分最对应 `plugin-config.md`，也是后续调整配置项时必须先核对的文档。

### 3. 消息发送与命令反馈

- `/oc`、`/oc-new`、`/oc-end`、`/oc-session`、`/oc-send` 等命令都在 `main.py` 协调处理。
- 发送文本、文件和执行状态反馈时，应优先对照 `send-message.md`。
- 需要理解消息事件入口和命令触发链路时，再配合 `listen-message-event.md` 一起看。

### 4. 会话控制

- 本仓库会话语义由 `main.py` 和 `core/session.py` 共同维护，但宿主侧会话等待与确认交互仍依赖 AstrBot 的会话控制能力。
- 需要修改确认流、等待用户回复、会话切换提示时，重点看 `session-control.md`。

### 5. 存储与 AI 能力

- `core/storage.py` 负责工作目录历史与清理行为，对应 `storage.md`。
- 与 AI、平台能力或 AstrBot 运行时能力相关的补充接入，可参考 `ai.md`、`env.md`、`other.md`。

## 阅读顺序

1. 先看 `simple.md`
   明确 AstrBot 插件的基本结构、注册方式和事件处理入口。
2. 再看 `plugin-config.md`
   明确 `_conf_schema.json` 应如何表达配置字段、默认值和提示文案。
3. 然后看 `send-message.md` 与 `session-control.md`
   这两篇直接对应本仓库的命令反馈、确认等待、会话切换和用户提示。
4. 最后看 `listen-message-event.md`、`ai.md`、`storage.md`
   用于补齐事件流、AI 接入和持久化/清理等边界知识。

## 使用方式

- 以官方原文为规范基线，仓库文档只做摘要、导航和与本仓库代码的映射。
- 如果你要修改 `main.py` 的命令行为，先回看这里，再打开相关官方文档核对 API 细节。
- 如果你要调整 `_conf_schema.json`，默认值、字段含义和文案都应与官方配置模型保持一致，不要只根据运行时实现猜测。
