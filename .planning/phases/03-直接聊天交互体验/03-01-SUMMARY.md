## 完成内容

- `main.py` 为 `/oc` 流式执行增加正文 chunk 缓冲与 flush 逻辑，按 120 字符 / 换行 / 1.2 秒阈值合并回传。
- `core/output.py` 保留并合并 `message_chunk`，同时在最终结果阶段对已流式回传的正文做去重。
- `tests/core/test_executor_acp.py`、`tests/core/test_output_events.py`、`tests/test_main_commands.py` 补齐流式正文、关键节点和最终结果去重回归。

## 验证

- `.venv/bin/python -m pytest tests/core/test_executor_acp.py tests/core/test_output_events.py tests/test_main_commands.py -q`
- 结果：通过
