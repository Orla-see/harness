#!/usr/bin/env python3
"""Deterministic builder for `dist/mindie-harness-seed.pyz` and `dist/seed-lock.json`.

[Role]
Packages `mindie_harness/bootstrap/seed_main.py` into a reproducible `< 60 KB`
stdlib zipapp (`dist/mindie-harness-seed.pyz`) with fixed ZIP timestamps and
permissions, writes `dist/seed-lock.json` (`mindie-harness-seed/1`), and verifies
reproducibility + `< 115`-line template invariants.

[Invariants]
- Fixed `ZipInfo.date_time = (2026, 1, 1, 0, 0, 0)` and `external_attr = 0o644 << 16`
  ensure two builds on any OS produce byte-for-byte identical SHA-256 digests.
- Enforces `size_bytes < 60 * 1024` (`60 KB` ceiling) and `< 115` lines on all 7
  rendered host bootstrap templates.

[Timeouts & Locks]
- Pure local file compression and SHA-256 verification (`< 100ms`); no locks.

[Side-Effect Policy]
- Writes `dist/mindie-harness-seed.pyz` and `dist/seed-lock.json` (unless `--check` is set).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from mindie_harness.atomic import atomic_write_bytes, atomic_write_json  # noqa: E402
from mindie_harness.bootstrap.seed_main import (  # noqa: E402
    SEED_VERSION,
    compute_seed_lock,
    render_plugin_bootstrap_template,
    verify_seed_lock,
)
from mindie_harness.paths import HOSTS  # noqa: E402

MAX_SEED_BYTES = 60 * 1024
SHEBANG = b"#!/usr/bin/env python3\n"
FIXED_ZIP_DATE = (2026, 1, 1, 0, 0, 0)


def build_seed_bytes(source_path: Path | None = None) -> bytes:
    """Build deterministic zipapp bytes from `seed_main.py` in memory."""
    src = source_path or (REPO_ROOT / "mindie_harness" / "bootstrap" / "seed_main.py")
    code_bytes = src.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        info = zipfile.ZipInfo(filename="__main__.py", date_time=FIXED_ZIP_DATE)
        info.compress_type = zipfile.ZIP_DEFLATED
        info.create_system = 3  # Unix
        info.external_attr = (0o100644 & 0xFFFF) << 16
        zf.writestr(info, code_bytes)

    payload = SHEBANG + buf.getvalue()
    if len(payload) >= MAX_SEED_BYTES:
        raise ValueError(f"Seed zipapp size ({len(payload)}B) exceeds 60 KiB ceiling ({MAX_SEED_BYTES}B)")
    return payload


def verify_all_templates() -> None:
    for host in HOSTS:
        rendered = render_plugin_bootstrap_template(host)
        line_count = len(rendered.splitlines())
        if line_count >= 115:
            raise ValueError(f"Bootstrap template for {host} is {line_count} lines (must be < 115)")
        compile(rendered, f"<bootstrap-{host}>", "exec")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=REPO_ROOT / "dist")
    parser.add_argument("--emit-template", choices=HOSTS, help="Print rendered <115L plugin launcher to stdout.")
    parser.add_argument("--check", action="store_true", help="Verify existing dist/ artifacts match reproducible build.")
    args = parser.parse_args(argv)

    if args.emit_template:
        sys.stdout.write(render_plugin_bootstrap_template(args.emit_template))
        return 0

    verify_all_templates()
    first = build_seed_bytes()
    second = build_seed_bytes()
    if first != second:
        raise RuntimeError("Non-deterministic zipapp output detected across consecutive builds")

    sha = hashlib.sha256(first).hexdigest()
    out_dir = args.out_dir.resolve()
    pyz_path = out_dir / "mindie-harness-seed.pyz"
    lock_path = out_dir / "seed-lock.json"

    if args.check:
        verified = verify_seed_lock(pyz_path, lock_path)
        if verified["sha256"] != sha or verified["size_bytes"] != len(first):
            raise SystemExit(
                f"Stale dist/mindie-harness-seed.pyz: expected sha256={sha} ({len(first)}B), "
                f"found {verified['sha256']} ({verified['size_bytes']}B)"
            )
        print(json.dumps({"status": "verified", **verified}, sort_keys=True))
        return 0

    atomic_write_bytes(pyz_path, first, mode=0o755)
    lock_doc = compute_seed_lock(pyz_path, version=SEED_VERSION)
    atomic_write_json(lock_path, lock_doc, mode=0o644)
    verify_seed_lock(pyz_path, lock_path)
    print(json.dumps({"status": "built", "pyz": str(pyz_path), "lock": str(lock_path), **lock_doc}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
