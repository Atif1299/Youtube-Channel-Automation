from __future__ import annotations

import shutil
import subprocess
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
    require_ffmpeg()
    cmd = ["ffmpeg", "-y", *args]
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FFmpegError(result.stderr[-2000:] if result.stderr else "ffmpeg failed")
