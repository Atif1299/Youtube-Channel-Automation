from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from pipeline.config import get_settings, load_niche
from pipeline.research.youtube_client import YOUTUBE_API, YouTubeResearchError, youtube_get

__all__ = [
    "YOUTUBE_API",
    "YouTubeResearchError",
    "refresh_competitor_cache",
    "load_competitor_context",
    "_handle_to_channel_id",
    "_channel_uploads_playlist",
    "_video_details",
    "_parse_duration",
]


def _handle_to_channel_id(handle: str, api_key: str) -> str | None:
    handle = handle.lstrip("@")
    data = youtube_get("channels", {"part": "id", "forHandle": handle}, api_key)
    items = data.get("items", [])
    return items[0]["id"] if items else None


def _channel_uploads_playlist(channel_id: str, api_key: str) -> str | None:
    data = youtube_get("channels", {"part": "contentDetails", "id": channel_id}, api_key)
    items = data.get("items", [])
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def _playlist_videos(playlist_id: str, api_key: str, max_results: int = 50) -> list[str]:
    video_ids: list[str] = []
    page_token: str | None = None
    while len(video_ids) < max_results:
        batch = min(50, max_results - len(video_ids))
        params: dict = {
            "part": "contentDetails",
            "playlistId": playlist_id,
            "maxResults": batch,
        }
        if page_token:
            params["pageToken"] = page_token
        data = youtube_get("playlistItems", params, api_key)
        for item in data.get("items", []):
            vid = item.get("contentDetails", {}).get("videoId")
            if vid:
                video_ids.append(vid)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return video_ids


def _video_details(video_ids: list[str], api_key: str) -> list[dict]:
    if not video_ids:
        return []
    data = youtube_get(
        "videos",
        {"part": "snippet,contentDetails,statistics", "id": ",".join(video_ids)},
        api_key,
    )
    return data.get("items", [])


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
        video_ids = _playlist_videos(playlist, api_key, max_results=50)
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
