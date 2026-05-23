from __future__ import annotations

import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from pipeline.config import ROOT, get_settings
from pipeline.models import VideoMetadata


def _get_credentials() -> Credentials:
    settings = get_settings()
    token_path = ROOT / "token.json"
    if token_path.exists():
        data = json.loads(token_path.read_text(encoding="utf-8"))
        creds = Credentials.from_authorized_user_info(data)
    else:
        refresh = settings["youtube_refresh_token"]
        client_id = settings["youtube_client_id"]
        client_secret = settings["youtube_client_secret"]
        if not all([refresh, client_id, client_secret]):
            raise ValueError(
                "YouTube credentials missing. Run: python main.py auth-youtube"
            )
        creds = Credentials(
            token=None,
            refresh_token=refresh,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
        )
    if creds.expired and creds.refresh_token:
        from google.auth.transport.requests import Request

        creds.refresh(Request())
    return creds


def upload_video(
    video_path: Path,
    metadata: VideoMetadata,
    privacy: str = "private",
    publish_at: str | None = None,
) -> str:
    creds = _get_credentials()
    youtube = build("youtube", "v3", credentials=creds)

    body: dict = {
        "snippet": {
            "title": metadata.title[:100],
            "description": metadata.description[:5000],
            "tags": metadata.tags[:30],
            "categoryId": metadata.category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }
    if metadata.contains_synthetic_media:
        body["status"]["containsSyntheticMedia"] = True
    if publish_at:
        body["status"]["privacyStatus"] = "private"
        body["status"]["publishAt"] = publish_at

    media = MediaFileUpload(
        str(video_path),
        chunksize=1024 * 1024,
        resumable=True,
        mimetype="video/mp4",
    )
    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )
    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"Upload progress: {pct}%")
    return response["id"]
