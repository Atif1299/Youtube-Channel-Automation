from __future__ import annotations

import shutil
import subprocess

from pipeline.job_control import (
    JobCancelledError,
    current_job_id,
    is_cancelled,
    register_proc,
    unregister_proc,
)
from pathlib import Path


class FFmpegError(RuntimeError):
    pass


def require_ffmpeg() -> str:
    path = shutil.which("ffmpeg")
    if not path:
        raise FFmpegError(
            "ffmpeg not found on PATH. Install from https://ffmpeg.org/download.html"
        )
    return path


def run_ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    job_id = current_job_id.get()
    if job_id and is_cancelled(job_id):
        raise JobCancelledError(f"Job {job_id} was cancelled")

    require_ffmpeg()
    cmd = ["ffmpeg", "-y", *args]
    proc = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if job_id:
        register_proc(job_id, proc)
    try:
        _, stderr = proc.communicate()
    finally:
        if job_id:
            unregister_proc(job_id)
    if job_id and is_cancelled(job_id):
        raise JobCancelledError(f"Job {job_id} was cancelled")
    if proc.returncode != 0:
        raise FFmpegError(stderr[-2000:] if stderr else "ffmpeg failed")


def probe_duration(path: Path) -> float | None:
    """Return media duration in seconds via ffprobe, or None on failure."""
    require_ffmpeg()
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    proc = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return None
