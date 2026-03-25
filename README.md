# AstrBot Plugin: OpenCode Bridge

让 AstrBot 对接 [OpenCode](https://github.com/anomalyco/opencode)，通过 ACP 会话在聊天里驱动智能体完成编程、文档和文件相关任务。
本项目使用 OpenCode 构建。

使用过程中若有问题或宝贵意见，欢迎发布 issue、提交 PR。

## 功能特性

- **ACP only**：插件只保留 `acp_opencode` 一条执行路径，统一以 `opencode acp` 作为后端入口
- **自然语言控制**：通过 `/oc` 在聊天里持续驱动 OpenCode agent 执行任务
- **Agent 与 Mode 分离**：支持 `/oc-agent` 管默认 agent，`/oc-mode` 管当前 mode / config option 偏好
- **多模态输入**：支持图片、文件、引用消息作为任务上下文
- **权限确认流**：前置安全检查 + ACP 权限请求二次确认，默认超时即取消
- **会话连续性**：同一用户多次 `/oc` 自动复用当前 ACP 会话上下文
- **会话管理**：支持列出、绑定历史 ACP 会话，并保留当前工作目录偏好
- **多种输出模式**：文本摘要、长图渲染、TXT 文件、合并转发
- **安全机制**：管理员权限、敏感操作确认、可配置关键词拦截、路径安全检查
- **历史记录**：自动记录使用过的工作目录，方便回溯

## 安装

### 前置条件

1. 安装 [OpenCode CLI](https://opencode.ai) 并确保终端可运行 `opencode` 命令
2. AstrBot v4.5.7 或更高版本

### 安装步骤

1. 在 AstrBot WebUI 插件市场搜索 `opencode` 安装
2. 或手动将插件文件夹放入 `data/plugins/` 目录
3. 重启 AstrBot 并在管理面板启用插件

## 快速开始

1. 在插件配置中确认后端保持为 `acp_opencode`
2. 默认启动命令保持 `acp_command=opencode`、`acp_args=["acp"]`
3. 先发 `/oc 你好，你是谁`
4. 再发 `/oc 当前工作目录是什么`
5. 如需切目录，执行 `/oc-new /tmp/demo-acp`
6. 如需切默认 agent，执行 `/oc-agent plan`
7. 如需切 mode，执行 `/oc-mode ask`

## 指令

| 指令 | 说明 | 示例 |
|------|------|------|
| `/oc <任务>` | 执行自然语言任务，默认延续当前 ACP 会话上下文 | `/oc 查看当前目录下的文件` |
| `/oc-agent [名称]` | 查看或设置默认 agent；已有 live session 时本轮不强切 | `/oc-agent`、`/oc-agent plan` |
| `/oc-mode [值]` | 查看或设置 mode / config option；后端支持时会同步作用到当前 live session | `/oc-mode`、`/oc-mode ask` |
| `/oc-new [路径]` | 解绑当前 ACP 会话，并为下一次新会话更新工作目录 | `/oc-new D:\Projects` |
| `/oc-end` | 仅结束当前 ACP 会话绑定，保留工作目录与默认偏好 | `/oc-end` |
| `/oc-session [序号/ID/标题]` | 查看、绑定历史 ACP 会话 | `/oc-session`、`/oc-session 1` |
| `/oc-send [参数]` | 列出并发送 AstrBot 宿主机文件 | `/oc-send`、`/oc-send 1,3`、`/oc-send src/a.py` |
| `/oc-clean` | 手动清理临时文件 | `/oc-clean` |
| `/oc-history` | 查看工作目录使用历史 | `/oc-history` |

## 会话语义

- **`/oc`**：首次执行会创建 ACP 会话；后续继续复用同一会话，保持上下文
- **`/oc-new`**：解绑当前会话；如果带路径，则更新下一次建会话时使用的工作目录
- **`/oc-end`**：只解绑当前会话与待确认权限，不改工作目录、默认 agent、默认 mode
- **`/oc-agent <name>`**：更新默认 agent；当前 live session 不会被强制切换，下一次新会话生效
- **`/oc-mode <value>`**：优先按 backend 暴露的 `configOptions(category=mode)` 切换；若没有，再回退到 `modes`
- **`/oc-session`**：无参数时列最近会话；传入序号、ID 或标题后绑定对应 ACP 会话
- **历史会话绑定规则**：绑定旧会话只切换 `backend_session_id`，不会从历史会话倒推旧的工作目录；当前 sender 的 `work_dir` 仍然保持不变

## 权限与安全

插件的安全策略分成两层：

1. **前置安全检查**：管理员校验、敏感关键词确认、可选路径安全限制
2. **ACP 权限请求**：当后端发起 `session/request_permission` 时，插件会在聊天里给出编号选项，等待用户回复

### 权限确认流

- 插件收到权限请求后，会展示工具标题、工具类型、关键路径或命令摘要
- 常见选项会映射成中文提示，例如“允许一次”“始终允许”“拒绝一次”“始终拒绝”
- 用户按编号或中文别名回复即可
- 超时、取消或无效响应默认按拒绝处理
- `allow_always` 仅作用于当前 ACP 会话，不做跨重启永久记忆

## 配置项

在 AstrBot WebUI 中配置：

### 基础配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `only_admin` | 仅管理员可用 | `true` |
| `backend_type` | 后端类型，当前固定为 `acp_opencode` | `acp_opencode` |
| `acp_command` | ACP 启动命令 | `opencode` |
| `acp_args` | ACP 启动参数 | `["acp"]` |
| `acp_startup_timeout` | ACP 启动与握手超时（秒） | `30` |
| `acp_client_capabilities` | 初始化时上报的 ACP 客户端能力 | `{"fs_read_text": true, "fs_write_text": true, "terminal": true}` |
| `default_agent` | 新会话默认 agent | `build` |
| `default_mode` | 新会话默认 mode | `ask` |
| `default_config_options` | 新会话默认 config option 键值对 | `{}` |
| `work_dir` | 默认工作目录 | (插件数据目录下的 workspace) |
| `proxy_url` | 代理地址 | (空) |
| `destructive_keywords` | 敏感操作关键词（正则） | `删除`, `rm`, `delete` 等 |
| `confirm_all_write_ops` | 写操作需确认 | `true` |
| `check_path_safety` | 文件路径安全检查 | `false` |
| `auto_clean_interval` | 自动清理间隔（分钟） | `60` |
| `confirm_timeout` | 敏感操作确认超时（秒） | `30` |

### 输出配置

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `output_modes` | 输出方式（多选） | `ai_summary`, `txt_file`, `long_image`, `full_text` |
| `merge_forward_enabled` | 是否启用合并转发发送 | `false` |
| `summary_provider` | AI 摘要服务提供商 | (空) |
| `max_text_length` | 长文本阈值 | `1000` |
| `smart_trigger_ai_summary` | `ai_summary` 是否按阈值智能触发 | `true` |
| `smart_trigger_txt_file` | `txt_file` 是否按阈值智能触发 | `true` |
| `smart_trigger_long_image` | `long_image` 是否按阈值智能触发 | `true` |

**可选输出模式**：
- `last_line`：显示文本末段（长文本自动截断）
- `ai_summary`：AI 智能摘要
- `txt_file`：生成 TXT 文件
- `long_image`：渲染为代码风格长图
- `full_text`：全量文本（超阈值按 `max_text_length` 自动切分）

### LLM 工具配置

| 配置项 | 说明 |
|--------|------|
| `tool_description` | Function Tool 描述（影响 AI 何时调用） |
| `arg_description` | 参数描述 |

## `/oc-send` 说明

- `/oc-send` 发送的是 **AstrBot 插件宿主机可访问** 的文件
- 它用于把当前工作区或指定路径的文件发回聊天，不是 ACP 内部文件浏览器
- 若开启 `check_path_safety`，插件会限制可访问范围，防止误发敏感路径

## 破坏性升级说明

从旧版本升级到当前 ACP-only 版本时，需要注意：

- 已移除旧的本地 CLI / 远程 HTTP 双路径说明与配置
- 已移除 `/oc-shell`
- 插件只认 ACP-only 配置模型，不再承接 legacy 连接字段
- 文档、命令说明与会话语义全部改为 ACP-first 叙事

如果你之前依赖旧配置，请在升级后重新检查 WebUI 中的插件配置，确认只保留 ACP 相关字段。

## 安全说明

本插件赋予机器人对宿主电脑的操作权限，请注意：

1. **保持 `only_admin` 为 `true`**
2. **敏感操作和写操作都应结合确认流使用**
3. **建议在隔离环境运行**，如 Docker 容器或专用开发机
4. **定期检查日志**，确认无异常操作
5. **对 `/oc-send` 启用路径安全检查** 时，可进一步降低误发系统敏感文件的风险

## 工作目录历史

插件会自动记录所有使用过的工作目录到 `data/plugin_data/astrbot_plugin_opencode/workdir_history.json`。

历史记录包含：
- 路径
- 首次使用时间
- 最后使用时间
- 使用次数
- 使用者 ID

使用 `/oc-history` 可查看最近使用的 10 个工作目录。

## 用例

<table>
  <tr>
    <td align="center">
      <img src="./screenshots/image1.jpg" width="100%" />
      <br/>
      <strong></strong>
    </td>
    <td align="center">
      <img src="./screenshots/image2.jpg" width="75%" />
      <br/>
      <strong></strong>
    </td>
    <td align="center">
      <img src="./screenshots/image3.jpg" width="100%" />
      <br/>
      <strong></strong>
    </td>
  </tr>
</table>

<details>
<summary>点击此处展开</summary>

### 1) 主入口：持续对话执行（`/oc`）
```text
用户: /oc 帮我创建一个 Python 项目骨架，并生成 README
机器人: 🚀 开始执行任务
机器人: ✅ 已完成项目初始化，并继续保留当前 ACP 会话上下文
```

### 2) 多模态输入：图片/引用消息参与任务
```text
用户: [发送截图] /oc 按这张图复刻页面并保存为 index.html
机器人: 🚀 开始执行任务
机器人: ✅ 已完成页面生成并写入 index.html
```

### 3) Agent 与 Mode 偏好
```text
用户: /oc-agent plan
机器人: ✅ 已更新默认 agent

用户: /oc-mode ask
机器人: ✅ 已更新 mode 偏好
```

### 4) 会话重置与目录切换（`/oc-new` / `/oc-end`）
```text
用户: /oc-new D:\Projects\demo
机器人: ✅ 已重置当前 ACP 会话绑定

用户: /oc-end
机器人: 🚫 已结束当前 ACP 会话绑定
```

### 5) 历史会话绑定（`/oc-session`）
```text
用户: /oc-session
机器人: 📋 ACP 会话列表

用户: /oc-session 1
机器人: ✅ 已绑定 ACP 会话
```

### 6) 权限确认流
```text
用户: /oc 再创建一个 hello.txt 文件
机器人: ⚠️ 权限确认：展示工具、路径摘要和可选项
用户: 1
机器人: ✅ 已继续执行
```

### 7) 文件发送与路径安全（`/oc-send`）
```text
用户: /oc-send
机器人: 📄 列出当前工作区文件（分页，带阿拉伯数字序号）

用户: /oc-send 1,3-5
机器人: [按序号发送多个文件]
```

### 8) 输出与运维（`/oc-clean` / `/oc-history`）
```text
用户: /oc-clean
机器人: 🧹 清理完成，返回释放空间

用户: /oc-history
机器人: 📂 显示最近工作目录使用记录
```

</details>
