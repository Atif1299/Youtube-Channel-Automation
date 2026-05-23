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
    """Create a job and run the full generate pipeline synchronously."""
    db.init_db()
    niche_cfg = load_niche(niche)
    mode = audio_mode or niche_cfg.get("audio_mode", "music_only")
    job_id = db.create_job(topic=topic, niche=niche, audio_mode=mode)
    execute_generate(
        job_id,
        topic=topic,
        duration_minutes=duration_minutes,
        audio_mode=mode,
        niche=niche,
    )
    return job_id


def execute_generate(
    job_id: str,
    topic: str,
    duration_minutes: int = 12,
    audio_mode: str = "music_only",
    niche: str = "fitness_warmup",
) -> None:
    """Run generate pipeline for an existing job (used by API background tasks)."""
    db.init_db()
    settings = get_settings()
    work_dir = settings["root"] / "assets" / "output" / ".work" / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    db.update_job(
        job_id,
        status="generating",
        work_dir=str(work_dir),
        error=None,
        stage="script",
        stage_message="Generating script…",
        progress_pct=5,
    )

    try:
        script = generate_script(
            topic=topic,
            duration_minutes=duration_minutes,
            audio_mode=audio_mode,
            niche_name=niche,
        )
        db.update_job(
            job_id,
            script_json=script.model_dump_json(),
            stage="render",
            stage_message="Rendering video segments…",
            progress_pct=20,
        )

        def on_stage(stage: str, message: str, pct: int) -> None:
            db.update_job_stage(job_id, stage, message, pct)

        final = render_fitness_tv(script, work_dir, on_stage=on_stage)

        db.update_job_stage(
            job_id,
            "finalize",
            "Copying to pending review…",
            95,
        )
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
                    "audio_mode": audio_mode,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        db.update_job(
            job_id,
            status="pending_review",
            video_path=str(pending_path),
            stage="done",
            stage_message="Ready for review",
            progress_pct=100,
        )
    except Exception as e:
        db.update_job(
            job_id,
            status="failed",
            error=str(e),
            stage="failed",
            stage_message=str(e),
        )
        raise


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
    src = Path(job["video_path"]) if job.get("video_path") else None
    if src and src.exists():
        dest = settings["output_rejected"] / src.name
        shutil.move(str(src), str(dest))
    db.update_job(job_id, status="rejected")


def _unlink(path: Path) -> None:
    if path.exists():
        path.unlink()


def _remove_job_artifacts(job: dict) -> None:
    settings = get_settings()
    job_id = job["id"]

    video_path = job.get("video_path")
    if video_path:
        vp = Path(video_path)
        _unlink(vp)
        _unlink(vp.with_suffix(".json"))
        _unlink(vp.with_suffix(".metadata.json"))

    work_dir = job.get("work_dir")
    if work_dir:
        wd = Path(work_dir)
        if wd.is_dir():
            shutil.rmtree(wd, ignore_errors=True)

    default_work = settings["root"] / "assets" / "output" / ".work" / job_id
    if default_work.is_dir():
        shutil.rmtree(default_work, ignore_errors=True)

    for folder in (
        settings["output_pending"],
        settings["output_approved"],
        settings["output_rejected"],
    ):
        if not folder.is_dir():
            continue
        for path in folder.glob(f"{job_id}_*"):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                shutil.rmtree(path, ignore_errors=True)


def delete_job(job_id: str) -> None:
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    if job["status"] in ("generating", "uploading"):
        raise ValueError("Cannot delete a job while it is running")
    _remove_job_artifacts(job)
    if not db.delete_job(job_id):
        raise ValueError(f"Job not found: {job_id}")


def publish_job(job_id: str, publish_at: str | None = None) -> str:
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    if job["status"] != "approved":
        raise ValueError("Job must be approved before publish")

    from pipeline.models import VideoMetadata

    metadata = VideoMetadata.model_validate_json(job["metadata_json"])
    db.update_job(job_id, status="uploading", stage="publish", stage_message="Uploading to YouTube…")
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
            stage="done",
            stage_message="Published",
            progress_pct=100,
        )
        return video_id
    except Exception as e:
        db.update_job(job_id, status="failed", error=str(e), stage="failed", stage_message=str(e))
        raise


def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text)[:40].strip("_")
