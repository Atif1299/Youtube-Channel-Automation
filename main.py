#!/usr/bin/env python3
"""CLI for YouTube fitness warm-up automation pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from pipeline import db
from pipeline.config import get_settings
from pipeline.db import init_db
from pipeline.orchestrator import approve_job, publish_job, reject_job, run_generate
from pipeline.publish.auth_youtube import run_oauth_flow
from pipeline.research.competitor import refresh_competitor_cache


@click.group()
def cli() -> None:
    """YouTube Automations — fitness warm-up pipeline."""
    init_db()


@cli.command("research")
def research() -> None:
    """Refresh competitor channel cache (YouTube Data API)."""
    path = refresh_competitor_cache()
    click.echo(f"Competitor cache updated: {path}")


@cli.command("quick-test")
@click.option("--topic", default="1 min desk stretch quick test", help="Video topic")
@click.option(
    "--audio",
    "audio_mode",
    type=click.Choice(["music_only", "coach_voice"]),
    default="coach_voice",
    help="Default coach_voice so you hear narration",
)
def quick_test(topic: str, audio_mode: str) -> None:
    """1-minute test video (fastest pipeline check)."""
    click.echo(f"Quick test: {topic} (1 min, {audio_mode})...")
    job_id = run_generate(
        topic=topic,
        duration_minutes=1,
        audio_mode=audio_mode,
    )
    job = db.get_job(job_id)
    click.echo(f"Job {job_id} ready for review.")
    click.echo(f"Video: {job['video_path']}")


@cli.command("generate")
@click.option("--topic", required=True, help="Video topic e.g. 'Morning desk stretch warm up'")
@click.option("--duration", default=12, type=int, help="Target duration in minutes (use 1 for quick test)")
@click.option(
    "--audio",
    "audio_mode",
    type=click.Choice(["music_only", "coach_voice"]),
    default=None,
    help="Override niche audio_mode",
)
@click.option("--niche", default="fitness_warmup", help="Niche config name")
def generate(topic: str, duration: int, audio_mode: str | None, niche: str) -> None:
    """Generate video → pending_review folder."""
    click.echo(f"Generating: {topic} ({duration} min)...")
    job_id = run_generate(
        topic=topic,
        duration_minutes=duration,
        audio_mode=audio_mode,
        niche=niche,
    )
    job = db.get_job(job_id)
    click.echo(f"Job {job_id} ready for review.")
    click.echo(f"Video: {job['video_path']}")
    click.echo("Commands:")
    click.echo(f"  python main.py approve {job_id}")
    click.echo(f"  python main.py reject {job_id}")


@cli.command("list")
@click.option("--status", default=None, help="Filter by status")
def list_jobs(status: str | None) -> None:
    """List pipeline jobs."""
    jobs = db.list_jobs(status=status)
    if not jobs:
        click.echo("No jobs found.")
        return
    for j in jobs:
        click.echo(
            f"{j['id']}  {j['status']:16}  {j.get('topic', '')[:50]}  "
            f"{j.get('video_path') or ''}"
        )


@cli.command("show")
@click.argument("job_id")
def show(job_id: str) -> None:
    """Show job details."""
    job = db.get_job(job_id)
    if not job:
        raise click.ClickException(f"Job not found: {job_id}")
    click.echo(json.dumps(dict(job), indent=2, default=str))


@cli.command("approve")
@click.argument("job_id")
def approve(job_id: str) -> None:
    """Approve video → generates metadata → moves to approved/."""
    approve_job(job_id)
    job = db.get_job(job_id)
    click.echo(f"Approved {job_id}")
    click.echo(f"Video: {job['video_path']}")
    click.echo(f"Publish: python main.py publish {job_id}")
    click.echo(f"Schedule: python main.py publish {job_id} --at 2026-06-01T18:00:00+05:00")


@cli.command("reject")
@click.argument("job_id")
def reject(job_id: str) -> None:
    """Reject video → moves to rejected/."""
    reject_job(job_id)
    click.echo(f"Rejected {job_id}")


@cli.command("publish")
@click.argument("job_id")
@click.option(
    "--at",
    "publish_at",
    default=None,
    help="ISO 8601 schedule time (video stays private until then)",
)
def publish(job_id: str, publish_at: str | None) -> None:
    """Upload approved video to YouTube."""
    video_id = publish_job(job_id, publish_at=publish_at)
    click.echo(f"Uploaded. YouTube video ID: {video_id}")


@cli.command("auth-youtube")
def auth_youtube() -> None:
    """Run OAuth flow and save refresh token to .env."""
    token = run_oauth_flow()
    click.echo("YouTube OAuth complete. Refresh token saved to .env and token.json")


@cli.command("ui")
def ui() -> None:
    """Start local web UI (http://127.0.0.1:8765)."""
    import uvicorn

    click.echo("UI: http://127.0.0.1:8765")
    uvicorn.run("ui.server:app", host="127.0.0.1", port=8765, reload=False)


@cli.command("check")
def check() -> None:
    """Verify environment and dependencies."""
    settings = get_settings()
    checks = [
        ("OPENAI_API_KEY", bool(settings["openai_api_key"])),
        ("PEXELS_API_KEY", bool(settings["pexels_api_key"])),
        ("LOCAL_CLIPS_DIR", settings["local_clips_dir"].exists()),
        ("MUSIC_LIBRARY_DIR", settings["music_library_dir"].exists()),
    ]
    for name, ok in checks:
        click.echo(f"{'OK' if ok else 'MISSING':7} {name}")
    try:
        from pipeline.render.ffmpeg_util import require_ffmpeg

        ff = require_ffmpeg()
        click.echo(f"OK      ffmpeg ({ff})")
    except Exception as e:
        click.echo(f"MISSING ffmpeg — {e}")
    music = list(settings["music_library_dir"].glob("*.mp3"))
    click.echo(f"        music tracks: {len(music)}")


if __name__ == "__main__":
    cli()
