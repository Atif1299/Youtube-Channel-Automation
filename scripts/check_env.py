#!/usr/bin/env python3
"""Verify environment (dev/debug only)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.config import get_settings
from pipeline.render.ffmpeg_util import require_ffmpeg


def main() -> int:
    settings = get_settings()
    checks = [
        ("OPENAI_API_KEY", bool(settings["openai_api_key"])),
        ("PEXELS_API_KEY", bool(settings["pexels_api_key"])),
        ("LOCAL_CLIPS_DIR", settings["local_clips_dir"].exists()),
        ("MUSIC_LIBRARY_DIR", settings["music_library_dir"].exists()),
    ]
    ok = True
    for name, passed in checks:
        print(f"{'OK' if passed else 'MISSING':7} {name}")
        if not passed and name.endswith("_KEY"):
            ok = False
    try:
        ff = require_ffmpeg()
        print(f"OK      ffmpeg ({ff})")
    except Exception as e:
        print(f"MISSING ffmpeg — {e}")
        ok = False
    music = list(settings["music_library_dir"].glob("*.mp3"))
    print(f"        music tracks: {len(music)}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
