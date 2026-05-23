from __future__ import annotations

import concurrent.futures
import json
import shutil
import time
from pathlib import Path

from pipeline import db
from pipeline.config import get_settings, load_niche
from pipeline.job_control import JobCancelledError, cancel_job, clear_cancel, current_job_id, is_cancelled
from pipeline.metadata import generate_metadata
from pipeline.models import VideoScript
from pipeline.publish.youtube import upload_video
from pipeline.render.fitness_tv import render_fitness_tv
from pipeline.script import generate_script
from pipeline.video_providers.assign import assign_providers


def _generate_script_with_heartbeat(
    job_id: str,
    *,
    topic: str,
    duration_minutes: int,
    audio_mode: str,
    niche_name: str,
) -> VideoScript:
    """Run script generation with periodic DB heartbeats so the UI shows live progress."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            generate_script,
            topic,
            duration_minutes,
            audio_mode,
            niche_name,
        )
        start = time.monotonic()
        while True:
            try:
                return future.result(timeout=5)
            except concurrent.futures.TimeoutError:
                if is_cancelled(job_id):
                    raise JobCancelledError()
                elapsed = int(time.monotonic() - start)
                db.update_job(
                    job_id,
                    stage_message=f"Generating script… ({elapsed}s)",
                )


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
    video_mode: str = "stock",
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

    token = current_job_id.set(job_id)
    try:
        _execute_generate_inner(
            job_id,
            topic=topic,
            duration_minutes=duration_minutes,
            audio_mode=audio_mode,
            niche=niche,
            video_mode=video_mode,
            work_dir=work_dir,
            settings=settings,
        )
    except JobCancelledError:
        if db.get_job(job_id):
            db.update_job(
                job_id,
                status="failed",
                error="Cancelled by user",
                stage="cancelled",
                stage_message="Cancelled",
            )
    finally:
        current_job_id.reset(token)
        clear_cancel(job_id)


def _execute_generate_inner(
    job_id: str,
    topic: str,
    duration_minutes: int,
    audio_mode: str,
    niche: str,
    video_mode: str,
    work_dir: Path,
    settings: dict,
) -> None:
    if is_cancelled(job_id):
        raise JobCancelledError()

    try:
        script = _generate_script_with_heartbeat(
            job_id,
            topic=topic,
            duration_minutes=duration_minutes,
            audio_mode=audio_mode,
            niche_name=niche,
        )
        script, provider_warning = assign_providers(script, video_mode)
        if is_cancelled(job_id):
            raise JobCancelledError()
        stage_message = "Rendering video segments…"
        if provider_warning:
            stage_message = provider_warning
        elif video_mode == "premium":
            stage_message = "Rendering with Veo 3 (Pexels fallback per scene)…"
        db.update_job(
            job_id,
            script_json=script.model_dump_json(),
            stage="render",
            stage_message=stage_message,
            progress_pct=20,
        )

        def on_stage(stage: str, message: str, pct: int) -> None:
            if is_cancelled(job_id):
                cancel_job(job_id)
                raise JobCancelledError()
            db.update_job_stage(job_id, stage, message, pct)

        final = render_fitness_tv(script, work_dir, on_stage=on_stage)

        if is_cancelled(job_id):
            raise JobCancelledError()

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
    except JobCancelledError:
        raise
    except Exception as e:
        if db.get_job(job_id):
            db.update_job(
                job_id,
                status="failed",
                error=str(e),
                stage="failed",
                stage_message=str(e),
            )
        raise


def _unlink(path: Path) -> None:
    if path.exists():
        path.unlink()


def _copy_then_remove(src: Path, dest: Path) -> None:
    """Copy a file then remove the source (Windows-safe when file is briefly locked)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    for _ in range(8):
        try:
            _unlink(src)
            return
        except PermissionError:
            time.sleep(0.25)


def _move_file(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        _unlink(dest)
    try:
        shutil.move(str(src), str(dest))
    except PermissionError:
        _copy_then_remove(src, dest)


def approve_job(job_id: str) -> None:
    job = db.get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    if job["status"] not in ("pending_review", "rendered"):
        raise ValueError(f"Job {job_id} is not pending review (status={job['status']})")

    settings = get_settings()
    src = Path(job["video_path"])
    dest = settings["output_approved"] / src.name
    if src.exists():
        _move_file(src, dest)
    elif not dest.exists():
        raise ValueError(f"Video file missing: {src}")
    sidecar_src = src.with_suffix(".json")
    if sidecar_src.exists():
        _move_file(sidecar_src, dest.with_suffix(".json"))

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
        _move_file(src, dest)
        sidecar_src = src.with_suffix(".json")
        if sidecar_src.exists():
            _move_file(sidecar_src, dest.with_suffix(".json"))
    db.update_job(job_id, status="rejected")


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
        cancel_job(job_id)
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


def generate_script_draft(
    topic: str,
    duration_minutes: int = 12,
    audio_mode: str = "coach_voice",
    niche: str = "fitness_warmup",
    video_mode: str = "stock",
    idea_id: str | None = None,
    label: str = "",
    extra_context: str = "",
) -> str:
    """Generate script only and store as draft. Returns draft_id."""
    db.init_db()
    script = generate_script(
        topic=topic,
        duration_minutes=duration_minutes,
        audio_mode=audio_mode,
        niche_name=niche,
        extra_context=extra_context,
    )
    script, _ = assign_providers(script, video_mode)
    draft_id = db.create_script_draft(
        topic=topic,
        script_json=script.model_dump_json(),
        idea_id=idea_id,
        label=label,
        duration_min=duration_minutes,
        audio_mode=audio_mode,
        video_mode=video_mode,
    )
    if idea_id:
        db.update_idea(idea_id, status="drafting")
    return draft_id


def execute_render_from_draft(draft_id: str, job_id: str | None = None) -> str:
    """Render video from saved script draft. Returns job_id."""
    db.init_db()
    draft = db.get_script_draft(draft_id)
    if not draft or not draft.get("script_json"):
        raise ValueError(f"Draft not found or empty: {draft_id}")

    script = VideoScript.model_validate_json(draft["script_json"])
    settings = get_settings()
    if not job_id:
        job_id = db.create_job(
            topic=draft["topic"],
            niche="fitness_warmup",
            audio_mode=draft.get("audio_mode") or script.audio_mode,
        )
    work_dir = settings["root"] / "assets" / "output" / ".work" / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    db.update_job(
        job_id,
        status="generating",
        work_dir=str(work_dir),
        script_json=draft["script_json"],
        stage="render",
        stage_message="Rendering from script draft…",
        progress_pct=20,
    )

    token = current_job_id.set(job_id)
    try:
        def on_stage(stage: str, message: str, pct: int) -> None:
            if is_cancelled(job_id):
                cancel_job(job_id)
                raise JobCancelledError()
            db.update_job_stage(job_id, stage, message, pct)

        final = render_fitness_tv(script, work_dir, on_stage=on_stage)
        pending_name = f"{job_id}_{_slug(draft['topic'])}.mp4"
        pending_path = settings["output_pending"] / pending_name
        shutil.copy2(final, pending_path)
        sidecar = pending_path.with_suffix(".json")
        sidecar.write_text(
            json.dumps(
                {
                    "job_id": job_id,
                    "topic": draft["topic"],
                    "title_draft": script.title_draft,
                    "audio_mode": draft.get("audio_mode"),
                    "draft_id": draft_id,
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
        if draft.get("idea_id"):
            db.update_idea(draft["idea_id"], status="used")
    except JobCancelledError:
        if db.get_job(job_id):
            db.update_job(
                job_id,
                status="failed",
                error="Cancelled by user",
                stage="cancelled",
                stage_message="Cancelled",
            )
        raise
    except Exception as e:
        if db.get_job(job_id):
            db.update_job(
                job_id,
                status="failed",
                error=str(e),
                stage="failed",
                stage_message=str(e),
            )
        raise
    finally:
        current_job_id.reset(token)
        clear_cancel(job_id)

    return job_id
