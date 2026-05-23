"""Internal API server for the Electron desktop app."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import db
from pipeline.config import get_settings
from pipeline.db import init_db
from pipeline.orchestrator import approve_job, execute_generate, publish_job, reject_job
from pipeline.publish.auth_youtube import run_oauth_flow
from pipeline.research.competitor import refresh_competitor_cache
from pipeline.render.ffmpeg_util import require_ffmpeg

app = FastAPI(title="YouTube Automations API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class GenerateRequest(BaseModel):
    topic: str
    duration: int = 12
    audio_mode: str = "coach_voice"
    niche: str = "fitness_warmup"


class PublishRequest(BaseModel):
    publish_at: str | None = None


@app.on_event("startup")
def startup() -> None:
    init_db()
    for d in (
        get_settings()["output_pending"],
        get_settings()["output_approved"],
        get_settings()["output_rejected"],
    ):
        d.mkdir(parents=True, exist_ok=True)


@app.get("/api/check")
def api_check() -> dict:
    settings = get_settings()
    ffmpeg_ok = True
    ffmpeg_msg = ""
    try:
        require_ffmpeg()
    except Exception as e:
        ffmpeg_ok = False
        ffmpeg_msg = str(e)
    music = list(settings["music_library_dir"].glob("*.mp3"))
    ready = (
        bool(settings["openai_api_key"])
        and bool(settings["pexels_api_key"])
        and ffmpeg_ok
    )
    return {
        "ready": ready,
        "openai": bool(settings["openai_api_key"]),
        "pexels": bool(settings["pexels_api_key"]),
        "youtube_api": bool(settings["youtube_api_key"]),
        "youtube_oauth": bool(settings["youtube_refresh_token"]),
        "ffmpeg": ffmpeg_ok,
        "ffmpeg_msg": ffmpeg_msg,
        "music_tracks": len(music),
    }


@app.get("/api/jobs")
def api_jobs(status: str | None = None) -> list[dict]:
    return db.list_jobs(status=status)


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> dict:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return dict(job)


@app.get("/api/jobs/{job_id}/video")
def api_job_video(job_id: str) -> FileResponse:
    job = db.get_job(job_id)
    if not job or not job.get("video_path"):
        raise HTTPException(404, "Video not found")
    path = Path(job["video_path"])
    if not path.exists():
        raise HTTPException(404, "Video file missing")
    return FileResponse(
        path,
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"},
    )


@app.get("/api/jobs/{job_id}/metadata")
def api_job_metadata(job_id: str) -> dict:
    job = db.get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if not job.get("metadata_json"):
        raise HTTPException(404, "No metadata yet")
    return json.loads(job["metadata_json"])


@app.post("/api/generate")
def api_generate(req: GenerateRequest, bg: BackgroundTasks) -> dict:
    db.init_db()
    job_id = db.create_job(
        topic=req.topic, niche=req.niche, audio_mode=req.audio_mode
    )

    def task() -> None:
        try:
            execute_generate(
                job_id,
                topic=req.topic,
                duration_minutes=req.duration,
                audio_mode=req.audio_mode,
                niche=req.niche,
            )
        except Exception:
            pass

    bg.add_task(task)
    return {"job_id": job_id, "status": "generating"}


@app.post("/api/jobs/{job_id}/approve")
def api_approve(job_id: str) -> dict:
    try:
        approve_job(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "job": db.get_job(job_id)}


@app.post("/api/jobs/{job_id}/reject")
def api_reject(job_id: str) -> dict:
    try:
        reject_job(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


@app.post("/api/jobs/{job_id}/publish")
def api_publish(job_id: str, body: PublishRequest) -> dict:
    try:
        video_id = publish_job(job_id, publish_at=body.publish_at)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    return {"ok": True, "youtube_video_id": video_id}


@app.post("/api/research")
def api_research() -> dict:
    try:
        path = refresh_competitor_cache()
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    return {"ok": True, "path": str(path)}


@app.post("/api/auth-youtube")
def api_auth_youtube() -> dict:
    try:
        run_oauth_flow()
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8765)
