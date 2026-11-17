"""Consolidated pure-stdlib RSI ledger, loop state machine, crossover DAG, and explore args.

[Role]
Unifies `experiment_ledger`, `rsi_loop`, `rsi_crossover`, `rsi_explore`, and
`support` (`flagged`, `guard_regression`, `assess_stagnation`) inside `mindie_harness.rsi`
so `mindie-knowledge` remains 100% pure knowledge domain and all 7 host plugins
share one canonical RSI implementation without copy-paste drift.

[Invariants]
- 100% pure Python stdlib; zero imports of `mindie_knowledge`, `mindie_bench`, or `torch`.
- Preserves schemas `mindie-rsi-loop/2`, `mindie-experiment-ledger/1`, and
  `mindie-rsi-evaluation/1`, plus `python -m mindie_harness.rsi.rsi_loop` and
  `python -m mindie_harness.rsi.experiment_ledger` CLIs.

[Timeouts & Locks]
- Ledger and loop mutations serialize under `mindie_harness.locks.exclusive_lock` (`5.0s`).

[Side-Effect Policy]
- Pure imports on package load; disk writes happen only in `experiment_ledger` / `rsi_loop`.
"""
from __future__ import annotations

from .experiment_ledger import (
    EVALUATION_SCHEMA,
    SCHEMA_VERSION,
    append,
    check_trials,
    evaluate_rsi_axes,
    evaluate_rsi_candidate_gates,
    exclusive_lock,
    fingerprint,
    fold,
    gate,
    has_git_marker,
    iter_ledger,
    judge,
    read_ledger,
    render_progress,
    render_progress_file,
    resolve_git_worktree_info,
    validate,
)
from .rsi_crossover import (
    bind_fold_lineage,
    default_ablation_retained,
    derive_crossover_ablation_receipt,
    normalize_parent_exp_ids,
    resolve_kept_anchor,
    resolve_measure_ablation_receipt,
    snapshot_parent_source_digests,
    suggest_orthogonal_crossovers,
)
from .rsi_explore import MODES, OPTIONAL_KEYS, forwarded, parse_args, schema_properties
from .rsi_loop import SCHEMA as LOOP_SCHEMA, STEPS, complete, finish, init, next_step
from .support import assess_stagnation, flagged, guard_regression, walk

__all__ = [
    "EVALUATION_SCHEMA",
    "LOOP_SCHEMA",
    "MODES",
    "OPTIONAL_KEYS",
    "SCHEMA_VERSION",
    "STEPS",
    "append",
    "assess_stagnation",
    "bind_fold_lineage",
    "check_trials",
    "complete",
    "default_ablation_retained",
    "derive_crossover_ablation_receipt",
    "evaluate_rsi_axes",
    "evaluate_rsi_candidate_gates",
    "exclusive_lock",
    "fingerprint",
    "finish",
    "flagged",
    "fold",
    "forwarded",
    "gate",
    "guard_regression",
    "has_git_marker",
    "init",
    "iter_ledger",
    "judge",
    "next_step",
    "normalize_parent_exp_ids",
    "parse_args",
    "read_ledger",
    "render_progress",
    "render_progress_file",
    "resolve_git_worktree_info",
    "resolve_kept_anchor",
    "resolve_measure_ablation_receipt",
    "schema_properties",
    "snapshot_parent_source_digests",
    "suggest_orthogonal_crossovers",
    "validate",
    "walk",
]
