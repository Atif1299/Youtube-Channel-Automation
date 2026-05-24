"""
YT Video Studio - Consolidated Pipeline Engine
Single-file FastAPI backend for video generation, research, and publishing.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import os
import random
import shutil
import sqlite3
import subprocess
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import uuid4

import httpx
import yaml
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from openai import OpenAI
from pydantic import BaseModel, Field

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR
load_dotenv(APP_DIR / ".env")

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="YT Video Studio API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =============================================================================
# CONFIG
# =============================================================================

def _path_from_env(key: str, default: str) -> Path:
    raw = os.getenv(key, default)
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


@lru_cache
def get_settings() -> dict:
    return {
        "root": ROOT,
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
        "pexels_api_key": os.getenv("PEXELS_API_KEY", ""),
        "youtube_api_key": os.getenv("YOUTUBE_API_KEY", ""),
        "youtube_client_id": os.getenv("YOUTUBE_CLIENT_ID", ""),
        "youtube_client_secret": os.getenv("YOUTUBE_CLIENT_SECRET", ""),
        "youtube_refresh_token": os.getenv("YOUTUBE_REFRESH_TOKEN", ""),
        "veo_model": os.getenv("VEO_MODEL", "veo-3.0-generate-001"),
        "local_clips_dir": _path_from_env("LOCAL_CLIPS_DIR", "assets/clips"),
        "music_library_dir": _path_from_env("MUSIC_LIBRARY_DIR", "assets/music"),
        "output_pending": ROOT / "assets/output/pending",
        "output_approved": ROOT / "assets/output/approved",
        "output_rejected": ROOT / "assets/output/rejected",
        "jobs_db": ROOT / "data/jobs.db",
    }


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_brand() -> dict:
    return load_yaml(ROOT / "config/brand.yaml")


def load_niche(name: str = "fitness_warmup") -> dict:
    return load_yaml(ROOT / "config/niches" / f"{name}.yaml")


def load_prompt(rel_path: str) -> str:
    path = ROOT / "prompts" / rel_path
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


# =============================================================================
# MODELS
# =============================================================================

class VisualBible(BaseModel):
    setting: str = ""
    subject: str = ""
    wardrobe: str = ""
    camera_style: str = ""
    lighting: str = ""
    color_palette: str = ""


class Scene(BaseModel):
    id: int
    exercise: str
    duration_sec: int = Field(ge=5, le=180)
    on_screen_text: str
    voiceover: str = ""
    visual_prompt: str = ""
    continuity_note: str = ""
    negative_prompt: str = "warped limbs, blurry, watermark"
    provider: Literal["stock", "veo"] = "stock"
    stock_query: str = ""


class VideoScript(BaseModel):
    title_draft: str
    topic: str
    total_duration_sec: int
    audio_mode: Literal["music_only", "coach_voice"] = "music_only"
    visual_bible: VisualBible = Field(default_factory=VisualBible)
    scenes: list[Scene]


class VideoMetadata(BaseModel):
    title: str
    description: str
    tags: list[str]
    category_id: str = "17"
    contains_synthetic_media: bool = False
    chapters: list[dict] = Field(default_factory=list)


# =============================================================================
# DATABASE
# =============================================================================

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    settings = get_settings()
    settings["jobs_db"].parent.mkdir(parents=True, exist_ok=True)
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                topic TEXT,
                niche TEXT,
                audio_mode TEXT,
                video_mode TEXT,
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
        """)


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


def create_job(topic: str, niche: str = "fitness_warmup", audio_mode: str = "music_only", video_mode: str = "stock") -> str:
    job_id = uuid4().hex[:12]
    with _connect() as conn:
        conn.execute(
            "INSERT INTO jobs (id, status, topic, niche, audio_mode, video_mode, created_at, updated_at) VALUES (?, 'draft', ?, ?, ?, ?, ?, ?)",
            (job_id, topic, niche, audio_mode, video_mode, _now(), _now()),
        )
    return job_id


def update_job(job_id: str, **fields: Any) -> None:
    allowed = {"status", "script_json", "metadata_json", "video_path", "work_dir", "youtube_video_id", "publish_at", "error", "stage", "stage_message", "progress_pct"}
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
            rows = conn.execute("SELECT * FROM jobs WHERE status = ? ORDER BY created_at DESC", (status,)).fetchall()
        else:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_job(job_id: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
    return cur.rowcount > 0


# =============================================================================
# LLM
# =============================================================================

def get_openai_client() -> OpenAI:
    settings = get_settings()
    if not settings["openai_api_key"]:
        raise ValueError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=settings["openai_api_key"], timeout=120.0)


def llm_complete_json(system: str, user: str) -> dict:
    client = get_openai_client()
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
    )
    content = response.choices[0].message.content or "{}"
    return json.loads(content)


def generate_script(topic: str, duration_minutes: int = 12, audio_mode: str = "music_only", niche_name: str = "fitness_warmup") -> VideoScript:
    niche = load_niche(niche_name)
    brand = load_brand()
    system = load_prompt(f"niches/{niche_name}/script_system.md") or "You are a video script writer. Return JSON only."
    
    user = f"""
Topic: {topic}
Target duration: {duration_minutes} minutes
Audio mode: {audio_mode}
Niche audience: {niche.get('audience', '')}
Tone: {niche.get('tone', '')}
Brand channel: {brand.get('channel_name', '')}

Return JSON with this structure:
{{
  "title_draft": "string",
  "topic": "string",
  "total_duration_sec": number,
  "audio_mode": "{audio_mode}",
  "visual_bible": {{
    "setting": "string",
    "subject": "string",
    "wardrobe": "string",
    "camera_style": "string",
    "lighting": "string",
    "color_palette": "string"
  }},
  "scenes": [
    {{
      "id": 1,
      "exercise": "string",
      "duration_sec": number,
      "on_screen_text": "string",
      "voiceover": "string",
      "visual_prompt": "string",
      "stock_query": "string (3-6 words for Pexels)"
    }}
  ]
}}
Use 6-12 scenes for a {duration_minutes} minute video. First scene: intro. Last scene: closing.
Sum of all duration_sec MUST equal total_duration_sec exactly.
"""
    raw = llm_complete_json(system, user)
    raw["topic"] = topic
    raw["audio_mode"] = audio_mode
    return VideoScript.model_validate(raw)


def generate_metadata(script: VideoScript, used_ai_clips: bool = False) -> VideoMetadata:
    niche = load_niche()
    brand = load_brand()
    system = "You write YouTube SEO metadata. Return JSON with keys: title, description, tags (array), chapters (array of {time, title})."
    user = f"""
Video title draft: {script.title_draft}
Topic: {script.topic}
Duration seconds: {script.total_duration_sec}
Keywords: {', '.join(niche.get('keywords_seed', []))}
Channel: {brand.get('channel_name', '')}
Disclaimer: {brand.get('disclaimer', '')}
CTA: {niche.get('cta', '')}

Exercises: {json.dumps([s.exercise for s in script.scenes])}

Generate chapters with MM:SS timestamps starting at 0:00 for intro.
"""
    raw = llm_complete_json(system, user)
    return VideoMetadata(
        title=raw.get("title", script.title_draft),
        description=raw.get("description", ""),
        tags=raw.get("tags", [])[:15],
        contains_synthetic_media=used_ai_clips,
        chapters=raw.get("chapters", []),
    )


# =============================================================================
# ASSETS - PEXELS
# =============================================================================

PEXELS_VIDEO_SEARCH = "https://api.pexels.com/videos/search"


def _local_clip_for_query(query: str) -> Path | None:
    clips_dir = get_settings()["local_clips_dir"]
    if not clips_dir.exists():
        return None
    candidates = list(clips_dir.glob("*.mp4")) + list(clips_dir.glob("*.mov"))
    if not candidates:
        return None
    query_tokens = set(query.lower().replace("-", " ").split())
    scored = []
    for path in candidates:
        name_tokens = set(path.stem.lower().replace("-", " ").replace("_", " ").split())
        score = len(query_tokens & name_tokens)
        scored.append((score, path))
    scored.sort(key=lambda x: (-x[0], x[1].name))
    return scored[0][1] if scored[0][0] > 0 else random.choice(candidates)


def fetch_pexels_clip(query: str, min_duration: int = 5) -> Path | None:
    settings = get_settings()
    api_key = settings["pexels_api_key"]
    if not api_key:
        return _local_clip_for_query(query)
    
    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": 8, "orientation": "landscape"}
    try:
        with httpx.Client(timeout=60) as client:
            resp = client.get(PEXELS_VIDEO_SEARCH, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError:
        return _local_clip_for_query(query)
    
    videos = data.get("videos", [])
    if not videos:
        return _local_clip_for_query(query)
    
    random.shuffle(videos)
    for video in videos:
        files = sorted(video.get("video_files", []), key=lambda f: f.get("width", 0), reverse=True)
        for vf in files:
            if vf.get("width", 0) < 1280:
                continue
            link = vf.get("link")
            if not link:
                continue
            duration = video.get("duration", 0)
            if duration and duration < min_duration:
                continue
            return _download_video(link, query)
    return _local_clip_for_query(query)


def _download_video(url: str, query: str) -> Path | None:
    settings = get_settings()
    dest_dir = settings["root"] / "assets" / "output" / ".cache" / "pexels"
    dest_dir.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in query)[:40]
    dest = dest_dir / f"{safe}_{random.randint(1000, 9999)}.mp4"
    try:
        with httpx.Client(timeout=120, follow_redirects=True) as client:
            with client.stream("GET", url) as resp:
                resp.raise_for_status()
                with open(dest, "wb") as f:
                    for chunk in resp.iter_bytes():
                        f.write(chunk)
        return dest
    except httpx.HTTPError:
        return None


# =============================================================================
# ASSETS - VEO
# =============================================================================

def fetch_veo_clip(scene: Scene, work_dir: Path, topic: str, visual_bible: VisualBible | None = None) -> Path | None:
    settings = get_settings()
    api_key = settings.get("gemini_api_key")
    if not api_key:
        log.warning("Veo skipped: GEMINI_API_KEY not set")
        return fetch_pexels_clip(scene.stock_query or scene.exercise)
    
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        log.warning("Veo skipped: google-genai not installed")
        return fetch_pexels_clip(scene.stock_query or scene.exercise)
    
    model = settings.get("veo_model", "veo-3.0-generate-001")
    style = load_prompt("fitness_warmup/visual_veo.md") or ""
    
    bible_text = ""
    if visual_bible:
        parts = []
        for key in ("setting", "subject", "wardrobe", "camera_style", "lighting", "color_palette"):
            val = getattr(visual_bible, key, "")
            if val:
                parts.append(f"{key.replace('_', ' ').title()}: {val}")
        if parts:
            bible_text = "VISUAL BIBLE:\n" + "\n".join(parts) + "\n\n"
    
    scene_desc = scene.visual_prompt or scene.exercise
    prompt = f"{style}\n\n{bible_text}TOPIC: {topic}\nTHIS SCENE ({scene.duration_sec}s): {scene.on_screen_text}\nFocus: {scene_desc}"
    
    out = work_dir / f"veo_scene_{scene.id}.mp4"
    if out.exists():
        return out
    
    client = genai.Client(api_key=api_key)
    try:
        config = types.GenerateVideosConfig(negative_prompt=scene.negative_prompt)
        log.info("Veo scene %s: starting %s", scene.id, model)
        operation = client.models.generate_videos(model=model, prompt=prompt, config=config)
        while not operation.done:
            time.sleep(10)
            operation = client.operations.get(operation)
        if not operation.response or not operation.response.generated_videos:
            raise RuntimeError("Veo returned no videos")
        generated = operation.response.generated_videos[0]
        client.files.download(file=generated.video)
        generated.video.save(str(out))
        log.info("Veo scene %s: saved %s", scene.id, out.name)
        return out
    except Exception as e:
        log.warning("Veo failed scene %s (%s), using Pexels fallback", scene.id, e)
        return fetch_pexels_clip(scene.stock_query or scene.exercise)


# =============================================================================
# ASSETS - TTS
# =============================================================================

def synthesize_voice(text: str, output_path: Path, voice: str = "alloy") -> Path:
    settings = get_settings()
    if not settings["openai_api_key"]:
        raise ValueError("OPENAI_API_KEY required for TTS")
    client = OpenAI(api_key=settings["openai_api_key"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with client.audio.speech.with_streaming_response.create(
        model="tts-1",
        voice=voice,
        input=text,
    ) as response:
        response.stream_to_file(output_path)
    return output_path


# =============================================================================
# FFMPEG UTILITIES
# =============================================================================

def require_ffmpeg() -> None:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise RuntimeError("ffmpeg not found. Install ffmpeg and add to PATH.") from e


def run_ffmpeg(args: list[str]) -> None:
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"] + args
    subprocess.run(cmd, check=True)


def probe_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True,
            text=True,
            check=True,
        )
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        return None


# =============================================================================
# RENDER PIPELINE
# =============================================================================

def _escape_drawtext(text: str) -> str:
    return text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'").replace("%", "\\%")


def _truncate_label(text: str, max_len: int = 48) -> str:
    text = text.strip()
    return text if len(text) <= max_len else text[:max_len - 1].rstrip() + "…"


def _prepare_scene_segment(scene: Scene, source: Path, out_path: Path, width: int, height: int, primary_color: str, font_size: int, text_color: str, fps: int, loop: bool = True) -> None:
    label = _escape_drawtext(_truncate_label(scene.on_screen_text))
    safe_bottom = 140
    vf = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},drawtext=text='{label}':fontsize={font_size}:fontcolor={text_color}:box=1:boxcolor={primary_color}@0.85:boxborderw=12:x=(w-text_w)/2:y=h-{safe_bottom}"
    cmd = []
    if loop:
        cmd.extend(["-stream_loop", "-1"])
    cmd.extend(["-i", str(source), "-t", str(scene.duration_sec), "-vf", vf, "-an", "-r", str(fps), "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", str(out_path)])
    run_ffmpeg(cmd)


def _concat_segments(segment_paths: list[Path], out_path: Path, fps: int) -> None:
    if not segment_paths:
        raise ValueError("No segments to concat")
    list_file = out_path.parent / "concat_list.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in segment_paths]
    list_file.write_text("\n".join(lines), encoding="utf-8")
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(list_file), "-r", str(fps), "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart", str(out_path)])


def _pick_music() -> Path | None:
    music_dir = get_settings()["music_library_dir"]
    tracks = list(music_dir.glob("*.mp3")) + list(music_dir.glob("*.wav"))
    return random.choice(tracks) if tracks else None


def _fit_voice_clip(src: Path, dest: Path, duration_sec: float) -> None:
    dur = max(0.1, float(duration_sec))
    run_ffmpeg(["-i", str(src), "-af", f"atrim=duration={dur},apad=whole_dur={dur}", "-t", str(dur), "-c:a", "libmp3lame", "-q:a", "4", str(dest)])


def _silence_clip(dest: Path, duration_sec: float) -> None:
    dur = max(0.1, float(duration_sec))
    run_ffmpeg(["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(dur), "-c:a", "libmp3lame", "-q:a", "4", str(dest)])


def _mix_audio(video_path: Path, output_path: Path, voice_path: Path | None, music_path: Path | None) -> None:
    if not voice_path and not music_path:
        run_ffmpeg(["-i", str(video_path), "-c", "copy", "-movflags", "+faststart", str(output_path)])
        return
    
    inputs = ["-i", str(video_path)]
    filter_parts = []
    
    if voice_path:
        inputs.extend(["-i", str(voice_path)])
    if music_path:
        inputs.extend(["-i", str(music_path)])
    
    if voice_path and music_path:
        filter_parts.append("[1:a]aformat=sample_rates=44100:channel_layouts=mono[v]")
        filter_parts.append("[2:a]aformat=sample_rates=44100:channel_layouts=stereo,aloop=loop=-1:size=2e+09,volume=0.18[m]")
        filter_parts.append("[v][m]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        maps = ["-map", "0:v", "-map", "[aout]"]
    elif voice_path:
        filter_parts.append("[1:a]aformat=sample_rates=44100:channel_layouts=mono[aout]")
        maps = ["-map", "0:v", "-map", "[aout]"]
    elif music_path:
        filter_parts.append("[1:a]aformat=sample_rates=44100:channel_layouts=stereo,aloop=loop=-1:size=2e+09,volume=0.25[aout]")
        maps = ["-map", "0:v", "-map", "[aout]"]
    
    cmd = inputs.copy()
    if filter_parts:
        cmd.extend(["-filter_complex", ";".join(filter_parts)])
    cmd.extend(maps)
    cmd.extend(["-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(output_path)])
    run_ffmpeg(cmd)


def _build_voiceover(script: VideoScript, work_dir: Path, on_stage: Callable | None = None) -> Path | None:
    if script.audio_mode != "coach_voice":
        return None
    parts = []
    for i, scene in enumerate(script.scenes):
        if on_stage:
            pct = 55 + int(20 * (i + 1) / max(len(script.scenes), 1))
            on_stage("tts", f"Voiceover scene {i + 1}/{len(script.scenes)}…", pct)
        synced = work_dir / f"voice_synced_{scene.id:02d}.mp3"
        if scene.voiceover.strip():
            raw = work_dir / f"voice_{scene.id}.mp3"
            synthesize_voice(scene.voiceover, raw)
            _fit_voice_clip(raw, synced, scene.duration_sec)
        else:
            _silence_clip(synced, scene.duration_sec)
        parts.append(synced)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    list_file = work_dir / "voice_concat.txt"
    list_file.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in parts), encoding="utf-8")
    combined = work_dir / "voiceover.mp3"
    run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(combined)])
    return combined


def render_video(script: VideoScript, work_dir: Path, on_stage: Callable | None = None) -> Path:
    require_ffmpeg()
    niche = load_niche()
    brand = load_brand()
    res = niche.get("resolution", "1920x1080")
    width, height = (int(x) for x in res.split("x"))
    primary = brand.get("primary_color", "#7B2CBF")
    font_size = int(brand.get("font_size", 48))
    text_color = brand.get("text_color", "#FFFFFF")
    fps = int(niche.get("fps", 30))
    
    work_dir.mkdir(parents=True, exist_ok=True)
    segments_dir = work_dir / "segments"
    segments_dir.mkdir(exist_ok=True)
    
    segment_paths = []
    for i, scene in enumerate(script.scenes):
        if on_stage:
            pct = 25 + int(30 * (i + 1) / max(len(script.scenes), 1))
            if scene.provider == "veo":
                on_stage("veo", f"Scene {i + 1}/{len(script.scenes)}: Veo 3 generating…", pct)
            else:
                on_stage("clips", f"Scene {i + 1}/{len(script.scenes)}: fetching stock clip…", pct)
        
        if scene.provider == "veo":
            clip = fetch_veo_clip(scene, work_dir, script.topic, script.visual_bible)
        else:
            clip = fetch_pexels_clip(scene.stock_query or scene.exercise)
        
        seg_out = segments_dir / f"scene_{scene.id:02d}.mp4"
        if clip and clip.exists():
            clip_dur = probe_duration(clip)
            use_loop = clip_dur is None or clip_dur < scene.duration_sec - 0.5
            _prepare_scene_segment(scene, clip, seg_out, width, height, primary, font_size, text_color, fps, loop=use_loop)
        else:
            run_ffmpeg(["-f", "lavfi", "-i", f"color=c=0x2d1b4e:s={width}x{height}:d={scene.duration_sec}", "-vf", f"drawtext=text='{_escape_drawtext(_truncate_label(scene.on_screen_text))}':fontsize={font_size}:fontcolor={text_color}:box=1:boxcolor={primary}@0.85:boxborderw=12:x=(w-text_w)/2:y=h-140", "-r", str(fps), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(seg_out)])
        segment_paths.append(seg_out)
    
    if on_stage:
        on_stage("render", "Concatenating segments…", 58)
    
    concat_out = work_dir / "video_no_audio.mp4"
    _concat_segments(segment_paths, concat_out, fps)
    
    voice = _build_voiceover(script, work_dir, on_stage=on_stage)
    music = _pick_music()
    
    if on_stage:
        on_stage("mix", "Mixing audio…", 80)
    
    final = work_dir / "final.mp4"
    _mix_audio(concat_out, final, voice, music)
    return final


# =============================================================================
# PROVIDER ASSIGNMENT
# =============================================================================

def assign_providers(script: VideoScript, video_mode: str) -> tuple[VideoScript, str | None]:
    settings = get_settings()
    niche = load_niche()
    has_gemini = bool(settings.get("gemini_api_key"))
    warning = None
    
    if video_mode == "premium" and not has_gemini:
        warning = "Premium unavailable — add GEMINI_API_KEY; using Pexels stock"
        video_mode = "stock"
    
    max_veo = int(niche.get("max_ai_clips_per_video", 5))
    use_veo = video_mode == "premium" and has_gemini
    
    veo_indices = set()
    if use_veo and len(script.scenes) > 0:
        veo_indices = {0, len(script.scenes) - 1}
        remaining = max_veo - len(veo_indices)
        middle = list(range(1, len(script.scenes) - 1))
        if middle and remaining > 0:
            step = max(1, len(middle) // remaining)
            for i in range(0, len(middle), step):
                if len(veo_indices) >= max_veo:
                    break
                veo_indices.add(middle[i])
    
    for i, scene in enumerate(script.scenes):
        scene.provider = "veo" if i in veo_indices else "stock"
    
    return script, warning


# =============================================================================
# RESEARCH - YOUTUBE TRENDING
# =============================================================================

PERIOD_DAYS = {"today": 1, "1d": 1, "7d": 7, "30d": 30, "90d": 90}


def youtube_get(endpoint: str, params: dict, api_key: str) -> dict:
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}"
    params["key"] = api_key
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()


def fetch_trending(period: str = "7d", source: str = "both", query: str | None = None, niche_name: str = "fitness_warmup") -> dict:
    settings = get_settings()
    api_key = settings["youtube_api_key"]
    if not api_key:
        return {"error": "YOUTUBE_API_KEY required", "combined": []}
    
    niche = load_niche(niche_name)
    days = PERIOD_DAYS.get(period, 7)
    since = datetime.now(timezone.utc) - timedelta(days=days)
    published_after = since.strftime("%Y-%m-%dT%H:%M:%SZ")
    
    q = query or " ".join(niche.get("keywords_seed", [])[:3])
    
    try:
        params = {
            "part": "snippet",
            "type": "video",
            "order": "viewCount",
            "publishedAfter": published_after,
            "q": q,
            "maxResults": 25,
            "videoDuration": "medium",
        }
        data = youtube_get("search", params, api_key)
        video_ids = [item["id"]["videoId"] for item in data.get("items", []) if item.get("id", {}).get("videoId")]
        
        if not video_ids:
            return {"combined": [], "period": period, "source": source}
        
        stats_data = youtube_get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(video_ids)}, api_key)
        
        results = []
        for item in stats_data.get("items", []):
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            results.append({
                "video_id": item["id"],
                "title": snippet.get("title", ""),
                "channel_handle": snippet.get("channelTitle", ""),
                "view_count": int(stats.get("viewCount", 0)),
                "source": "niche",
                "url": f"https://www.youtube.com/watch?v={item['id']}",
            })
        
        results.sort(key=lambda v: v["view_count"], reverse=True)
        return {"combined": results, "period": period, "source": source, "query": q}
    except Exception as e:
        return {"error": str(e), "combined": []}


# =============================================================================
# YOUTUBE UPLOAD
# =============================================================================

def upload_video(video_path: Path, metadata: VideoMetadata, privacy: str = "private", publish_at: str | None = None) -> str:
    settings = get_settings()
    refresh = settings["youtube_refresh_token"]
    client_id = settings["youtube_client_id"]
    client_secret = settings["youtube_client_secret"]
    
    if not all([refresh, client_id, client_secret]):
        raise ValueError("YouTube credentials missing. Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, and YOUTUBE_REFRESH_TOKEN in .env")
    
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    
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
    
    youtube = build("youtube", "v3", credentials=creds)
    
    body = {
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
    
    media = MediaFileUpload(str(video_path), chunksize=1024 * 1024, resumable=True, mimetype="video/mp4")
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    response = None
    while response is None:
        status, response = request.next_chunk()
    return response["id"]


# =============================================================================
# ORCHESTRATION
# =============================================================================

def _slug(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text)[:40].strip("_")


def execute_generate(job_id: str, topic: str, duration_minutes: int = 12, audio_mode: str = "music_only", niche: str = "fitness_warmup", video_mode: str = "stock") -> None:
    init_db()
    settings = get_settings()
    work_dir = settings["root"] / "assets" / "output" / ".work" / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    
    update_job(job_id, status="generating", work_dir=str(work_dir), error=None, stage="script", stage_message="Generating script…", progress_pct=5)
    
    try:
        script = generate_script(topic, duration_minutes, audio_mode, niche)
        script, warning = assign_providers(script, video_mode)
        
        stage_msg = warning or ("Rendering with Veo 3…" if video_mode == "premium" else "Rendering video segments…")
        update_job(job_id, script_json=script.model_dump_json(), stage="render", stage_message=stage_msg, progress_pct=20)
        
        def on_stage(stage: str, message: str, pct: int) -> None:
            update_job(job_id, stage=stage, stage_message=message, progress_pct=pct)
        
        final = render_video(script, work_dir, on_stage=on_stage)
        
        update_job(job_id, stage="finalize", stage_message="Copying to pending…", progress_pct=95)
        
        pending_name = f"{job_id}_{_slug(topic)}.mp4"
        pending_path = settings["output_pending"] / pending_name
        pending_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(final, pending_path)
        
        update_job(job_id, status="pending_review", video_path=str(pending_path), stage="done", stage_message="Ready for review", progress_pct=100)
    except Exception as e:
        log.exception("Generate failed for job %s", job_id)
        update_job(job_id, status="failed", error=str(e), stage="failed", stage_message=str(e))


def approve_job(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    if job["status"] != "pending_review":
        raise ValueError(f"Job {job_id} is not pending review")
    
    settings = get_settings()
    src = Path(job["video_path"])
    dest = settings["output_approved"] / src.name
    dest.parent.mkdir(parents=True, exist_ok=True)
    
    if src.exists():
        shutil.move(str(src), str(dest))
    
    script = VideoScript.model_validate_json(job["script_json"])
    used_ai = any(s.provider == "veo" for s in script.scenes)
    metadata = generate_metadata(script, used_ai_clips=used_ai)
    
    meta_path = dest.with_suffix(".metadata.json")
    meta_path.write_text(metadata.model_dump_json(indent=2), encoding="utf-8")
    
    update_job(job_id, status="approved", video_path=str(dest), metadata_json=metadata.model_dump_json())


def reject_job(job_id: str) -> None:
    job = get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    
    settings = get_settings()
    src = Path(job["video_path"]) if job.get("video_path") else None
    if src and src.exists():
        dest = settings["output_rejected"] / src.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
    
    update_job(job_id, status="rejected")


def publish_job(job_id: str, publish_at: str | None = None) -> str:
    job = get_job(job_id)
    if not job:
        raise ValueError(f"Job not found: {job_id}")
    if job["status"] != "approved":
        raise ValueError("Job must be approved before publish")
    
    metadata = VideoMetadata.model_validate_json(job["metadata_json"])
    update_job(job_id, status="uploading", stage="publish", stage_message="Uploading to YouTube…")
    
    try:
        video_id = upload_video(Path(job["video_path"]), metadata, privacy="private" if publish_at else "public", publish_at=publish_at)
        status = "scheduled" if publish_at else "published"
        update_job(job_id, status=status, youtube_video_id=video_id, publish_at=publish_at, stage="done", stage_message="Published", progress_pct=100)
        return video_id
    except Exception as e:
        update_job(job_id, status="failed", error=str(e), stage="failed", stage_message=str(e))
        raise


# =============================================================================
# API ROUTES
# =============================================================================

class GenerateRequest(BaseModel):
    topic: str
    duration: int = 12
    audio_mode: str = "coach_voice"
    niche: str = "fitness_warmup"
    video_mode: str = "stock"


class ScriptRequest(BaseModel):
    topic: str
    duration: int = 12
    audio_mode: str = "coach_voice"
    niche: str = "fitness_warmup"
    video_mode: str = "stock"


class PublishRequest(BaseModel):
    publish_at: str | None = None


@app.on_event("startup")
def startup() -> None:
    init_db()
    for d in (get_settings()["output_pending"], get_settings()["output_approved"], get_settings()["output_rejected"]):
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
    ready = bool(settings["openai_api_key"]) and bool(settings["pexels_api_key"]) and ffmpeg_ok
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


@app.get("/api/niches")
def api_niches() -> list[str]:
    niches_dir = ROOT / "config/niches"
    if not niches_dir.exists():
        return ["fitness_warmup"]
    return [p.stem for p in niches_dir.glob("*.yaml")]


@app.get("/api/research/trending")
def api_research_trending(period: str = "7d", source: str = "both", q: str | None = None) -> dict:
    return fetch_trending(period=period, source=source, query=q)


@app.post("/api/script/generate")
def api_generate_script(req: ScriptRequest) -> dict:
    try:
        script = generate_script(req.topic, req.duration, req.audio_mode, req.niche)
        script, warning = assign_providers(script, req.video_mode)
        return {"ok": True, "script": script.model_dump(), "warning": warning}
    except Exception as e:
        raise HTTPException(500, str(e)) from e


@app.post("/api/generate")
def api_generate(req: GenerateRequest, bg: BackgroundTasks) -> dict:
    init_db()
    job_id = create_job(topic=req.topic, niche=req.niche, audio_mode=req.audio_mode, video_mode=req.video_mode)
    
    import threading
    def task():
        execute_generate(job_id, topic=req.topic, duration_minutes=req.duration, audio_mode=req.audio_mode, niche=req.niche, video_mode=req.video_mode)
    
    bg.add_task(lambda: threading.Thread(target=task, daemon=True, name=f"generate-{job_id}").start())
    return {"job_id": job_id, "status": "generating"}


@app.get("/api/jobs")
def api_jobs(status: str | None = None) -> dict:
    return {"ok": True, "jobs": list_jobs(status=status)}


@app.get("/api/jobs/{job_id}")
def api_job(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return dict(job)


@app.get("/api/jobs/{job_id}/video")
def api_job_video(job_id: str) -> FileResponse:
    job = get_job(job_id)
    if not job or not job.get("video_path"):
        raise HTTPException(404, "Video not found")
    path = Path(job["video_path"])
    if not path.exists():
        raise HTTPException(404, "Video file missing")
    return FileResponse(path, media_type="video/mp4", headers={"Accept-Ranges": "bytes", "Cache-Control": "no-cache"})


@app.post("/api/jobs/{job_id}/approve")
def api_approve(job_id: str) -> dict:
    try:
        approve_job(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True, "job": get_job(job_id)}


@app.post("/api/jobs/{job_id}/reject")
def api_reject(job_id: str) -> dict:
    try:
        reject_job(job_id)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return {"ok": True}


@app.delete("/api/jobs/{job_id}")
def api_delete_job(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.get("video_path"):
        try:
            Path(job["video_path"]).unlink(missing_ok=True)
        except Exception:
            pass
    if job.get("work_dir"):
        try:
            shutil.rmtree(job["work_dir"], ignore_errors=True)
        except Exception:
            pass
    delete_job(job_id)
    return {"ok": True}


@app.post("/api/jobs/{job_id}/cancel")
def api_cancel_job(job_id: str) -> dict:
    update_job(job_id, status="failed", error="Cancelled by user", stage="cancelled", stage_message="Cancelled")
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


@app.post("/api/auth-youtube")
def api_auth_youtube() -> dict:
    return {"ok": True, "message": "Set YOUTUBE_REFRESH_TOKEN in .env manually for now"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765)
