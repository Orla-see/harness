#!/usr/bin/env python3
"""Focused `< 150`-line stdlib PR checklist validator (`--profile harness`).

[Role]
Validates Pull Request descriptions against `.github/pull_request_template.md`
machine-stable checklist IDs (`HAR-ABI`, `HAR-UPGRADE`, `HAR-PROC`, `HAR-STATE`
for `--profile harness`), supporting `not-applicable: docs-only` on docs-only PRs.

[Invariants]
- Pure Python stdlib; zero external dependencies or network calls.
- Rejects unchecked `- [ ]` items, missing profile IDs, or placeholder sections.

[Timeouts & Locks]
- Pure in-memory regex parsing (`< 20ms`); no locks.

[Side-Effect Policy]
- Read-only inspection of `--body-file`, `PR_BODY`, or `GITHUB_EVENT_PATH`.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys

PROFILE_IDS: dict[str, tuple[str, ...]] = {
    "harness": ("HAR-ABI", "HAR-UPGRADE", "HAR-PROC", "HAR-STATE"),
    "hub": ("HUB-ROUTE", "HUB-DOC", "HUB-RELEASE", "HUB-GATE"),
    "host-plugin": ("HOST-NATIVE", "HOST-WIRE", "HOST-ADMISSION", "HOST-UPGRADE"),
    "control-plane": ("CTRL-LEASE-OR-AUTH", "CTRL-HANDLE", "CTRL-STREAM-IO", "CTRL-RECEIPT"),
    "state-service": ("SVC-CONSENT", "SVC-STATE-COMPAT", "SVC-LIFETIME", "SVC-EXPORT"),
    "device-tool": ("DEV-ZERO-CTX", "DEV-READONLY-PATH", "DEV-TOPOLOGY", "DEV-BOUNDED-MEM"),
    "bench": ("BENCH-ORACLE", "BENCH-VERDICT", "BENCH-PROVENANCE", "BENCH-ISOLATION"),
    "corpus": ("CORPUS-SCHEMA", "CORPUS-EVIDENCE", "CORPUS-REDACT", "CORPUS-REVISION"),
}
PLACEHOLDERS = frozenset({"todo", "tbd", "n/a", "na", "none", "null", "-", "无", "略", "待补充"})
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
HEADING_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
UNCHECKED_RE = re.compile(r"^\s*-\s*\[\s\]\s+(.+)$", re.MULTILINE)
CHECKED_ID_RE = re.compile(r"^\s*-\s*\[[xX]\]\s+\*\*([A-Z]+-[A-Z-]+)", re.MULTILINE)
EVIDENCE_RE = re.compile(r"^\s*-\s*\*\*(?:自查结论与证据|Review Evidence)\*\*\s*[：:]\s*(.*)$", re.MULTILINE)


def _sections(body: str) -> dict[str, str]:
    matches = list(HEADING_RE.finditer(body))
    return {
        m.group(1).strip(): body[m.end() : (matches[i + 1].start() if i + 1 < len(matches) else len(body))].strip()
        for i, m in enumerate(matches)
    }


def _find_sec(secs: dict[str, str], *keys: str) -> str | None:
    for title, text in secs.items():
        if any(k in title for k in keys):
            return text
    return None


def _clean_lines(text: str) -> list[str]:
    out = []
    for raw in text.splitlines():
        line = re.sub(r"^[-*+]\s+", "", raw.strip()).strip()
        if line and not line.startswith(">") and line.lower() not in PLACEHOLDERS:
            out.append(line)
    return out


def validate_pr_body(raw_body: str, *, profile: str = "harness") -> list[str]:
    required_ids = PROFILE_IDS.get(profile)
    if required_ids is None:
        return [f"Unknown checklist profile: {profile!r}"]
    body = COMMENT_RE.sub("", raw_body or "")
    if not body.strip():
        return ["PR description is empty; fill out .github/pull_request_template.md."]

    errors: list[str] = []
    secs = _sections(body)
    summary = _find_sec(secs, "变更摘要", "Summary")
    if summary is None or sum(len(x) for x in _clean_lines(summary)) < 10:
        errors.append("Section '## 变更摘要 (Summary)' must contain >= 10 substantive chars.")

    review = _find_sec(secs, "Pre-PR Checklist", "核查清单", "设计原则 Review")
    if review is None:
        errors.append("Missing '## ... (Pre-PR Checklist)' section.")
    else:
        docs_only = "not-applicable: docs-only" in review.lower()
        if UNCHECKED_RE.findall(review) and not docs_only:
            errors.append("All Pre-PR Checklist items must be checked ('- [x]') or marked 'not-applicable: docs-only'.")
        checked = set(CHECKED_ID_RE.findall(review))
        if not docs_only:
            for item_id in required_ids:
                if item_id not in checked:
                    errors.append(f"Missing checked item '- [x] **{item_id}...' for profile '{profile}'.")
        ev = EVIDENCE_RE.search(review)
        if ev is None:
            errors.append("Missing '- **自查结论与证据**：<concrete evidence>' line.")
        else:
            ev_text = (ev.group(1).strip() + " " + " ".join(_clean_lines(review[ev.end() :]))).strip()
            if not docs_only and (ev_text.lower() in PLACEHOLDERS or len(ev_text) < 12):
                errors.append("Review evidence must be concrete (>= 12 chars) or 'not-applicable: docs-only'.")

    verif = _find_sec(secs, "验证结果", "Verification")
    if verif is None or sum(len(x) for x in _clean_lines(verif)) < 10:
        errors.append("Section '## 验证结果 (Verification)' must record actual commands/results (>= 10 chars).")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", default="harness", choices=sorted(PROFILE_IDS))
    parser.add_argument("--body-file", type=Path)
    args = parser.parse_args(argv)
    if args.body_file:
        body = args.body_file.read_text(encoding="utf-8-sig")
    elif "PR_BODY" in os.environ:
        body = os.environ["PR_BODY"]
    elif (ep := os.environ.get("GITHUB_EVENT_PATH")) and Path(ep).is_file():
        body = ((json.loads(Path(ep).read_text(encoding="utf-8")).get("pull_request") or {}).get("body")) or ""
    else:
        raise SystemExit("Provide --body-file, PR_BODY, or GITHUB_EVENT_PATH.")
    errs = validate_pr_body(body, profile=args.profile)
    if errs:
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print(f"Pre-PR Checklist passed (profile={args.profile}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
