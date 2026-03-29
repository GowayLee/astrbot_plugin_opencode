# OVERVIEW

`core/` contains the runtime managers that `main.py` wires together for input processing, state tracking, execution, safety decisions, persistence, and output delivery.

This directory is intentionally split by operational concern. Extend the existing manager boundary before adding cross-cutting logic somewhere else.

# STRUCTURE

- `executor.py` - execution backends and transport contracts: local CLI runs, remote HTTP calls, health checks, session listing, shell execution.
- `session.py` - per-sender runtime state and continuity helpers; the source of truth for current workdir, environment, and OpenCode session ID.
- `security.py` - admin checks, destructive-operation detection, write-op confirmation triggers, and path-safety validation.
- `input.py` - inbound message normalization plus download of quoted/current media into `downloaded/`.
- `output.py` - output cleanup, ANSI handling, summary/TXT/long-image generation, and AstrBot send-plan construction.
- `storage.py` - persisted workdir history and background cleanup of temporary files.
- `utils.py` - sync file helpers meant to be called through thread offload, not a second runtime manager.

# COMPONENTS

- `executor.py`
  - Owns the local-vs-remote execution split.
  - New execution paths should fit this abstraction instead of adding side-channel subprocess or HTTP calls elsewhere.
- `session.py`
  - Owns per-sender in-memory state used across commands and background tool execution.
  - Treat it as the source of truth for continuity semantics.
- `security.py`
  - Centralizes admin gating and safety policy.
  - Reuse it instead of reimplementing checks inline in handlers.
- `input.py`
  - Prepares prompt context before execution code sees it.
  - Download behavior and `downloaded/` path semantics belong here.
- `output.py`
  - Central output router for formatting and delivery decisions.
  - Keep output flow funneled through `OutputProcessor.parse_output_plan`.
- `storage.py`
  - Owns retention and cleanup loops.
  - Background persistence belongs here, not in detached ad hoc tasks.

# WHERE TO LOOK

- Session/workdir bugs: `core/session.py`
- Local vs remote execution differences: `core/executor.py`
- Permission or path traversal concerns: `core/security.py`
- Media ingestion or downloaded-file handling: `core/input.py`
- Formatting, truncation, summary, exports, long-image rendering, merge-forward: `core/output.py`
- Workdir history or cleanup-loop behavior: `core/storage.py`

# CONVENTIONS

- Preserve manager separation. If a change spans input, execution, and output, update the boundary in each manager instead of collapsing logic into one file.
- Preserve async boundaries. Blocking filesystem helpers belong behind `asyncio.to_thread` or equivalent offload paths.
- Preserve shared-state semantics across normal commands, retries, and background tool execution.
- Route output decisions through `OutputProcessor.parse_output_plan` so formatting and delivery stay consistent.
- Prefer existing abstractions for safety, downloads, file access, and network calls before adding new side-effect paths.
- Keep local/remote behavior parity explicit in `executor.py`; if they diverge, the difference should be intentional and documented.

# ANTI-PATTERNS

- Do not stash ad hoc per-sender state in module globals or temporary caches outside `session.py`.
- Do not duplicate destructive-op checks, admin checks, or path validation outside `security.py`.
- Do not add output branches that bypass `OutputProcessor.parse_output_plan`, even for small formatting tweaks.
- Do not mix backend execution logic with input ingestion or rendering logic.
- Do not perform direct file, shell, or network side effects from arbitrary call sites when an existing manager already owns that responsibility.
- Do not turn `utils.py` into a miscellaneous fallback for runtime behavior.
