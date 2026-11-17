"""Deterministic pure-stdlib cold-bootstrap seed (`mindie-harness-seed.pyz`) and lock verifier.

[Role]
Re-exports `SEED_LOCK_SCHEMA`, `verify_seed_lock`, `render_plugin_bootstrap_template`,
and `main` from `seed_main`.

[Invariants]
- 100% pure Python stdlib; reproducible zipapp `< 60 KB`; `< 115`-line plugin launcher template.

[Timeouts & Locks]
- Cold provisioning serializes under a per-host prepare lock (`240s` `uv` timeout).

[Side-Effect Policy]
- Pure imports on load.
"""
from __future__ import annotations

from .seed_main import (
    SEED_LOCK_SCHEMA,
    compute_seed_lock,
    main,
    render_plugin_bootstrap_template,
    verify_seed_lock,
)

__all__ = [
    "SEED_LOCK_SCHEMA",
    "compute_seed_lock",
    "main",
    "render_plugin_bootstrap_template",
    "verify_seed_lock",
]
