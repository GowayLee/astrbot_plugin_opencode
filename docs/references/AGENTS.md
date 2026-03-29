# OVERVIEW

- `docs/references/` 存放本项目开发参考，不存放终端用户教程。
- 这里的内容服务后续实现和规划，目标是帮助执行者快速找到规范入口与本仓库相关点。

# RULES

- 官方原文优先，仓库整理稿不替代规范。
- 更新文档前先核对官方原文链接与当前仓库实现。
- 优先维护单文件主文档：每个来源目录先保留一个 `README.md` 作为主入口。
- 只有在单文件主文档已经无法承载内容时，才新增碎片文件，而且必须有明确理由。
- 总结说明保持中文，外链来源写清楚，不要写成模糊的“见官方文档”。

# MAINTENANCE

- 修改 `astrbot/README.md` 时，优先核对 AstrBot 官方插件开发指南与 `main.py`、`_conf_schema.json` 的对应关系。
- 修改 `acp/README.md` 时，优先核对 ACP 官方协议页面与 `core/acp_client.py`、`core/acp_adapter.py`、`core/acp_models.py` 的对应关系。
- 修改 `opencode/README.md` 时，优先核对 OpenCode ACP 官方页面与本仓库当前采用的本地 `stdio` 集成方式。
