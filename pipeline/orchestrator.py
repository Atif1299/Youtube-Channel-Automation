from __future__ import annotations

import json
import shutil
from pathlib import Path

from pipeline import db
from pipeline.config import get_settings, load_niche
from pipeline.metadata import generate_metadata
from pipeline.models import VideoScript
from pipeline.publish.youtube import upload_video
from pipeline.render.fitness_tv import render_fitness_tv
from pipeline.script import generate_script


def run_generate(
    topic: str,
    duration_minutes: int = 12,
    audio_mode: str | None = None,
    niche: str = "fitness_warmup",
) -> str:
    db.init_db()
    niche_cfg = load_niche(niche)
    mode = audio_mode or niche_cfg.get("audio_mode", "music_only")

    job_id = db.create_job(topic=topic, niche=niche, audio_mode=mode)
    settings = get_settings()
    work_dir = settings["root"] / "assets" / "output" / ".work" / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    script = generate_script(
        topic=topic,
        duration_minutes=duration_minutes,
        audio_mode=mode,
        niche_name=niche,
    )
    used_ai = any(s.provider in ("veo", "hailuo", "kling") for s in script.scenes)

    db.update_job(
        job_id,
        script_json=script.model_dump_json(),
        work_dir=str(work_dir),
    )

    final = render_fitness_tv(script, work_dir)
    pending_name = f"{job_id}_{_slug(topic)}.mp4"
    pending_path = settings["output_pending"] / pending_name
    shutil.copy2(final, pending_path)

    sidecar = pending_path.with_suffix(".json")
    sidecar.write_text(
        json.dumps(
            {
                "job_id": job_id,
                "topic": topic,
                "title_draft": script.title_draft,
                "audio_mode": mode,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    db.update_job(
        job_id,
        status="pending_review",
        video_path=str(pending_path),
    )
    return job_id


def approve_job(job_id: str) -> None:
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    if job["status"] not in ("pending_review", "rendered"):
        raise ValueError(f"Job {job_id} is not pending review (status={job['status']})")

    settings = get_settings()
    src = Path(job["video_path"])
    dest = settings["output_approved"] / src.name
    shutil.move(str(src), str(dest))
    sidecar_src = src.with_suffix(".json")
    if sidecar_src.exists():
        shutil.move(str(sidecar_src), str(dest.with_suffix(".json")))

    script = VideoScript.model_validate_json(job["script_json"])
    used_ai = any(s.provider in ("veo", "hailuo", "kling") for s in script.scenes)
    metadata = generate_metadata(script, used_ai_clips=used_ai)
    meta_path = dest.with_suffix(".metadata.json")
    meta_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")

    db.update_job(
        job_id,
        status="approved",
        video_path=str(dest),
        metadata_json=metadata.model_dump_json(),
    )


def reject_job(job_id: str) -> None:
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    settings = get_settings()
    src = Path(job["video_path"])
    if src.exists():
        dest = settings["output_rejected"] / src.name
        shutil.move(str(src), str(dest))
    db.update_job(job_id, status="rejected")


def publish_job(job_id: str, publish_at: str | None = None) -> str:
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    if job["status"] != "approved":
        raise ValueError("Job must be approved before publish")

    from pipeline.models import VideoMetadata

    metadata = VideoMetadata.model_validate_json(job["metadata_json"])
    db.update_job(job_id, status="uploading")
    try:
        video_id = upload_video(
            Path(job["video_path"]),
            metadata,
            privacy="private" if publish_at else "public",
            publish_at=publish_at,
        )
        status = "scheduled" if publish_at else "published"
        db.update_job(
            job_id,
            status=status,
            youtube_video_id=video_id,
            publish_at=publish_at,
        )
        return video_id
    except Exception as e:
        db.update_job(job_id, status="failed", error=str(e))
        raise


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text)[:40].strip("_")
