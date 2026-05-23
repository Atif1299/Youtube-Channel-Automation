from __future__ import annotations

import random
import shutil
from pathlib import Path

import httpx

from pipeline.config import get_settings

PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"


def _local_clip_for_query(query: str) -> Path | None:
    clips_dir: Path = get_settings()["local_clips_dir"]
    if not clips_dir.exists():
        return None
    query_tokens = set(query.lower().replace("-", " ").split())
    candidates = list(clips_dir.glob("*.mp4")) + list(clips_dir.glob("*.mov"))
    if not candidates:
        return None
    scored: list[tuple[int, Path]] = []
    for path in candidates:
        name_tokens = set(path.stem.lower().replace("-", " ").replace("_", " ").split())
        score = len(query_tokens & name_tokens)
        scored.append((score, path))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    if scored[0][0] > 0:
        return scored[0][1]
    return random.choice(candidates)


def fetch_pexels_clip(query: str, min_duration: int = 5) -> Path | None:
    settings = get_settings()
    api_key = settings["pexels_api_key"]
    if not api_key:
        return _local_clip_for_query(query)

    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": 8, "orientation": "landscape"}
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.get(PEXELS_VIDEO_SEARCH, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        return _local_clip_for_query(query)

    videos = data.get("videos", [])
    if not videos:
        return _local_clip_for_query(query)

    random.shuffle(videos)
    for video in videos:
        files = sorted(
            video.get("video_files", []),
            key=lambda f: f.get("width", 0),
            reverse=True,
        )
        for vf in files:
            if vf.get("width", 0) < 1280:
                continue
            link = vf.get("link")
            if not link:
                continue
            duration = video.get("duration", 0)
            if duration and duration < min_duration:
                continue
            return _download_video(link, query)

    return _local_clip_for_query(query)


def _download_video(url: str, query: str) -> Path | None:
    settings = get_settings()
    dest_dir = settings["root"] / "assets" / "output" / ".cache" / "pexels"
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in query)[:40]
    dest = dest_dir / f"{safe}_{random.randint(1000, 9999)}.mp4"
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
        return dest
    except httpx.HTTPError:
        return None


def resolve_scene_clip(query: str, min_duration: int = 5) -> Path | None:
    local = _local_clip_for_query(query)
    if local:
        return local
    return fetch_pexels_clip(query, min_duration=min_duration)
