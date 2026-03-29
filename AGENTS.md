# OVERVIEW

- AstrBot plugin that bridges chat commands to OpenCode, either through the local CLI or a remote OpenCode Server.
- `main.py` is the orchestration hub: AstrBot registration, command handlers, manager wiring, mode-aware guards, and the LLM tool entry.
- The repo is mostly runtime plumbing rather than domain logic: session continuity, prompt assembly, execution backend selection, safety checks, and output fan-out.
- Treat `_conf_schema.json` as the config contract and default-value authority. If behavior changes, schema and code should move together.
- User-facing copy is mostly Chinese; keep replies, hints, and warnings aligned with the existing tone.
- There is no in-repo test suite or CI. Keep changes small and leave a clear manual verification path through plugin commands.

# STRUCTURE

- `main.py` - plugin entrypoint and top-level workflow coordinator; owns commands like `/oc`, `/oc-shell`, `/oc-send`, `/oc-new`, `/oc-end`, `/oc-clean`, `/oc-history`, `/oc-session`, plus the `call_opencode` tool.
- `core/` - runtime manager layer; this is where execution, state, safety, input, output, persistence, and cleanup are split by responsibility.
- `core/executor.py` - local CLI vs remote HTTP execution, remote health/session APIs, shell execution, JSON output parsing.
- `core/session.py` - per-sender in-memory state: workdir, environment, OpenCode session ID, and related continuity helpers.
- `core/security.py` - admin gating, destructive keyword detection, write-op confirmation triggers, and optional path safety policy.
- `core/input.py` - quoted message/media ingestion and `downloaded/` file materialization before OpenCode sees the prompt.
- `core/output.py` - output normalization, ANSI cleanup/rendering, AI summary/TXT/long-image generation, and send-plan construction.
- `core/storage.py` - workdir history persistence and background cleanup of downloaded files and generated output logs.
- `core/utils.py` - small sync file-write helpers used via thread offload from async code.
- `assets/long_text.html` - HTML template used only for long-image rendering.
- `_conf_schema.json` - plugin settings, descriptions, defaults, and output toggle definitions used by AstrBot config UI.
- `.opencode/` - contributor-local OpenCode tooling area with config, plugin dependency manifest, lockfile, and generated `node_modules/`; not plugin runtime source.
- `README.md`, `CHANGELOG.md`, `metadata.yaml` - packaging and user-facing behavior docs; update when setup, semantics, or release notes change.
- `screenshots/`, `logo.png` - docs/presentation assets only.

# SUBAGENT HIERARCHY

- Start with this root file for repo-wide rules, command map, and cross-cutting behavior.
- If you are working under `core/`, read `core/AGENTS.md` first; it owns local manager boundaries and runtime implementation guidance.
- `docs/references/` 中有完整的ACP, opencode, Astrbot 的文档
- Closest-child rule: when a child `AGENTS.md` exists, prefer it over parent guidance for that subtree.
- Current hierarchy:
  - `AGENTS.md`
  - `core/AGENTS.md`
  - `docs/references/AGENTS.md`

# SEARCH STRATEGY

- **Preferred**: Use `contextweaver_codebase-retrieval` (semantic search) for exploring code structure, understanding behavior, or finding related code. It combines semantic understanding with exact symbol matching.
- **Fallback**: Use `grep` only when you need exhaustive text matching (e.g., "find ALL occurrences of a string").
- **Avoid**: Don't use `find` for file discovery—use `glob` for pattern-based file searches instead.

# WHERE TO LOOK

- Command behavior, AstrBot lifecycle, or cross-manager wiring: `main.py`
- Local vs remote backend differences, subprocess calls, remote session APIs: `core/executor.py`
- Session continuity, workdir changes, per-user state: `core/session.py`
- Admin checks, destructive-op detection, path safety rules: `core/security.py`
- Media/reply ingestion and prompt construction: `core/input.py`
- Formatting, truncation, summary generation, TXT export, long-image rendering, merge-forward behavior: `core/output.py`
- Workdir history, temp cleanup, retention behavior: `core/storage.py`
- Config defaults and UI-exposed switches: `_conf_schema.json`
- User-facing semantics for commands and remote/local behavior: `README.md`

# CODE MAP

- `OpenCodePlugin` in `main.py` constructs `SessionManager`, `StorageManager`, `SecurityChecker`, `InputProcessor`, `CommandExecutor`, and `OutputProcessor`, then wires their callbacks.
- `/oc` is the primary task path: preprocess input, block unsafe remote-local path mixes, apply confirmation logic, then execute via OpenCode.
- `/oc-shell` is a deliberate local-only escape hatch for native shell commands.
- `/oc-send` handles recursive file listing, paging/filtering, path resolution, optional path-safety gating, and file emission.
- `/oc-new`, `/oc-end`, `/oc-session` control conversation/session lifecycle rather than generic command execution.
- `/oc-clean` and `/oc-history` surface storage and retention state managed by `core/storage.py`.
- `call_opencode` reuses the same execution/output path as chat commands; background tool behavior should stay consistent with foreground commands.
- `core/output.py` turns one execution result into one or more outbound AstrBot messages based on config-driven output blocks.

# CONVENTIONS

- Preserve the local/remote split explicitly. Remote mode is not a transparent alias for local execution.
- When changing config-driven behavior, update `_conf_schema.json` in the same patch or first.
- Keep user-visible strings primarily in Chinese unless the surrounding context is already English-only.
- Prefer extending the existing manager in `core/` instead of growing `main.py` further.
- Reuse the existing confirmation flow and AstrBot reply style; do not invent parallel approval UX.
- Output changes should be wired through both `_conf_schema.json` and `core/output.py`.
- Treat workdir, plugin data dir, and history entries as separate concepts with different safety implications.

# ANTI-PATTERNS (THIS PROJECT)

- Do not hardcode config defaults in Python when `_conf_schema.json` already defines them.
- Do not enable `/oc-shell` in remote mode or silently fall back to local behavior.
- Do not allow remote mode to accept local file-path references; the guard is intentional.
- Do not bypass destructive confirmation, admin checks, or optional path-safety checks for convenience.
- Do not treat `.opencode/` as runtime source or edit its generated `node_modules/`.
- Do not commit secrets anywhere in the repo; `.opencode/opencode.jsonc` currently contains a literal GitHub token and should be treated as compromised.
- Do not shift long-image behavior away from `assets/long_text.html` plus `core/output.py` without a concrete need.

# UNIQUE STYLES

- Replies are operational and chat-facing: short status lines, emoji markers, explicit outcome, low fluff.
- Safety messaging is direct: detect risk, explain why, ask for confirmation, and fail closed on timeout/cancel.
- Remote mode wording should clearly state that local cache paths are not remotely accessible.
- Output handling is intentionally composable: summary, full text, TXT, long image, and merge-forward are a configurable pipeline, not one formatter.
- History and cleanup are user-visible behavior, not hidden housekeeping; preserve that mental model.

# COMMANDS

- Install runtime deps: `pip install -r requirements.txt`
- Start local OpenCode server for remote-mode testing: `opencode serve`
- Main chat entry: `/oc <任务>`
- Session reset / directory switch: `/oc-new [路径]`
- End only the current conversation context: `/oc-end`
- Inspect or switch OpenCode sessions: `/oc-session [序号/ID/标题]`
- Native shell execution in local mode only: `/oc-shell <命令>`
- List or send files from the current workspace: `/oc-send`, `/oc-send --page 2`, `/oc-send --find config`
- Manual cleanup / history inspection: `/oc-clean`, `/oc-history`

# NOTES

- `assets/long_text.html` is a rendering template only; do not turn it into a general asset bucket.
- Remote mode uses HTTP session/message APIs; local mode uses subprocess CLI plus persisted session IDs. Keep retries and fallbacks mode-specific.
- `core/security.py` is high-sensitivity code even when edits look small; regex changes can alter confirmation coverage.
- `check_path_safety` defaults to permissive behavior unless enabled in config; be explicit when changing that contract.
- Because there is no automated safety net here, document manual verification steps in PRs or change notes when behavior shifts.

<!-- GSD:profile-start -->
## Developer Profile

> Generated by GSD from session_analysis. Run `/gsd:profile-user --refresh` to update.

| Dimension | Rating | Confidence |
|-----------|--------|------------|
| Communication | conversational | HIGH |
| Decisions | deliberate-informed | MEDIUM |
| Explanations | detailed | HIGH |
| Debugging | hypothesis-driven | MEDIUM |
| UX Philosophy | backend-focused | MEDIUM |
| Vendor Choices | pragmatic-fast | LOW |
| Frustrations | instruction-adherence | MEDIUM |
| Learning | guided | HIGH |

**Directives:**
- **Communication:** 使用中文回复，保持中等长度的对话式交流风格。
- **Decisions:** 在涉及架构设计或复杂逻辑的决策前，先提供分析和方案对比。
- **Explanations:** 在修改代码前，主动提供相关模块的执行逻辑和设计意图分析。
- **Debugging:** 当开发者提出bug假设或分析结论时，先验证其正确性再提出修复方案。
- **UX Philosophy:** 优先关注功能实现和系统架构，除非开发者明确要求UI改进。
- **Vendor Choices:** 推荐常用的、维护良好的库，不要过度分析工具选型。
- **Frustrations:** 严格遵守开发者的指令范围，执行前确认指令边界。
- **Learning:** 提供完整的逻辑梳理，包括执行流程、数据变化和设计意图。
<!-- GSD:profile-end -->
