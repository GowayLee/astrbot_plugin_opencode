## 文档定位

这是一份面向本仓库开发者的 OpenCode ACP Server 参考，用来说明 OpenCode 在 ACP 下的实际工作方式、支持范围和已知限制。

它的重点不是 IDE 配置教程，而是回答两个问题：本仓库为什么用它，以及它在 ACP 规范下具体支持到什么程度。

## 官方来源

- OpenCode ACP 文档: <https://opencode.ai/docs/zh-cn/acp/>
- OpenCode 文档站根入口: <https://opencode.ai/docs/zh-cn/>

## OpenCode 作为 ACP Server 的工作方式

- OpenCode 通过 `opencode acp` 启动一个本地 ACP Server。
- 这条链路以 `stdio` 方式工作：宿主侧拉起子进程，再通过标准输入输出交换 JSON-RPC 消息。
- 对本仓库来说，这意味着 AstrBot 插件位于 client/宿主侧，负责启动 OpenCode 进程、建立 session、发送 prompt、接收 update，并处理 permission 决策。
- 当前默认配置也直接体现了这一点：`_conf_schema.json` 中默认命令与参数等价于执行 `opencode acp`。

最小启动心智模型可以理解为：

```text
AstrBot Plugin (ACP client) -> stdio -> `opencode acp` (ACP server)
```

## 支持范围与已知限制

根据 OpenCode 官方 ACP 页面，当前可用支持面包括：

- 内置工具
- 自定义工具与斜杠命令
- MCP servers
- 项目级 `AGENTS.md` 规则
- formatters / linters
- agents
- permissions

这说明 OpenCode 不只是一个“接 prompt 的壳”，而是会把自身已有的工具、规则和执行能力暴露在 ACP 会话里。

当前已知限制也需要明确写清：

- 部分内置 slash commands 暂不支持，至少包括 `/undo` 与 `/redo`。
- 因此后续若在 AstrBot 侧暴露命令列表或做能力映射，不能默认所有 OpenCode 内建命令都能经由 ACP 使用。

## 对本仓库的意义

- 本项目采用的是本地 `stdio` ACP 链路，不做远程 ACP Server 扩展设计。
- AstrBot 插件负责 client 侧宿主集成，OpenCode 负责 server 侧代理执行；两者职责不能混淆。
- 协议层通用规则先看 `docs/references/acp/README.md`，这里重点补充的是 OpenCode 在通用 ACP 之上的具体能力与限制。
- 项目内若看到 `AGENTS.md`、permission、tool call、mode/config 等行为，都应先判断这是 ACP 通用语义，还是 OpenCode 额外提供的实现能力。
