from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline.config import get_settings, load_niche
from pipeline.research.competitor import (
    _channel_uploads_playlist,
    _handle_to_channel_id,
    _parse_duration,
    _video_details,
    refresh_competitor_cache,
)
from pipeline.research.youtube_client import YouTubeResearchError, youtube_get

PERIOD_DAYS = {
    "today": 1,
    "1d": 1,
    "7d": 7,
    "30d": 30,
    "90d": 90,
}


def _period_start(period: str) -> datetime:
    days = PERIOD_DAYS.get(period, 7)
    return datetime.now(timezone.utc) - timedelta(days=days)


def _playlist_videos_since(
    playlist_id: str,
    since: datetime,
    api_key: str,
    max_videos: int = 50,
) -> list[str]:
    """Fetch upload playlist newest-first; stop when videos are older than `since`."""
    video_ids: list[str] = []
    page_token: str | None = None

    while len(video_ids) < max_videos:
        params: dict = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": min(50, max_videos - len(video_ids)),
        }
        if page_token:
            params["pageToken"] = page_token
        data = youtube_get("playlistItems", params, api_key)
        items = data.get("items", [])
        if not items:
            break

        for item in items:
            pub = item.get("snippet", {}).get("publishedAt", "")
            if pub:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                if pub_dt < since:
                    return video_ids
            vid = item.get("contentDetails", {}).get("videoId")
            if vid:
                video_ids.append(vid)

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return video_ids


def _normalize_video(item: dict, *, channel_handle: str = "", source: str = "competitor") -> dict:
    snippet = item.get("snippet", {})
    stats = item.get("statistics", {})
    thumbs = snippet.get("thumbnails", {})
    thumb = thumbs.get("medium") or thumbs.get("default") or {}
    video_id = item["id"]
    published = snippet.get("publishedAt", "")
    views = int(stats.get("viewCount", 0))
    duration_sec = _parse_duration(item.get("contentDetails", {}).get("duration", "PT0S"))
    days_old = 1
    if published:
        pub_dt = datetime.fromisoformat(published.replace("Z", "+00:00"))
        days_old = max(1, (datetime.now(timezone.utc) - pub_dt).days or 1)
    return {
        "video_id": video_id,
        "title": snippet.get("title", ""),
        "published_at": published,
        "duration_sec": duration_sec,
        "view_count": views,
        "views_per_day": round(views / days_old, 1),
        "channel_handle": channel_handle,
        "source": source,
        "tags": snippet.get("tags", [])[:15],
        "thumbnail_url": thumb.get("url", ""),
        "url": f"https://www.youtube.com/watch?v={video_id}",
    }


def fetch_competitor_trending(period: str = "7d", niche_name: str = "fitness_warmup") -> list[dict]:
    settings = get_settings()
    api_key = settings["youtube_api_key"]
    if not api_key:
        raise YouTubeResearchError("YOUTUBE_API_KEY is required for research")

    niche = load_niche(niche_name)
    since = _period_start(period)
    results: list[dict] = []
    errors: list[str] = []

    for ref in niche.get("reference_channels", []):
        handle = ref.get("handle", "")
        try:
            channel_id = _handle_to_channel_id(handle, api_key)
            if not channel_id:
                continue
            playlist = _channel_uploads_playlist(channel_id, api_key)
            if not playlist:
                continue
            video_ids = _playlist_videos_since(playlist, since, api_key, max_videos=50)
            if not video_ids:
                continue
            for batch_start in range(0, len(video_ids), 50):
                batch = video_ids[batch_start : batch_start + 50]
                for item in _video_details(batch, api_key):
                    pub = item.get("snippet", {}).get("publishedAt", "")
                    if not pub:
                        continue
                    pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    if pub_dt < since:
                        continue
                    results.append(
                        _normalize_video(item, channel_handle=handle, source="competitor")
                    )
        except YouTubeResearchError as e:
            errors.append(f"{handle}: {e}")
            continue

    if not results and errors:
        raise YouTubeResearchError("; ".join(errors))

    results.sort(key=lambda v: v["view_count"], reverse=True)
    return results


def fetch_niche_trending(
    period: str = "7d",
    query: str | None = None,
    niche_name: str = "fitness_warmup",
    max_results: int = 25,
) -> list[dict]:
    settings = get_settings()
    api_key = settings["youtube_api_key"]
    if not api_key:
        raise YouTubeResearchError("YOUTUBE_API_KEY is required for research")

    niche = load_niche(niche_name)
    since = _period_start(period)
    published_after = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    q = query or " ".join(niche.get("keywords_seed", [])[:3])

    params = {
        "part": "snippet",
        "type": "video",
        "order": "viewCount",
        "publishedAfter": published_after,
        "q": q,
        "maxResults": min(max_results, 50),
        "videoDuration": "medium",
        "relevanceLanguage": "en",
    }
    data = youtube_get("search", params, api_key)
    video_ids = [
        item["id"]["videoId"]
        for item in data.get("items", [])
        if item.get("id", {}).get("videoId")
    ]
    if not video_ids:
        return []

    results = []
    for item in _video_details(video_ids, api_key):
        results.append(_normalize_video(item, channel_handle="", source="niche"))
    results.sort(key=lambda v: v["view_count"], reverse=True)
    return results


def fetch_trending(
    period: str = "7d",
    source: str = "both",
    query: str | None = None,
    niche_name: str = "fitness_warmup",
) -> dict:
    if period not in PERIOD_DAYS:
        raise ValueError(f"Invalid period: {period}. Use one of {list(PERIOD_DAYS)}")

    competitors: list[dict] = []
    niche: list[dict] = []
    errors: list[str] = []

    if source in ("competitors", "both"):
        try:
            competitors = fetch_competitor_trending(period, niche_name)
        except YouTubeResearchError as e:
            errors.append(str(e))
    if source in ("niche", "both"):
        try:
            niche = fetch_niche_trending(period, query, niche_name)
        except YouTubeResearchError as e:
            errors.append(str(e))

    combined = competitors + niche
    if not combined and errors:
        raise YouTubeResearchError("; ".join(errors))

    combined.sort(key=lambda v: v["view_count"], reverse=True)
    seen: set[str] = set()
    deduped: list[dict] = []
    for v in combined:
        if v["video_id"] in seen:
            continue
        seen.add(v["video_id"])
        deduped.append(v)

    return {
        "period": period,
        "source": source,
        "query": query,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "competitors": competitors,
        "niche": niche,
        "combined": deduped,
        "warnings": errors,
    }


def load_research_cache() -> dict:
    settings = get_settings()
    path: Path = settings["competitor_cache"]
    if not path.exists():
        return {"updated_at": None, "channels": [], "title_patterns": []}
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "PERIOD_DAYS",
    "YouTubeResearchError",
    "fetch_trending",
    "load_research_cache",
    "refresh_competitor_cache",
]
