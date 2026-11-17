"""Concurrent dual-framing stdio MCP server, `P2.7`/`P2.1` router, and honest receipts.

[Role]
Re-exports `RemoteReceipts`, `BindStore`, `apply_receipt_honesty`, `RequestContext`,
`MCPRouter`, `MCPStdioServer`, `read_mcp_message`, `write_mcp_message`, and `serve_stdio`.

[Invariants]
- Deterministic tools (`remote_*`, `coordinator`, `debugger`, `diagnostics`, `npu-top`,
  `profiler`, `sim`) require ZERO pre-call session binding (`P2.7`), while `knowledge_*`
  strictly requires an active manual `/mindie-agent` session lease (`P2.1`).
- Parallel read-only/status/cancel requests are NEVER blocked by in-flight foreground tools.

[Timeouts & Locks]
- Enforces `outer_timeout >= inner_budget + cleanup_grace` per tool surface.

[Side-Effect Policy]
- Pure imports on load; stdio/SQLite activity occurs only when a server/router runs.
"""
from __future__ import annotations

from .receipts import (
    RECEIPTS_SCHEMA_V1,
    RECEIPTS_SCHEMA_V2,
    BindStore,
    RemoteReceipts,
    apply_receipt_honesty,
    is_owner_alive,
    process_boot_signature,
)
from .router import (
    FORGED_IDENTITY_KEYS,
    MCPRouter,
    RequestContext,
    compute_tool_deadline,
    is_readonly_or_control_tool,
)
from .server import MCPStdioServer, read_mcp_message, serve_stdio, write_mcp_message

__all__ = [
    "FORGED_IDENTITY_KEYS",
    "RECEIPTS_SCHEMA_V1",
    "RECEIPTS_SCHEMA_V2",
    "BindStore",
    "MCPRouter",
    "MCPStdioServer",
    "RemoteReceipts",
    "RequestContext",
    "apply_receipt_honesty",
    "compute_tool_deadline",
    "is_owner_alive",
    "is_readonly_or_control_tool",
    "process_boot_signature",
    "read_mcp_message",
    "serve_stdio",
    "write_mcp_message",
]
