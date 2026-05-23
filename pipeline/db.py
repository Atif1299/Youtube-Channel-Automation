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
    "generating",
    "rendered",
    "pending_review",
    "approved",
    "rejected",
    "uploading",
    "scheduled",
    "published",
    "failed",
)

_PROGRESS_COLUMNS = (
    ("stage", "TEXT"),
    ("stage_message", "TEXT"),
    ("progress_pct", "INTEGER"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migrate(conn: sqlite3.Connection) -> None:
    cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
    }
    for name, col_type in _PROGRESS_COLUMNS:
        if name not in cols:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {name} {col_type}")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ideas (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            notes TEXT,
            source TEXT NOT NULL DEFAULT 'manual',
            source_video_id TEXT,
            source_channel TEXT,
            view_count INTEGER,
            period TEXT,
            niche TEXT DEFAULT 'fitness_warmup',
            status TEXT NOT NULL DEFAULT 'saved',
            created_at TEXT,
            updated_at TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS script_drafts (
            id TEXT PRIMARY KEY,
            idea_id TEXT,
            label TEXT,
            topic TEXT NOT NULL,
            duration_min INTEGER DEFAULT 12,
            audio_mode TEXT DEFAULT 'coach_voice',
            video_mode TEXT DEFAULT 'stock',
            script_json TEXT,
            created_at TEXT,
            updated_at TEXT
        )
        """
    )


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
                stage TEXT,
                stage_message TEXT,
                progress_pct INTEGER,
                created_at TEXT,
                updated_at TEXT
            )
            """
        )
        _migrate(conn)


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
        "stage",
        "stage_message",
        "progress_pct",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [job_id]
    with _connect() as conn:
        conn.execute(f"UPDATE jobs SET {cols} WHERE id = ?", values)


def update_job_stage(
    job_id: str,
    stage: str,
    message: str,
    progress_pct: int | None = None,
) -> None:
    fields: dict[str, Any] = {
        "stage": stage,
        "stage_message": message,
    }
    if progress_pct is not None:
        fields["progress_pct"] = progress_pct
    update_job(job_id, **fields)


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


def delete_job(job_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    return cur.rowcount > 0


def job_script(job: dict) -> dict | None:
    if not job.get("script_json"):
        return None
    return json.loads(job["script_json"])


def job_metadata(job: dict) -> dict | None:
    if not job.get("metadata_json"):
        return None
    return json.loads(job["metadata_json"])


def create_idea(
    title: str,
    *,
    notes: str = "",
    source: str = "manual",
    source_video_id: str | None = None,
    source_channel: str | None = None,
    view_count: int | None = None,
    period: str | None = None,
    niche: str = "fitness_warmup",
) -> str:
    idea_id = uuid4().hex[:12]
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO ideas (
                id, title, notes, source, source_video_id, source_channel,
                view_count, period, niche, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'saved', ?, ?)
            """,
            (
                idea_id,
                title,
                notes,
                source,
                source_video_id,
                source_channel,
                view_count,
                period,
                niche,
                _now(),
                _now(),
            ),
        )
    return idea_id


def update_idea(idea_id: str, **fields: Any) -> None:
    allowed = {
        "title",
        "notes",
        "source",
        "source_video_id",
        "source_channel",
        "view_count",
        "period",
        "niche",
        "status",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [idea_id]
    with _connect() as conn:
        conn.execute(f"UPDATE ideas SET {cols} WHERE id = ?", values)


def get_idea(idea_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM ideas WHERE id = ?", (idea_id,)).fetchone()
    return dict(row) if row else None


def list_ideas(status: str | None = None) -> list[dict]:
    with _connect() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM ideas WHERE status = ? ORDER BY updated_at DESC",
                (status,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM ideas ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_idea(idea_id: str) -> bool:
    with _connect() as conn:
        conn.execute("UPDATE script_drafts SET idea_id = NULL WHERE idea_id = ?", (idea_id,))
        cur = conn.execute("DELETE FROM ideas WHERE id = ?", (idea_id,))
    return cur.rowcount > 0


def create_script_draft(
    topic: str,
    script_json: str,
    *,
    idea_id: str | None = None,
    label: str = "",
    duration_min: int = 12,
    audio_mode: str = "coach_voice",
    video_mode: str = "stock",
) -> str:
    draft_id = uuid4().hex[:12]
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO script_drafts (
                id, idea_id, label, topic, duration_min, audio_mode, video_mode,
                script_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft_id,
                idea_id,
                label or f"Draft {draft_id[:6]}",
                topic,
                duration_min,
                audio_mode,
                video_mode,
                script_json,
                _now(),
                _now(),
            ),
        )
    return draft_id


def update_script_draft(draft_id: str, **fields: Any) -> None:
    allowed = {
        "idea_id",
        "label",
        "topic",
        "duration_min",
        "audio_mode",
        "video_mode",
        "script_json",
    }
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    updates["updated_at"] = _now()
    cols = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [draft_id]
    with _connect() as conn:
        conn.execute(f"UPDATE script_drafts SET {cols} WHERE id = ?", values)


def get_script_draft(draft_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM script_drafts WHERE id = ?", (draft_id,)).fetchone()
    return dict(row) if row else None


def list_script_drafts(idea_id: str | None = None) -> list[dict]:
    with _connect() as conn:
        if idea_id:
            rows = conn.execute(
                "SELECT * FROM script_drafts WHERE idea_id = ? ORDER BY created_at DESC",
                (idea_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM script_drafts ORDER BY created_at DESC"
            ).fetchall()
    return [dict(r) for r in rows]


def delete_script_draft(draft_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM script_drafts WHERE id = ?", (draft_id,))
    return cur.rowcount > 0
