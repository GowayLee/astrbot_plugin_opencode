---
phase: quick-260329-suy-metadata-yaml-opencode
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - main.py
  - tests/test_main_commands.py
autonomous: true
requirements:
  - Q-IDENTITY-01
must_haves:
  truths:
    - "AstrBot 注册出来的插件身份与 metadata.yaml 完全一致，不再额外宣称 OpenCode Bridge 身份"
    - "代码里的插件标识、展示名、作者与测试断言都以 metadata.yaml 为准"
    - "与 OpenCode 相关的文案只保留在功能描述层，不再混入插件身份层"
  artifacts:
    - path: "metadata.yaml"
      provides: "当前插件身份基线"
      contains: "plugin_id: astrbot_plugin_acp"
    - path: "main.py"
      provides: "AstrBot register 常量与启动日志"
      contains: "PLUGIN_ID"
    - path: "tests/test_main_commands.py"
      provides: "插件身份回归测试"
      contains: "test_metadata_identity_matches"
  key_links:
    - from: "metadata.yaml"
      to: "main.py"
      via: "PLUGIN_* 常量 / @register 参数"
      pattern: "PLUGIN_ID|PLUGIN_DISPLAY_NAME|PLUGIN_AUTHOR|PLUGIN_DESCRIPTION|PLUGIN_REPO"
    - from: "tests/test_main_commands.py"
      to: "metadata.yaml"
      via: "metadata identity regression assertion"
      pattern: "plugin_id|display_name"
---

<objective>
把运行时代码里的插件身份重新对齐到 `metadata.yaml`，避免继续以 OpenCode Bridge / astrbot_plugin_opencode 作为对外身份。

Purpose: 当前仓库里 `metadata.yaml` 与 `main.py`/测试的插件身份相互冲突。按本次需求，`metadata.yaml` 是最新基线，执行时应以它为准，只修正“身份层”的命名漂移，不扩大到命令语义或 ACP/OpenCode 功能实现。

Output: 与 `metadata.yaml` 一致的运行时插件常量 + 防回归测试。
</objective>

<execution_context>
@./AGENTS.md
@./core/AGENTS.md
</execution_context>

<context>
@.planning/STATE.md
@metadata.yaml
@main.py
@tests/test_main_commands.py

<interfaces>
From metadata.yaml:

```yaml
plugin_id: astrbot_plugin_acp
name: astrbot_plugin_acp
display_name: ACP Client
author: Hauryn Lee
version: 1.3.1
description: 让 AstrBot 通过 ACP 会话对接 OpenCode 等智能体，在聊天中完成编程与文件任务。使用此插件，意味着你已知晓相关风险。
repo: https://github.com/GowayLee/astrbot_plugin_opencode
```

From main.py:

```python
PLUGIN_ID = "astrbot_plugin_opencode"
PLUGIN_DISPLAY_NAME = "OpenCode Bridge"
PLUGIN_AUTHOR = "GowayLee"
PLUGIN_DESCRIPTION = "让 AstrBot 通过 ACP 会话对接 OpenCode 智能体，在聊天中完成编程与文件任务。使用此插件，意味着你已知晓相关风险。"
PLUGIN_VERSION = "1.3.1"
PLUGIN_REPO = "https://github.com/GowayLee/astrbot_plugin_opencode"
```

```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: 先把 metadata 视为权威，补齐身份回归测试</name>
  <files>tests/test_main_commands.py</files>
  <behavior>
    - metadata 中的 plugin_id/name/display_name/author 必须与 main.py 中对外身份常量一致
    - 测试应在代码仍保留 `astrbot_plugin_opencode` / `OpenCode Bridge` 作为插件身份时失败
    - 测试只约束“插件身份层”，不禁止描述功能时提到 OpenCode
  </behavior>
  <action>更新现有 metadata identity 测试，把断言基线改为 `metadata.yaml` 当前值：`astrbot_plugin_acp`、`ACP Client`、`Hauryn Lee`。同时让测试明确区分“插件身份”和“功能描述”：允许描述里出现 OpenCode，但不允许 `PLUGIN_ID`、展示名、作者等身份常量继续漂移到旧的 opencode/open bridge 身份。</action>
  <verify>
    <automated>python3 -m pytest tests/test_main_commands.py -k "metadata_identity"</automated>
  </verify>
  <done>测试能稳定卡住后续实现范围：只有当 main.py 的插件身份与 metadata.yaml 一致时才通过。</done>
</task>

<task type="auto">
  <name>Task 2: 收敛 main.py 的插件身份常量与对外标识</name>
  <files>main.py</files>
  <action>把 `main.py` 中属于插件身份层的常量与相关启动/终止日志文案改到与 `metadata.yaml` 一致：`PLUGIN_ID`、展示名、作者、描述、以及任何直接宣称插件名为 OpenCode Bridge/OpenCode Plugin 的对外标识都要同步。保留 `/oc` 命令名、ACP/OpenCode 后端能力、类名 `OpenCodePlugin` 与业务实现不动，除非它们直接参与 AstrBot 的插件注册身份；本任务目标是修正宿主识别与展示身份，不是重命名整套功能语义。</action>
  <verify>
    <automated>python3 -m pytest tests/test_main_commands.py -k "metadata_identity"</automated>
  </verify>
  <done>`@register` 使用的插件身份与 metadata.yaml 完全一致，代码里不再把 OpenCode Bridge / astrbot_plugin_opencode 当作插件对外身份。</done>
</task>

</tasks>

<verification>
- 运行 `python3 -m pytest tests/test_main_commands.py -k "metadata_identity"`
- 抽查 `main.py` 的 `PLUGIN_*` 常量是否逐项对应 `metadata.yaml`
</verification>

<success_criteria>
- AstrBot 插件注册身份与 `metadata.yaml` 一致
- 回归测试可以阻止身份再次漂移回 `astrbot_plugin_opencode` / `OpenCode Bridge`
- 本次修改不扩散到命令名、ACP 执行链路或 OpenCode 功能叙述
</success_criteria>

<output>
After completion, create `.planning/quick/260329-suy-metadata-yaml-opencode/260329-suy-SUMMARY.md`
</output>
```
