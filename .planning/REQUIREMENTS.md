# Requirements: AstrBot-ACP 配置与交互重构

**Defined:** 2026-03-29
**Core Value:** 让 AstrBot 以自然、可控、低配置负担的方式接入 ACP Coding Agent，而不是把整套底层协议细节直接暴露给管理员和最终用户。

## v1 Requirements

### Admin Configuration

- [x] **CONF-01**: 管理员可以在 AstrBot 配置面板中完成插件初始化，而不需要理解或填写底层 ACP 协议字段
- [x] **CONF-02**: 管理员可以配置本地 ACP 启动命令、少量启动参数和启动超时
- [x] **CONF-03**: 管理员可以配置默认工作目录，作为新会话的默认执行上下文
- [x] **CONF-04**: 管理员可以通过单一开关控制插件是否允许文件写入类操作
- [x] **CONF-05**: 已有安装在升级到新配置结构后，不需要手工修补大量旧字段即可继续使用插件

### Direct Chat UX

- [ ] **CHAT-01**: 用户可以通过一个主 slash-command 直接提交自然语言任务来操控底层 Coding Agent
- [ ] **CHAT-02**: 用户在任务开始后可以立即看到“已接收/已开始”的反馈，而不需要等待最终结果
- [ ] **CHAT-03**: 用户在任务执行过程中可以看到适合 IM 环境的关键进度、权限确认和结束状态，而不是只能看到最终长文本
- [ ] **CHAT-04**: 用户可以明确地新建、结束或切换会话，以控制当前 Coding Agent 的上下文边界
- [ ] **CHAT-05**: 用户在命令使用错误或参数不完整时，可以得到清晰的帮助提示和下一步示例

### Tool Mediation

- [ ] **TOOL-01**: AstrBot 上层 Agent 可以调用插件 tool 来驱动底层 Coding Agent，而不由插件直接替上层 Agent 向用户发最终结果
- [ ] **TOOL-02**: tool 调用完成后，上层 Agent 可以拿到结构化结果，至少包含执行状态、摘要、会话标识和关键产物引用
- [ ] **TOOL-03**: tool 调用在等待权限确认、执行失败、被拒绝或被取消时，可以把这些状态以结构化形式返回给上层 Agent

### Session And State

- [x] **SESS-01**: 用户在同一聊天身份下连续发起任务时，可以延续同一底层 ACP 会话，而不会意外丢失上下文
- [x] **SESS-02**: 用户在执行 `/oc-new`、`/oc-end`、`/oc-session` 等生命周期命令后，可以得到一致且可预期的会话行为
- [x] **SESS-03**: slash-command 与 tool 调用可以复用同一套执行内核，但不会混淆彼此的输出语义或状态流

### ACP v1 Invalid Params Repair

- [x] **PHASE-02.3-01**: 插件发给 `opencode acp` 的 `initialize` 请求必须符合 ACP v1，包含 `protocolVersion`、`clientCapabilities` 与完整 `clientInfo.version`
- [x] **PHASE-02.3-02**: 插件发给 `session/new` 与 `session/load` 的 payload 必须显式携带 `mcpServers: []`，避免 OpenCode 因缺少必填字段拒绝会话建立或恢复
- [x] **PHASE-02.3-03**: 插件发给 `session/prompt` 的正式字段必须是 ACP v1 `prompt` 数组，而不是仓库旧字段 `contentBlocks`
- [x] **PHASE-02.3-04**: initialize 返回的 `agentCapabilities`、session state 的 mode/config 结构，以及 `session/update` 通知都必须被当前执行链正确消费，不再丢失恢复、mode、权限和过程消息
- [ ] **PHASE-02.3-05**: 在真实 AstrBot 宿主中执行 `/oc hello` 与 `/oc-session` 时，不再出现 `ACP 后端启动失败: opencode` 包裹的 `Invalid params`

### Safety And Permissions

- [ ] **SAFE-01**: 当管理员关闭文件写入能力时，插件会稳定阻止对应写入路径，而不是只改变提示文案
- [ ] **SAFE-02**: 当执行触发受控操作时，用户可以通过纯文本方式完成权限确认，并在超时或拒绝时默认失败关闭
- [ ] **SAFE-03**: slash-command 与 tool 调用会遵守同一套高层安全策略与 ACP permission 中介逻辑，而不会出现一条链路绕过另一条链路的情况

## v2 Requirements

### Interaction Enhancements

- **CHAT-06**: 用户可以在不中断当前会话的情况下补充 steering 指令来纠正任务方向
- **CHAT-07**: 用户可以把更多回复链、附件和工作区文件作为显式上下文注入给底层 Coding Agent

### Admin Experience

- **CONF-06**: 管理员可以直接选择预设策略模板，例如只读审查模式或写入需确认模式
- **CONF-07**: 管理员可以查看更细粒度的执行审计信息，包括高风险操作摘要和长期会话记录

### Advanced Routing

- **SESS-04**: 管理员可以为多个仓库或多个工作区配置更高级的默认路由策略

## Out of Scope

| Feature                                             | Reason                                                   |
| --------------------------------------------------- | -------------------------------------------------------- |
| 远程 ACP 服务器连接                                 | 本轮明确保持本地 `stdio` 方案，避免扩张传输层改造范围    |
| 将 slash-command 与 agent tool 拆成两套复杂权限系统 | 会显著增加配置和维护复杂度，不符合当前收敛方向           |
| 在配置面板暴露完整 ACP/OpenCode 协议字段            | 与“管理员初始化配置”目标冲突，会把面板重新做成协议调试器 |
| 富交互按钮式审批                                    | 宿主平台差异大，当前优先使用纯文本审批方案               |
| 多工作区高级路由                                    | 当前默认工作目录加显式切换已足够支撑本轮目标             |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement   | Phase      | Status               |
| ------------- | ---------- | -------------------- |
| CONF-01       | Phase 1    | Done                 |
| CONF-02       | Phase 1    | Done                 |
| CONF-03       | Phase 1    | Done                 |
| CONF-04       | Phase 1    | Done                 |
| CONF-05       | Phase 1    | Done                 |
| CHAT-01       | Phase 3    | Pending              |
| CHAT-02       | Phase 3    | Pending              |
| CHAT-03       | Phase 3    | Pending              |
| CHAT-04       | Phase 3    | Pending              |
| CHAT-05       | Phase 3    | Pending              |
| TOOL-01       | Phase 4    | Pending              |
| TOOL-02       | Phase 4    | Pending              |
| TOOL-03       | Phase 4    | Pending              |
| SESS-01       | Phase 2    | Complete             |
| SESS-02       | Phase 2    | Complete             |
| SESS-03       | Phase 2    | Complete             |
| PHASE-02.3-01 | Phase 02.3 | Complete             |
| PHASE-02.3-02 | Phase 02.3 | Complete             |
| PHASE-02.3-03 | Phase 02.3 | Complete             |
| PHASE-02.3-04 | Phase 02.3 | Complete             |
| PHASE-02.3-05 | Phase 02.3 | In manual validation |
| SAFE-01       | Phase 4    | Pending              |
| SAFE-02       | Phase 3    | Pending              |
| SAFE-03       | Phase 4    | Pending              |

**Coverage:**

- v1 requirements: 24 total
- Mapped to phases: 24
- Unmapped: 0 ✓

---

_Requirements defined: 2026-03-29_
_Last updated: 2026-03-29 after Phase 02.3 gap closure planning_
