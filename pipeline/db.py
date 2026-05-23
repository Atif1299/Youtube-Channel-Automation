from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pipeline.config import get_settings

STATUSES = (
    "draft",
    "rendered",
    "pending_review",
    "approved",
    "rejected",
    "uploading",
    "scheduled",
    "published",
    "failed",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    settings = get_settings()
    settings["jobs_db"].parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                topic TEXT,
                niche TEXT,
                audio_mode TEXT,
                script_json TEXT,
                metadata_json TEXT,
                video_path TEXT,
                work_dir TEXT,
                youtube_video_id TEXT,
                publish_at TEXT,
                error TEXT,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )


@contextmanager
def _connect():
    path = get_settings()["jobs_db"]
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def create_job(
    topic: str,
    niche: str = "fitness_warmup",
    audio_mode: str = "music_only",
) -> str:
    job_id = uuid4().hex[:12]
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, status, topic, niche, audio_mode, created_at, updated_at)
            VALUES (?, 'draft', ?, ?, ?, ?, ?)
            """,
            (job_id, topic, niche, audio_mode, _now(), _now()),
        )
    return job_id


def update_job(job_id: str, **fields: Any) -> None:
    allowed = {
        "status",
        "script_json",
        "metadata_json",
        "video_path",
        "work_dir",
        "youtube_video_id",
        "publish_at",
        "error",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [job_id]
    with _connect() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", values)


def get_job(job_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(status: str | None = None) -> list[dict]:
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def job_script(job: dict) -> dict | None:
    if not job.get("script_json"):
        return None
    return json.loads(job["script_json"])


def job_metadata(job: dict) -> dict | None:
    if not job.get("metadata_json"):
        return None
    return json.loads(job["metadata_json"])
