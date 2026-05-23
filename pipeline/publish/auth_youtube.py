from __future__ import annotations

import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from pipeline.config import ROOT, get_settings

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def run_oauth_flow() -> str:
    settings = get_settings()
    client_id = settings["youtube_client_id"]
    client_secret = settings["youtube_client_secret"]
    if not client_id or not client_secret:
        raise ValueError(
            "Set YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET in .env, "
            "or place client_secret.json in project root."
        )

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }
    secret_path = ROOT / "client_secret.json"
    if secret_path.exists():
        flow = InstalledAppFlow.from_client_secrets_file(
            str(secret_path), SCOPES
        )
    else:
        flow = InstalledAppFlow.from_client_config(client_config, SCOPES)

    creds = flow.run_local_server(port=0)
    token = creds.refresh_token or creds.token
    env_path = ROOT / ".env"
    _append_env_var(env_path, "YOUTUBE_REFRESH_TOKEN", token)
    token_path = ROOT / "token.json"
    token_path.write_text(creds.to_json(), encoding="utf-8")
    return token


def _append_env_var(env_path: Path, key: str, value: str) -> None:
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    lines = [ln for ln in lines if not ln.startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
