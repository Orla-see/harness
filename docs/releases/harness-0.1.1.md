# mindie-harness 0.1.1：MCP 组件工具截止时间透传与 600s 内层上限

[English](harness-0.1.1.en.md)

`mindie-harness v0.1.1` 正式发布，作为 MindIE Agent 全系 7 个原生宿主插件（`codex`、`cc`、`kimi`、`dsh`、`agy`、`wb`、`oc`）共用纯标准库底座（`mindie_harness`）的补丁版本，聚焦 MCP 确定性组件工具的长耗时调用边界：

- **组件工具 `timeout_ms` 端到端透传（`mindie_harness.mcp.router.compute_tool_deadline`）**：`coordinator`、`debugger`、`profiler`、`sim`、`npu-top`、`diagnostics` 等确定性组件工具现在会读取调用方 `timeout_ms`，将内层预算从固定 `120s` 提升至最高 `600s`（10 分钟）；内层超过 `120s` 时清理宽限由 `10s` 提升至 `60s`，外层截止时间相应为最高 `660s`，避免长时间 Profiling / Sim 采集被过早终止。
- **确定性回退与单向扩权**：缺省、非数值、布尔、非有限或非正的 `timeout_ms` 一律回退至历史 `120s + 10s = 130s`；路由层显式 `timeout` 只能延长、不能缩短外层截止时间，保持既有调用方语义不变。
- **Tier-0 回归覆盖**：新增覆盖 `120s` / `300s` / `600s` / `900s` 调用、非法输入回退、显式超时扩权与 `600s` 内层硬上限的确定性单元测试，确保截止时间算术与 `Deadline` 清理宽限契约不回退。
- **版本与冷启动 Seed 同步**：`pyproject.toml`、包元数据、双语文档与 `dist/mindie-harness-seed.pyz` / `dist/seed-lock.json`（`mindie-harness-seed/1`）统一升至 `0.1.1`；`API_VERSION` 保持 `1`，公共 ABI 完全向后兼容。
