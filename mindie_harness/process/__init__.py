"""Cross-platform bounded process supervision, Win32 Job Objects, and WSL2 binary resolution.

[Role]
Re-exports `Deadline`, `ProcessSpec`, `ProcessOutcome`, `run_owned`, PE subsystem
verification helpers, and POSIX/WSL2 executable resolution.

[Invariants]
- Zero `conhost.exe` console flashes on Windows (`CREATE_NO_WINDOW` without
  `CREATE_NEW_CONSOLE` or `DETACHED_PROCESS`).
- Every child tree is owned by a POSIX process group (`start_new_session=True` +
  `killpg`) or a Windows nested Job Object (`KILL_ON_JOB_CLOSE` before `ResumeThread`).

[Timeouts & Locks]
- Enforces `outer_timeout >= sum(inner_budgets) + cleanup_grace` via `Deadline`.

[Side-Effect Policy]
- Pure imports on load; OS side effects occur only when `run_owned` is called.
"""
from __future__ import annotations

from .posix import which_posix_binary
from .supervisor import (
    Deadline,
    OutputLimitError,
    ProcessCancelledError,
    ProcessExecutionError,
    ProcessOutcome,
    ProcessSpec,
    run_owned,
)
from .win32 import probe_current_job, read_pe_subsystem, verify_gui_subsystem

__all__ = [
    "Deadline",
    "OutputLimitError",
    "ProcessCancelledError",
    "ProcessExecutionError",
    "ProcessOutcome",
    "ProcessSpec",
    "probe_current_job",
    "read_pe_subsystem",
    "run_owned",
    "verify_gui_subsystem",
    "which_posix_binary",
]
