from __future__ import annotations

import time
from typing import Any

import httpx

YOUTUBE_API = "https://www.googleapis.com/youtube/v3"
DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=45.0)
MAX_RETRIES = 3


class YouTubeResearchError(Exception):
    pass


def youtube_get(path: str, params: dict[str, Any], api_key: str) -> dict:
    """GET YouTube Data API v3 with retries on transient network/SSL failures."""
    params = {**params, "key": api_key}
    last_err: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
                resp = client.get(f"{YOUTUBE_API}/{path}", params=params)
            if resp.status_code == 403:
                raise YouTubeResearchError(
                    "YouTube API access denied (403). Check YOUTUBE_API_KEY and quota."
                )
            if resp.status_code == 429:
                raise YouTubeResearchError("YouTube API rate limit (429). Try again later.")
            resp.raise_for_status()
            return resp.json()
        except YouTubeResearchError:
            raise
        except (
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.ConnectError,
            httpx.RemoteProtocolError,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
        ) as e:
            last_err = e
            if attempt < MAX_RETRIES - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise YouTubeResearchError(
                "Could not reach YouTube API (network/SSL timeout). "
                "Check your internet connection and try again."
            ) from e
        except httpx.HTTPStatusError as e:
            raise YouTubeResearchError(
                f"YouTube API error ({e.response.status_code}). Try again later."
            ) from e
        except httpx.HTTPError as e:
            raise YouTubeResearchError(f"YouTube API request failed: {e}") from e

    raise YouTubeResearchError("YouTube API request failed") from last_err
