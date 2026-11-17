"""Shared component registry, compatibility interval evaluator, and ABI selector.

[Role]
Defines the authoritative v2 `SHARED_COMPONENTS` catalog (9 shared runtime components
including `mindie-harness`), `RuntimeSelection`, version/interval compatibility
matching (optional `packaging` with deterministic pure-stdlib fallback), Python ABI
selection, and platform-isolated generation keys.

[Invariants]
- Zero hard dependency on `packaging`: when `packaging` is absent, the built-in
  PEP 440 / semver comparator evaluates comma-separated interval clauses (`>=`, `<=`,
  `==`, `!=`, `<`, `>`, `~=`, `*`) identically for standard releases and pre-releases.
- Generation keys hash sorted component pins, plugin version, OS platform, and Python
  ABI so Windows (`.venv-win32`) and Linux/WSL2 (`.venv-linux`) never collide.

[Timeouts & Locks]
- Pure in-memory version parsing and cryptographic hashing (`< 1ms`); no locks or I/O.

[Side-Effect Policy]
- Pure functional helpers; mutates no files, globals, or environment state.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
import re
import sys
from typing import Any, Mapping, Sequence

from ..paths import HarnessError

SHARED_COMPONENTS: dict[str, str] = {
    "mindie-harness": "mindie-agent/harness",
    "mindie-knowledge": "mindie-agent/knowledge",
    "remote-dev": "mindie-agent/remote-dev",
    "mindie-diagnostics": "mindie-agent/diagnostics",
    "mindie-debugger": "mindie-agent/debugger",
    "mindie-profiler": "mindie-agent/profiler",
    "mindie-sim": "mindie-agent/sim",
    "npu-top": "mindie-agent/npu-top",
    "mindie-coordinator": "mindie-agent/coordinator",
}
RETIRED_COMPONENTS: frozenset[str] = frozenset({"mindie-bench"})

_VERSION_RE = re.compile(
    r"^v?(?P<release>[0-9]+(?:\.[0-9]+)*)"
    r"(?:[-._]?(?P<pre_kind>a|alpha|b|beta|rc|c|pre|preview)(?P<pre_num>[0-9]*))?"
    r"(?:\+.*)?$",
    re.IGNORECASE,
)
_CLAUSE_RE = re.compile(r"^\s*(==|!=|<=|>=|~=|<|>)\s*([^\s,]+)\s*$")
_PRE_RANK = {
    "a": -3,
    "alpha": -3,
    "b": -2,
    "beta": -2,
    "c": -1,
    "rc": -1,
    "pre": -1,
    "preview": -1,
}


def parse_version_key(version: str) -> tuple[tuple[int, ...], int, int]:
    """Parse a release version into a comparable `(release_tuple, pre_rank, pre_num)` key."""
    raw = str(version or "").strip()
    match = _VERSION_RE.match(raw)
    if match is None:
        raise ValueError(f"Invalid version string: {version!r}")
    nums = [int(part) for part in match.group("release").split(".")]
    while len(nums) > 1 and nums[-1] == 0:
        nums.pop()
    pre_kind = match.group("pre_kind")
    if not pre_kind:
        return (tuple(nums), 0, 0)
    rank = _PRE_RANK[pre_kind.lower()]
    pre_num = int(match.group("pre_num") or "0")
    return (tuple(nums), rank, pre_num)


def _stdlib_clause_matches(ver_key: tuple[tuple[int, ...], int, int], clause: str) -> bool:
    stripped = clause.strip()
    if not stripped or stripped == "*":
        return True
    match = _CLAUSE_RE.match(stripped)
    if match is None:
        raise ValueError(f"Unsupported version specifier clause: {clause!r}")
    op, target_raw = match.group(1), match.group(2)
    if op in {"==", "!="} and target_raw.endswith(".*"):
        prefix_str = target_raw[:-2].lstrip("vV")
        prefix_nums = tuple(int(p) for p in prefix_str.split("."))
        raw_nums = ver_key[0]
        padded = raw_nums + (0,) * max(0, len(prefix_nums) - len(raw_nums))
        matched = padded[: len(prefix_nums)] == prefix_nums
        return matched if op == "==" else not matched

    target_key = parse_version_key(target_raw)
    if op == "==":
        return ver_key == target_key
    if op == "!=":
        return ver_key != target_key
    if op == "<=":
        return ver_key <= target_key
    if op == ">=":
        return ver_key >= target_key
    if op == "<":
        return ver_key < target_key
    if op == ">":
        return ver_key > target_key
    if op == "~=":
        raw_parts = [int(p) for p in target_raw.lstrip("vV").split("+")[0].split("-")[0].split(".")]
        if len(raw_parts) < 2:
            raise ValueError(f"Compatible release (~=) requires at least two segments: {target_raw!r}")
        upper_parts = raw_parts[:-2] + [raw_parts[-2] + 1]
        while len(upper_parts) > 1 and upper_parts[-1] == 0:
            upper_parts.pop()
        upper_key = (tuple(upper_parts), -4, 0)
        return ver_key >= target_key and ver_key < upper_key
    raise ValueError(f"Unknown operator {op!r}")


def version_satisfies(version: str, specifier: str) -> bool:
    """Return True if `version` satisfies PEP 440 / semver `specifier`."""
    spec_text = str(specifier or "").strip()
    if not spec_text or spec_text == "*":
        parse_version_key(version)
        return True
    try:
        from packaging.specifiers import SpecifierSet  # type: ignore[import-not-found]
        from packaging.version import Version  # type: ignore[import-not-found]

        return Version(str(version).lstrip("vV")) in SpecifierSet(spec_text)
    except ImportError:
        pass
    ver_key = parse_version_key(version)
    return all(_stdlib_clause_matches(ver_key, part) for part in spec_text.split(",") if part.strip())


def select_python_abi(
    preferred_version: tuple[int, int] | None = None,
    *,
    is_windows: bool | None = None,
) -> str:
    """Select the supported Python `major.minor` ABI (`>=3.11`, default `3.12+` on Windows)."""
    win = (os.name == "nt") if is_windows is None else bool(is_windows)
    major, minor = preferred_version or (sys.version_info.major, sys.version_info.minor)
    if (major, minor) < (3, 11):
        raise HarnessError(
            f"Python >= 3.11 is required (got {major}.{minor})",
            stage="abi_select",
            reason="unsupported_python_abi",
            reportable=False,
        )
    if win and (major, minor) < (3, 12) and preferred_version is not None:
        raise HarnessError(
            f"Windows managed runtime requires Python >= 3.12 when explicitly pinned (got {major}.{minor})",
            stage="abi_select",
            reason="unsupported_python_abi",
            reportable=False,
        )
    return f"{major}.{minor}"


def compute_generation_key(
    components: Mapping[str, Mapping[str, str]],
    *,
    plugin_version: str | None = None,
    python_abi: str | None = None,
    platform_tag: str | None = None,
) -> str:
    """Compute a deterministic 24-hex generation directory key."""
    filtered = {
        str(k): {
            "version": str(v.get("version", "")),
            "revision": str(v.get("revision", "")),
        }
        for k, v in sorted(components.items())
        if k not in RETIRED_COMPONENTS
    }
    material = {
        "abi_version": 1,
        "platform": platform_tag or sys.platform,
        "python_abi": python_abi or select_python_abi(),
        "plugin_version": plugin_version or "",
        "components": filtered,
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()
    return digest[:24]


@dataclass(frozen=True)
class RuntimeSelection:
    """Resolved set of compatible component pins for one runtime generation."""

    generation_key: str
    components: dict[str, dict[str, str]] = field(default_factory=dict)
    python_abi: str = field(default_factory=select_python_abi)
    plugin_version: str | None = None
    source_sha256: str | None = None

    @classmethod
    def from_pins(
        cls,
        components: Mapping[str, Mapping[str, str]],
        *,
        plugin_version: str | None = None,
        python_abi: str | None = None,
        source_sha256: str | None = None,
        platform_tag: str | None = None,
    ) -> "RuntimeSelection":
        abi = python_abi or select_python_abi()
        clean_components = {
            str(name): {
                "version": str(meta.get("version", "")),
                "revision": str(meta.get("revision", "")),
                **({"repository": str(meta["repository"])} if "repository" in meta else {}),
            }
            for name, meta in sorted(components.items())
            if name not in RETIRED_COMPONENTS
        }
        key = compute_generation_key(
            clean_components,
            plugin_version=plugin_version,
            python_abi=abi,
            platform_tag=platform_tag,
        )
        return cls(
            generation_key=key,
            components=clean_components,
            python_abi=abi,
            plugin_version=plugin_version,
            source_sha256=source_sha256,
        )


def select_compatible_release(
    releases: Sequence[Mapping[str, Any]],
    *,
    host: str,
    host_version: str,
    installed_version: str | None = None,
    api_version: int = 1,
) -> dict[str, Any]:
    """Select the newest release compatible with `host_version` and `api_version`."""
    eligible: list[tuple[tuple[tuple[int, ...], int, int], dict[str, Any]]] = []
    installed_key = parse_version_key(installed_version) if installed_version else None

    for raw in releases:
        if raw.get("draft") or raw.get("prerelease"):
            continue
        ver = str(raw.get("version") or "").strip()
        if not ver:
            continue
        try:
            ver_key = parse_version_key(ver)
        except ValueError:
            continue
        if installed_key is not None and ver_key <= installed_key:
            continue
        compat = raw.get("compatibility") or {}
        req_api = compat.get("harness_api_version")
        if req_api is not None and int(req_api) != int(api_version):
            continue
        host_spec = (compat.get("hosts") or {}).get(host) or compat.get("specifier") or "*"
        try:
            if not version_satisfies(host_version, str(host_spec)):
                continue
        except ValueError:
            continue
        eligible.append((ver_key, dict(raw)))

    if not eligible:
        return {"status": "up_to_date", "candidate": None}
    eligible.sort(key=lambda pair: pair[0], reverse=True)
    return {"status": "candidate", "candidate": eligible[0][1]}
