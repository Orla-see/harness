# mindie-harness 0.1.1: MCP Component-Tool Deadline Propagation with a 600s Inner Ceiling

[中文](harness-0.1.1.md)

`mindie-harness v0.1.1` is a patch release of the zero-heavy-dependency, pure-Python-stdlib shared substrate (`mindie_harness`) powering all 7 MindIE Agent native host plugins (`codex`, `cc`, `kimi`, `dsh`, `agy`, `wb`, `oc`), focused on the long-running boundary of deterministic MCP component tools:

- **End-to-End `timeout_ms` Propagation for Component Tools (`mindie_harness.mcp.router.compute_tool_deadline`)**: Deterministic component tools (`coordinator`, `debugger`, `profiler`, `sim`, `npu-top`, `diagnostics`) now read the caller's `timeout_ms` and raise the inner budget from a fixed `120s` up to `600s` (10 minutes). Once the inner budget exceeds `120s`, the cleanup grace increases from `10s` to `60s`, yielding an outer deadline of up to `660s` so long Profiling / Sim captures are no longer terminated prematurely.
- **Deterministic Fallback and Extend-Only Semantics**: Missing, non-numeric, boolean, non-finite, or non-positive `timeout_ms` values fall back to the historical `120s + 10s = 130s`; an explicit router-level `timeout` may only extend, never shrink, the outer deadline, preserving existing caller semantics.
- **Tier-0 Regression Coverage**: Adds deterministic unit tests for `120s` / `300s` / `600s` / `900s` callers, invalid-input fallback, explicit-timeout extension, and the `600s` inner hard cap, locking the deadline arithmetic and `Deadline` cleanup-grace contract.
- **Synchronized Version and Cold-Bootstrap Seed**: `pyproject.toml`, package metadata, bilingual docs, and `dist/mindie-harness-seed.pyz` / `dist/seed-lock.json` (`mindie-harness-seed/1`) are all bumped to `0.1.1`; `API_VERSION` remains `1`, keeping the public ABI fully backward compatible.
