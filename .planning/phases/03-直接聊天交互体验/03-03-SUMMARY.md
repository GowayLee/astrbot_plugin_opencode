## 完成内容

- `main.py` 新增统一短帮助渲染函数，用于命令误用场景输出“问题说明 + 示例”。
- 为 `/oc` 空输入、`/oc-mode` 非法 mode、`/oc-session` 查无会话、`/oc-send` 无有效文件这 4 条错误路径补齐可复制示例。
- `tests/test_main_commands.py` 补齐对应帮助输出回归测试。

## 验证

- `.venv/bin/python -m pytest tests/test_main_commands.py -q`
- 结果：通过
