from __future__ import annotations

import subprocess
from contextvars import ContextVar

current_job_id: ContextVar[str | None] = ContextVar("current_job_id", default=None)

_cancelled: set[str] = set()
_procs: dict[str, subprocess.Popen] = {}


class JobCancelledError(Exception):
    pass


def is_cancelled(job_id: str) -> bool:
    return job_id in _cancelled


def cancel_job(job_id: str) -> None:
    _cancelled.add(job_id)
    proc = _procs.get(job_id)
    if proc and proc.poll() is None:
        proc.kill()


def clear_cancel(job_id: str) -> None:
    _cancelled.discard(job_id)


def register_proc(job_id: str, proc: subprocess.Popen) -> None:
    _procs[job_id] = proc


def unregister_proc(job_id: str) -> None:
    _procs.pop(job_id, None)
