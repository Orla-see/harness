"""Pure-stdlib recursive gate evidence helpers and model-free RSI stagnation detector.

[Role]
Provides `walk`, `flagged`, `guard_regression`, and `assess_stagnation` so
`experiment_ledger` and `rsi_loop` execute with zero `mindie_knowledge` dependency.

[Invariants]
- Gate evidence is inspected recursively; only explicit regression signals fail,
  and missing optional keys never fabricate a regression.
- Information stagnation is distinct from execution failure: infrastructure or
  measurement faults (`infra_failed`, `measurement_invalid`, non-noise `inconclusive`)
  request repair and never increment stalled-attempt counts.
- `promotion_ready` becomes `True` only after `max(limit, 3)` consecutive refuted
  attempts with `>= 3` distinct candidate source hashes since last progress.

[Timeouts & Locks]
- Pure in-memory validation and arithmetic; zero subprocesses, network calls, or locks.

[Side-Effect Policy]
- Pure functions returning derived dictionaries/booleans; mutates nothing.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from typing import Any

REPAIR_OUTCOMES: frozenset[str] = frozenset({"infra_failed", "measurement_invalid"})
PROGRESS_VERDICTS: frozenset[str] = frozenset(
    {
        "supported",
        "attained",
        "subtarget_valid",
        "improved",
        "qualified_improvement",
        "distill_candidate",
    }
)
NEGATIVE_VERDICTS: frozenset[str] = frozenset(
    {
        "refuted",
        "failed",
        "negative",
        "rejected",
        "unsupported",
        "record_conditional_finding",
    }
)
NEGATIVE_OUTCOMES: frozenset[str] = frozenset(
    {
        "no_improvement",
        "regression",
        "failed",
        "refuted",
        "speedup_within_noise",
    }
)


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object")
    return dict(value)


def walk(value: Any, key: str) -> Iterator[Any]:
    """Recursively yield values bound to `key` across nested mappings and sequences."""
    if isinstance(value, Mapping):
        if key in value:
            yield value[key]
        for child in value.values():
            yield from walk(child, key)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for child in value:
            yield from walk(child, key)


def flagged(value: Any, key: str) -> bool:
    """Return True if any nested occurrence of `key` carries a truthy signal."""
    return any(found not in (None, False, 0, "0", "", [], {}) for found in walk(value, key))


def guard_regression(value: Any) -> bool:
    """Return True when any guard workload row reports a performance or pass regression."""
    rows = value.values() if isinstance(value, Mapping) else value or ()
    for row in rows:
        if not isinstance(row, Mapping):
            if row is True:
                return True
            continue
        if (
            row.get("regression") is True
            or row.get("regressed") is True
            or row.get("guard_ok") is False
        ):
            return True
        reg_val, margin = row.get("regression"), row.get("noise_margin", 0.01)
        if (
            isinstance(reg_val, (int, float))
            and not isinstance(reg_val, bool)
            and isinstance(margin, (int, float))
            and not isinstance(margin, bool)
            and reg_val > margin
        ):
            return True
        if row.get("baseline_pass") is True and row.get("candidate_pass") is False:
            return True
        baseline, candidate, margin = (
            row.get("baseline_ms"),
            row.get("candidate_ms"),
            row.get("noise_margin", 0.01),
        )
        if (
            all(
                isinstance(item, (int, float)) and not isinstance(item, bool)
                for item in (baseline, candidate, margin)
            )
            and candidate > baseline * (1 + margin)
        ):
            return True
    return False


def assess_stagnation(
    ledger_entries: Sequence[Mapping[str, Any]],
    *,
    consecutive_limit: int = 3,
    max_stalled_attempts: int | None = None,
) -> dict[str, Any]:
    """Deduplicate ledger attempts by candidate hash / `run_id` and evaluate stagnation."""
    limit = consecutive_limit if max_stalled_attempts is None else max_stalled_attempts
    if type(limit) is not int or limit < 1:
        raise ValueError("consecutive_limit must be a positive integer")

    unique_map: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(ledger_entries or ()):
        entry = _mapping(raw, f"ledger_entries[{index}]")
        if entry.get("is_baseline") is True:
            continue
        cand_sha = (
            entry.get("candidate_sha256")
            or entry.get("candidate_hash")
            or entry.get("source_digest")
        )
        run_id = entry.get("run_id")
        if isinstance(cand_sha, str) and cand_sha.strip():
            norm_sha = cand_sha.strip()
            entry = {**entry, "_candidate_hash": norm_sha}
            key = f"sha256:{norm_sha}"
        elif isinstance(run_id, str) and run_id.strip():
            key = run_id.strip()
        else:
            key = f"attempt:{index}"
        unique_map.pop(key, None)
        unique_map[key] = entry

    unique = list(unique_map.values())
    stalled_count = 0
    repair = False
    progressed = False
    budget_exhausted = False
    unverified = 0
    refuted_hashes_since_progress: list[str] = []

    for attempt in unique:
        verdict = attempt.get("verdict")
        outcome = attempt.get("outcome")
        axes = attempt.get("axes")
        attainment = (
            axes.get("goal_attainment") if isinstance(axes, Mapping) else None
        ) or attempt.get("goal_attainment")
        if attempt.get("budget_exhausted") is True:
            budget_exhausted = True
        if attempt.get("hypothesis") and not (
            attempt.get("hypothesis_verified") is True or verdict in PROGRESS_VERDICTS
        ):
            unverified += 1
        if outcome in REPAIR_OUTCOMES or (
            verdict == "inconclusive" and outcome != "speedup_within_noise"
        ):
            repair = True
        elif (
            verdict in PROGRESS_VERDICTS
            or attainment == "attained"
            or attempt.get("new_observation") is True
            or attempt.get("divergent_layer_identified") is True
            or attempt.get("improvement") is True
            or (isinstance(axes, Mapping) and axes.get("goal_achieved") is True)
        ):
            stalled_count, progressed = 0, True
            refuted_hashes_since_progress = []
        elif (
            verdict in NEGATIVE_VERDICTS
            or outcome in NEGATIVE_OUTCOMES
            or attainment in {"not_attained", "regressed", "failed"}
        ):
            stalled_count += 1
            chash = attempt.get("_candidate_hash")
            if isinstance(chash, str) and chash and chash not in refuted_hashes_since_progress:
                refuted_hashes_since_progress.append(chash)

    legacy = bool(unique) and all(
        "verdict" in entry
        and "outcome" not in entry
        and "budget_exhausted" not in entry
        and "hypothesis" not in entry
        for entry in unique
    )
    threshold = min(limit, 2) if legacy and max_stalled_attempts is None else limit
    if stalled_count >= threshold:
        status, stalled = "stalled", True
        reason = "consecutive_unimproved_limit_reached"
    elif repair and not stalled_count:
        status, stalled = "repair_execution_conditions", False
        reason = "execution conditions are invalid; repair them before judging information stagnation"
    elif not unique:
        status, stalled = "no_attempts", False
        reason = "no attempts were supplied"
    elif stalled_count:
        status, stalled = "monitoring", False
        reason = f"{stalled_count} unproductive attempt(s); below the {threshold} reminder threshold"
    elif progressed:
        status, stalled = "progressing", False
        reason = "a new observation, supported verdict, or identified divergent layer is progress"
    else:
        status, stalled = "monitoring", False
        reason = "no decisive information yet"
    if repair and status in {"progressing", "monitoring"}:
        reason += "; some attempts require repaired execution conditions"

    distinct_hashes = [
        entry["_candidate_hash"]
        for entry in unique
        if isinstance(entry.get("_candidate_hash"), str) and entry["_candidate_hash"]
    ]
    promotion_threshold = max(limit, 3)
    promotion_ready = bool(
        stalled_count >= promotion_threshold
        and len(refuted_hashes_since_progress) >= promotion_threshold
    )
    return {
        "stalled": stalled,
        "stalled_count": stalled_count,
        "consecutive_limit": limit,
        "status": status,
        "reason": reason,
        "tail_run_ids": [
            entry["run_id"]
            for entry in unique[-limit:]
            if isinstance(entry.get("run_id"), str)
        ],
        "distinct_candidate_hashes": distinct_hashes,
        "distinct_refuted_candidate_hashes": refuted_hashes_since_progress,
        "promotion_ready": promotion_ready,
        "unverified_hypotheses_remaining": unverified,
        "budget_exhausted": budget_exhausted,
        "should_escalate": bool(stalled),
        "escalation_reason": reason,
    }


PROGRESS_MARKER_START = "<!-- mindie-rsi-progress:start -->"
PROGRESS_MARKER_END = "<!-- mindie-rsi-progress:end -->"
MANAGED_PROGRESS_HEADINGS = frozenset(
    {"Goal", "Best Supported Candidate", "Active Hypotheses", "Refuted Directions", "Experiments To Complete"}
)
import json  # noqa: E402
import math as _math  # noqa: E402
import re as _re  # noqa: E402

RECOVERY_TOKEN_RE = _re.compile(
    r"(?i)(?:\b(?:in_flight_runs|slot_id|job_id|run_id|host_endpoint|manifest_path)\b|\b(?:endpoint|manifest)\b[`'\"]?\s*[:=])"
)


def rank_supported_candidates(live: list[dict[str, Any]]) -> list[tuple[dict[str, Any], float, float]]:
    """Compute cumulative speedup over explicit baseline/source lineage and rank kept candidates."""
    kept = [rec for rec in live if rec.get("verdict") in ("supported", "subtarget_valid")]
    by_exp: dict[tuple[str, str], list[dict[str, Any]]] = {}
    by_digest: dict[tuple[str, str], list[dict[str, Any]]] = {}
    non_kept_exps: set[tuple[str, str]] = set()
    non_kept_digests: set[tuple[str, str]] = set()
    primary_ids = {
        (json.dumps(r.get("conditions") or {}, sort_keys=True), str(r.get("exp_id") or r.get("candidate_id") or "").strip())
        for r in live
    }
    for rec in live:
        cond_key = json.dumps(rec.get("conditions") or {}, sort_keys=True)
        cid = str(rec.get("exp_id") or rec.get("candidate_id") or "").strip()
        src = str(rec.get("source_digest") or "").strip()
        alias_ids = ([cid] if cid else []) + [
            old.strip()
            for old in (rec.get("_superseded_ids") or ())
            if isinstance(old, str) and old.strip() and (cond_key, old.strip()) not in primary_ids
        ]
        if rec.get("verdict") in ("supported", "subtarget_valid"):
            if src:
                by_digest.setdefault((cond_key, src), []).append(rec)
            for eid in alias_ids:
                by_exp.setdefault((cond_key, eid), []).append(rec)
        else:
            if src:
                non_kept_digests.add((cond_key, src))
            non_kept_exps.update((cond_key, eid) for eid in alias_ids)

    def step_of(rec: dict[str, Any]) -> float:
        raw = rec.get("speedup_ratio")
        return float(raw) if (not isinstance(raw, bool) and isinstance(raw, (int, float)) and _math.isfinite(raw) and raw > 0) else 0.0

    def resolve_parent(rec: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
        cond_key = json.dumps(rec.get("conditions") or {}, sort_keys=True)
        cid = str(rec.get("exp_id") or rec.get("candidate_id") or "").strip()
        own_ids = {cid, *(str(a).strip() for a in (rec.get("_superseded_ids") or ()))}
        cand_src = str(rec.get("source_digest") or "").strip()
        b_exp = rec.get("baseline_exp_id").strip() if isinstance(rec.get("baseline_exp_id"), str) else ""
        b_src = rec.get("baseline_source_digest").strip() if isinstance(rec.get("baseline_source_digest"), str) else ""
        if (b_exp and b_exp in own_ids) or (b_src and b_src == cand_src):
            return "invalid", None
        if b_exp:
            if (cond_key, b_exp) in non_kept_exps:
                return "invalid", None
            matches = [m for m in by_exp.get((cond_key, b_exp), []) if m is not rec]
            if len(matches) > 1:
                return "invalid", None
            if len(matches) == 1:
                p_src = str(matches[0].get("source_digest") or "").strip()
                return ("invalid", None) if (b_src and p_src and p_src != b_src) else ("ok", matches[0])
            return ("invalid", None) if (b_src and (by_digest.get((cond_key, b_src)) or (cond_key, b_src) in non_kept_digests)) else ("root", None)
        if b_src:
            matches = [m for m in by_digest.get((cond_key, b_src), []) if m is not rec]
            return ("invalid", None) if len(matches) > 1 else ("ok", matches[0]) if len(matches) == 1 else (("invalid", None) if (cond_key, b_src) in non_kept_digests else ("root", None))
        return "root", None

    def cumulative_of(rec: dict[str, Any]) -> float:
        seen_ids: set[int] = set()
        curr: dict[str, Any] | None = rec
        total = 1.0
        while curr is not None:
            rid, step = id(curr), step_of(curr)
            if step <= 0 or rid in seen_ids:
                return 0.0
            seen_ids.add(rid)
            total *= step
            kind, curr = resolve_parent(curr)
            if kind in ("invalid", "root"):
                return 0.0 if kind == "invalid" else total
        return total

    ranked = [(rec, step_of(rec), cum, str(rec.get("candidate_id") or rec.get("exp_id") or "")) for rec in kept if (cum := cumulative_of(rec)) > 0]
    ranked.sort(key=lambda item: (-round(item[2], 9), 0 if item[0].get("verdict") == "supported" else 1, -round(item[1], 9), item[3]))
    return [(rec, step, cum) for rec, step, cum, _ in ranked]


def extract_embedded_recovery_paragraphs(section_body: str) -> list[str]:
    """Preserve `in_flight_runs` / endpoint recovery blocks embedded inside `PROGRESS.md`."""
    text = section_body.strip()
    if not text or not RECOVERY_TOKEN_RE.search(text):
        return []
    lines, segments, idx = text.splitlines(), [], 0
    while idx < len(lines):
        line, stripped = lines[idx], lines[idx].strip()
        if not stripped:
            idx += 1
        elif stripped.startswith("```"):
            buf, idx = [line], idx + 1
            while idx < len(lines) and (not buf[-1].strip().startswith("```") or len(buf) == 1):
                buf.append(lines[idx])
                idx += 1
                if buf[-1].strip().startswith("```"):
                    break
            segments.append(("\n".join(buf).strip(), True))
        elif stripped.startswith(("{", "[")):
            buf, depth, idx = [line], line.count("{") + line.count("[") - line.count("}") - line.count("]"), idx + 1
            while idx < len(lines) and depth > 0:
                buf.append(lines[idx])
                depth += lines[idx].count("{") + lines[idx].count("[") - lines[idx].count("}") - lines[idx].count("]")
                idx += 1
            segments.append(("\n".join(buf).strip(), True))
        elif _re.match(r"(?i)^in_flight_runs\b", stripped):
            buf, idx = [line], idx + 1
            while idx < len(lines) and lines[idx].strip() and not lines[idx].strip().startswith("```"):
                buf.append(lines[idx])
                idx += 1
            segments.append(("\n".join(buf).strip(), True))
        elif RECOVERY_TOKEN_RE.search(line):
            base_indent, buf, idx = len(line) - len(line.lstrip(" \t")), [line], idx + 1
            while idx < len(lines) and lines[idx].strip() and not lines[idx].strip().startswith(("```", "{", "[")) and (len(lines[idx]) - len(lines[idx].lstrip(" \t"))) > base_indent:
                buf.append(lines[idx])
                idx += 1
            segments.append(("\n".join(buf).strip(), True))
        else:
            segments.append((stripped, False))
            idx += 1
    rescued, s_idx = [], 0
    while s_idx < len(segments):
        seg_text, _ = segments[s_idx]
        if (seg_text.startswith("#") or seg_text.endswith(":")) and s_idx + 1 < len(segments) and (RECOVERY_TOKEN_RE.search(seg_text) or RECOVERY_TOKEN_RE.search(segments[s_idx + 1][0])):
            next_text, next_atomic = segments[s_idx + 1]
            rescued.append(f"{seg_text}{chr(10) if next_atomic and next_text.startswith(('```', '{', '[', '-')) else chr(10) * 2}{next_text}")
            s_idx += 2
        else:
            if RECOVERY_TOKEN_RE.search(seg_text):
                rescued.append(seg_text)
            s_idx += 1
    return [r for r in rescued if r]


def render_managed_progress_body(live: list[dict[str, Any]], *, campaign_id: str, goal: str = "") -> str:
    """Render the managed RSI progress sections from folded `live` records."""
    ranked_kept = rank_supported_candidates(live)
    refuted = [e for e in live if e.get("verdict") == "refuted"]
    inconclusive = [e for e in live if e.get("verdict") == "inconclusive"]
    lines = [PROGRESS_MARKER_START, "## Goal", "", goal or f"Optimize `{campaign_id}` under verified measurement and ablation gates.", "", "## Best Supported Candidate", ""]
    if ranked_kept:
        best, step_ratio, cum_ratio = ranked_kept[0]
        cid, cum_note = best.get("candidate_id") or best.get("exp_id"), (f", cumulative `{cum_ratio:.4f}x`" if abs(cum_ratio - step_ratio) > 1e-6 else "")
        lines.append(f"- candidate: `{cid}` (`{best.get('verdict')}`, `{step_ratio:.4f}x`{cum_note}) — {best.get('mutation_summary', '')}")
    else:
        lines.append("- None yet.")
    lines.extend(["", "## Active Hypotheses", ""])
    lines.extend(
        [f"- `{item.get('candidate_id') or item.get('exp_id')}` ({item.get('verdict')}): {item.get('mutation_summary', '')} (`{s:.4f}x`{f', cumulative `{c:.4f}x`' if abs(c - s) > 1e-6 else ''})" for item, s, c in ranked_kept[:3]]
        or ["- Establish first verified candidate passing Gates 1-3."]
    )
    lines.extend(["", "## Refuted Directions", ""])
    refuted_lines = []
    for item in refuted[-10:]:
        avoids = item.get("conditional_avoid") or (
            [{"candidate_id": item.get("candidate_id") or item.get("exp_id"), "run_id": item.get("run_id"), "conditions": item.get("conditions") or {}, "reason": item.get("failure_reason") or item.get("outcome") or "refuted"}]
            if item.get("conditions")
            else []
        )
        for avoid in avoids:
            target_id = avoid.get("candidate_id") or item.get("candidate_id") or item.get("exp_id") or avoid.get("what_to_avoid")
            run_ref = avoid.get("run_id") or item.get("run_id") or "unknown"
            reason = avoid.get("reason") or item.get("failure_reason") or item.get("outcome") or "refuted"
            refuted_lines.append(f"- avoid {target_id} when {json.dumps(avoid.get('conditions', {}), sort_keys=True, ensure_ascii=False)}: {reason} (run `{run_ref}`)")
    lines.extend(refuted_lines or ["- None recorded."])
    lines.extend(["", "## Experiments To Complete", ""])
    lines.extend([f"- `{item.get('candidate_id') or item.get('exp_id')}`: outcome=`{item.get('outcome')}` ({item.get('failure_reason') or 're-verify measurement/ablation'})" for item in inconclusive[-5:]] or ["- None pending."])
    lines.append(PROGRESS_MARKER_END)
    return "\n".join(lines)


def merge_progress_markdown(existing_text: str | None, managed_body: str, *, campaign_id: str) -> str:
    """Merge managed RSI progress sections with user/recovery sections in `PROGRESS.md`."""
    title = f"# RSI Progress: {campaign_id}"
    if not existing_text or not existing_text.strip():
        return f"{title}\n\n{managed_body}\n"
    cleaned = "\n".join(line for line in existing_text.splitlines() if line.strip() not in (PROGRESS_MARKER_START, PROGRESS_MARKER_END)) + "\n"
    matches = list(_re.finditer(r"(?m)^## +([^\n]+)\n", cleaned))
    preamble_lines = [ln for ln in (cleaned[: matches[0].start()] if matches else cleaned).splitlines() if not ln.strip().startswith("# RSI Progress:")]
    preamble_blocks = [b.strip() for b in _re.split(r"\n\s*\n", "\n".join(preamble_lines).strip()) if b.strip()]
    preserved_sections = []
    for idx, match in enumerate(matches):
        heading, sec_end = match.group(1).strip(), matches[idx + 1].start() if idx + 1 < len(matches) else len(cleaned)
        if heading not in MANAGED_PROGRESS_HEADINGS:
            preserved_sections.append(cleaned[match.start() : sec_end].strip())
        else:
            preamble_blocks.extend(r for r in extract_embedded_recovery_paragraphs(cleaned[match.end() : sec_end]) if r not in preamble_blocks)
    return "\n\n".join([title] + preamble_blocks + preserved_sections + [managed_body]) + "\n"
