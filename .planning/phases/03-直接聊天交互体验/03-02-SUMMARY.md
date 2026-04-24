## 完成内容

- `core/output.py` 将权限确认消息改为多行结构，包含操作、目标和编号选项，适配 IM 场景。
- `main.py` 收敛 `/oc-new`、`/oc-end`、`/oc-session` 的生命周期回显，只默认展示工作目录、当前会话、当前 agent、当前 mode。
- 补充权限选项映射与生命周期摘要回归测试，确保不再展开默认 agent/default mode/proxy 等常规噪音字段。

## 验证

- `.venv/bin/python -m pytest tests/core/test_output_events.py tests/test_main_commands.py -q`
- 结果：通过
