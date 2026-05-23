from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import httpx

from pipeline.config import get_settings, load_niche

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"


def _handle_to_channel_id(handle: str, api_key: str) -> str | None:
    handle = handle.lstrip("@")
    params = {"part": "id", "forHandle": handle, "key": api_key}
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{YOUTUBE_API}/channels", params=params)
        resp.raise_for_status()
        items = resp.json().get("items", [])
    return items[0]["id"] if items else None


def _channel_uploads_playlist(channel_id: str, api_key: str) -> str | None:
    params = {"part": "contentDetails", "id": channel_id, "key": api_key}
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{YOUTUBE_API}/channels", params=params)
        resp.raise_for_status()
        items = resp.json().get("items", [])
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _playlist_videos(playlist_id: str, api_key: str, max_results: int = 15) -> list[str]:
    params = {
        "part": "contentDetails",
        "playlistId": playlist_id,
        "maxResults": max_results,
        "key": api_key,
    }
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{YOUTUBE_API}/playlistItems", params=params)
        resp.raise_for_status()
        items = resp.json().get("items", [])
    return [i["contentDetails"]["videoId"] for i in items if "videoId" in i["contentDetails"]]


def _video_details(video_ids: list[str], api_key: str) -> list[dict]:
    if not video_ids:
        return []
    params = {
        "part": "snippet,contentDetails,statistics",
        "id": ",".join(video_ids),
        "key": api_key,
    }
    with httpx.Client(timeout=30) as client:
        resp = client.get(f"{YOUTUBE_API}/videos", params=params)
        resp.raise_for_status()
        return resp.json().get("items", [])


def _parse_duration(iso: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso)
    if not m:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def refresh_competitor_cache() -> Path:
    settings = get_settings()
    api_key = settings["youtube_api_key"]
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY is required for competitor research")

    niche = load_niche()
    cache_path: Path = settings["competitor_cache"]
    channels_out: list[dict] = []
    all_titles: list[str] = []

    for ref in niche.get("reference_channels", []):
        handle = ref.get("handle", "")
        channel_id = _handle_to_channel_id(handle, api_key)
        if not channel_id:
            continue
        playlist = _channel_uploads_playlist(channel_id, api_key)
        if not playlist:
            continue
        video_ids = _playlist_videos(playlist, api_key)
        details = _video_details(video_ids, api_key)
        videos = []
        for v in details:
            title = v["snippet"]["title"]
            all_titles.append(title)
            videos.append(
                {
                    "video_id": v["id"],
                    "title": title,
                    "published_at": v["snippet"].get("publishedAt"),
                    "duration_sec": _parse_duration(
                        v["contentDetails"].get("duration", "PT0S")
                    ),
                    "view_count": int(v["statistics"].get("viewCount", 0)),
                    "tags": v["snippet"].get("tags", [])[:15],
                }
            )
        channels_out.append({"handle": handle, "channel_id": channel_id, "videos": videos})

    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "channels": channels_out,
        "title_patterns": _extract_title_patterns(all_titles),
    }
    cache_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return cache_path


def _extract_title_patterns(titles: list[str]) -> list[str]:
    patterns: list[str] = []
    for t in titles[:30]:
        if re.search(r"\d+\s*min", t, re.I):
            patterns.append("duration_min_in_title")
        if "|" in t:
            patterns.append("pipe_separator")
        if re.search(r"warm.?up|mobility|stretch", t, re.I):
            patterns.append("warmup_mobility_keyword")
    return sorted(set(patterns))


def load_competitor_context() -> str:
    settings = get_settings()
    path: Path = settings["competitor_cache"]
    if not path.exists():
        return ""
    data = json.loads(path.read_text(encoding="utf-8"))
    lines = ["Competitor title patterns (emulate structure, not exact wording):"]
    for p in data.get("title_patterns", []):
        lines.append(f"- {p}")
    for ch in data.get("channels", [])[:3]:
        for v in ch.get("videos", [])[:5]:
            lines.append(f"- Example: {v.get('title')}")
    return "\n".join(lines)
