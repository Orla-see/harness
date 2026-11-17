"""Deterministic CPU-only release microbenchmarks for `mindie-harness`.

[Role]
Verifies functional correctness and measures per-operation latency (`us/op`) for
two core substrate hot paths required by `mindie-bench` (`mindie-release-suite/1`):
1. `seed-lock-verify`: streaming SHA-256 verification of `dist/mindie-harness-seed.pyz`
   against `dist/seed-lock.json` (`mindie-harness-seed/1`).
2. `mcp-router-dispatch`: `P2.7` zero-binding deterministic MCP `tools/call` routing
   (`mindie_status`) in an isolated temporary profile directory.

[Invariants]
- Business invariants are asserted before and after timing; invalid outcomes fail closed.

[Timeouts & Locks]
- Fixed bounded iterations (`200` ops); zero network calls or sleeps.

[Side-Effect Policy]
- Uses `tempfile.TemporaryDirectory` for profile isolation and writes only to
  `MINDIE_BENCH_RESULT_PATH`.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mindie_harness.bootstrap.seed_main import verify_seed_lock  # noqa: E402
from mindie_harness.mcp.router import MCPRouter  # noqa: E402
from mindie_harness.paths import ProfileRef  # noqa: E402

ITERATIONS = 200


def _measure(name: str, iterations: int, fn, verify) -> dict:
    verify(fn())
    started = time.perf_counter()
    res = None
    for _ in range(iterations):
        res = fn()
    elapsed = time.perf_counter() - started
    verify(res)
    us_per_op = elapsed * 1_000_000.0 / iterations
    assert math.isfinite(us_per_op) and us_per_op > 0.0
    return {
        "name": name,
        "unit": "us/op",
        "value": us_per_op,
        "iterations": iterations,
    }


def main(argv: list[str] | None = None) -> int:
    selected = list(sys.argv[1:] if argv is None else argv)
    pyz = REPO_ROOT / "dist" / "mindie-harness-seed.pyz"
    lock = REPO_ROOT / "dist" / "seed-lock.json"

    with tempfile.TemporaryDirectory(prefix="mindie-harness-bench-") as tmp:
        tmp_path = Path(tmp)
        profile = ProfileRef.resolve(
            "codex",
            plugin_root=tmp_path,
            config_path=tmp_path / "cfg" / "codex.json",
            data_dir=tmp_path / "data",
        )
        router = MCPRouter(profile, surface="tools")
        req = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "mindie_status", "arguments": {}}}

        workloads = {
            "seed-lock-verify": (
                "seed_lock_verify_latency",
                ITERATIONS,
                lambda: verify_seed_lock(pyz, lock),
                lambda doc: assert_true(doc.get("schema") == "mindie-harness-seed/1"),
            ),
            "mcp-router-dispatch": (
                "mcp_zero_binding_dispatch_latency",
                ITERATIONS,
                lambda: router.call_tool(req),
                lambda out: assert_true(isinstance(out, dict) and out.get("isError") is False),
            ),
        }
        chosen = selected or list(workloads)
        unknown = [k for k in chosen if k not in workloads]
        if unknown:
            raise SystemExit(f"Unknown benchmark case(s): {', '.join(unknown)}")

        metrics = [_measure(*workloads[k]) for k in chosen]
        dest = Path(os.environ["MINDIE_BENCH_RESULT_PATH"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps({"status": "pass", "metrics": metrics}) + "\n", encoding="utf-8", newline="\n")
    return 0


def assert_true(cond: bool) -> None:
    if not cond:
        raise AssertionError("Benchmark invariant assertion failed")


if __name__ == "__main__":
    raise SystemExit(main())
