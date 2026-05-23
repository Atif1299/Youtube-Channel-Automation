"""Internal API server for the Electron desktop app."""

from __future__ import annotations

import json
import sys
import threading
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
from pipeline.orchestrator import (
    approve_job,
    delete_job,
    execute_generate,
    execute_render_from_draft,
    generate_script_draft,
    publish_job,
    reject_job,
)
from pipeline.publish.auth_youtube import run_oauth_flow
from pipeline.research.competitor import refresh_competitor_cache
from pipeline.research.trending import YouTubeResearchError, fetch_trending, load_research_cache
from pipeline.render.ffmpeg_util import require_ffmpeg
from pipeline.models import VideoScript

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
    video_mode: str = "stock"


class PublishRequest(BaseModel):
    publish_at: str | None = None


class IdeaCreateRequest(BaseModel):
    title: str
    notes: str = ""
    source: str = "manual"
    source_video_id: str | None = None
    source_channel: str | None = None
    view_count: int | None = None
    period: str | None = None
    niche: str = "fitness_warmup"


class IdeaUpdateRequest(BaseModel):
    title: str | None = None
    notes: str | None = None
    status: str | None = None


class DraftGenerateRequest(BaseModel):
    topic: str
    duration: int = 12
    audio_mode: str = "coach_voice"
    niche: str = "fitness_warmup"
    video_mode: str = "stock"
    idea_id: str | None = None
    label: str = ""
    extra_context: str = ""


class DraftUpdateRequest(BaseModel):
    label: str | None = None
    topic: str | None = None
    script_json: str | None = None
    duration_min: int | None = None
    audio_mode: str | None = None
    video_mode: str | None = None


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
        "gemini": bool(settings["gemini_api_key"]),
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
                video_mode=req.video_mode,
            )
        except Exception as e:
            job = db.get_job(job_id)
            if job and job.get("status") == "generating":
                db.update_job(
                    job_id,
                    status="failed",
                    error=str(e),
                    stage="failed",
                    stage_message=str(e),
                )

    bg.add_task(
        lambda: threading.Thread(
            target=task,
            daemon=True,
            name=f"generate-{job_id}",
        ).start()
    )
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


@app.delete("/api/jobs/{job_id}")
def api_delete_job(job_id: str) -> dict:
    try:
        delete_job(job_id)
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
@app.post("/api/research/refresh")
def api_research_refresh() -> dict:
    try:
        path = refresh_competitor_cache()
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    return {"ok": True, "path": str(path)}


@app.get("/api/research/cache")
def api_research_cache() -> dict:
    return load_research_cache()


@app.get("/api/research/trending")
def api_research_trending(
    period: str = "7d",
    source: str = "both",
    q: str | None = None,
) -> dict:
    try:
        return fetch_trending(period=period, source=source, query=q)
    except YouTubeResearchError as e:
        raise HTTPException(400, str(e)) from e
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.get("/api/ideas")
def api_list_ideas(status: str | None = None) -> list[dict]:
    return db.list_ideas(status=status)


@app.post("/api/ideas")
def api_create_idea(body: IdeaCreateRequest) -> dict:
    idea_id = db.create_idea(
        body.title,
        notes=body.notes,
        source=body.source,
        source_video_id=body.source_video_id,
        source_channel=body.source_channel,
        view_count=body.view_count,
        period=body.period,
        niche=body.niche,
    )
    return {"ok": True, "idea": db.get_idea(idea_id)}


@app.get("/api/ideas/{idea_id}")
def api_get_idea(idea_id: str) -> dict:
    idea = db.get_idea(idea_id)
    if not idea:
        raise HTTPException(404, "Idea not found")
    return idea


@app.patch("/api/ideas/{idea_id}")
def api_update_idea(idea_id: str, body: IdeaUpdateRequest) -> dict:
    if not db.get_idea(idea_id):
        raise HTTPException(404, "Idea not found")
    fields = body.model_dump(exclude_unset=True)
    db.update_idea(idea_id, **fields)
    return {"ok": True, "idea": db.get_idea(idea_id)}


@app.delete("/api/ideas/{idea_id}")
def api_delete_idea(idea_id: str) -> dict:
    if not db.delete_idea(idea_id):
        raise HTTPException(404, "Idea not found")
    return {"ok": True}


@app.get("/api/drafts")
def api_list_drafts(idea_id: str | None = None) -> list[dict]:
    return db.list_script_drafts(idea_id=idea_id)


@app.get("/api/drafts/{draft_id}")
def api_get_draft(draft_id: str) -> dict:
    draft = db.get_script_draft(draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found")
    return draft


@app.post("/api/drafts/generate")
def api_generate_draft(body: DraftGenerateRequest) -> dict:
    try:
        draft_id = generate_script_draft(
            topic=body.topic,
            duration_minutes=body.duration,
            audio_mode=body.audio_mode,
            niche=body.niche,
            video_mode=body.video_mode,
            idea_id=body.idea_id,
            label=body.label,
            extra_context=body.extra_context,
        )
    except Exception as e:
        raise HTTPException(500, str(e)) from e
    return {"ok": True, "draft_id": draft_id, "draft": db.get_script_draft(draft_id)}


@app.patch("/api/drafts/{draft_id}")
def api_update_draft(draft_id: str, body: DraftUpdateRequest) -> dict:
    if not db.get_script_draft(draft_id):
        raise HTTPException(404, "Draft not found")
    fields = body.model_dump(exclude_unset=True)
    if fields.get("script_json"):
        VideoScript.model_validate_json(fields["script_json"])
    db.update_script_draft(draft_id, **fields)
    return {"ok": True, "draft": db.get_script_draft(draft_id)}


@app.delete("/api/drafts/{draft_id}")
def api_delete_draft(draft_id: str) -> dict:
    if not db.delete_script_draft(draft_id):
        raise HTTPException(404, "Draft not found")
    return {"ok": True}


@app.post("/api/drafts/{draft_id}/generate-video")
def api_draft_generate_video(draft_id: str, bg: BackgroundTasks) -> dict:
    draft = db.get_script_draft(draft_id)
    if not draft:
        raise HTTPException(404, "Draft not found")

    job_id = db.create_job(
        topic=draft["topic"],
        niche="fitness_warmup",
        audio_mode=draft.get("audio_mode") or "coach_voice",
    )

    def task() -> None:
        try:
            execute_render_from_draft(draft_id, job_id=job_id)
        except Exception as e:
            job = db.get_job(job_id)
            if job and job.get("status") == "generating":
                db.update_job(
                    job_id,
                    status="failed",
                    error=str(e),
                    stage="failed",
                    stage_message=str(e),
                )

    bg.add_task(
        lambda: threading.Thread(
            target=task,
            daemon=True,
            name=f"render-draft-{draft_id}",
        ).start()
    )
    return {"job_id": job_id, "status": "generating", "draft_id": draft_id}


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
