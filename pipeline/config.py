from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def _path_from_env(key: str, default: str) -> Path:
    raw = os.getenv(key, default)
    p = Path(raw)
    return p if p.is_absolute() else ROOT / p


@lru_cache
def get_settings() -> dict:
    return {
        "root": ROOT,
        "openai_api_key": os.getenv("OPENAI_API_KEY", ""),
        "anthropic_api_key": os.getenv("ANTHROPIC_API_KEY", ""),
        "gemini_api_key": os.getenv("GEMINI_API_KEY", ""),
        "pexels_api_key": os.getenv("PEXELS_API_KEY", ""),
        "youtube_api_key": os.getenv("YOUTUBE_API_KEY", ""),
        "youtube_client_id": os.getenv("YOUTUBE_CLIENT_ID", ""),
        "youtube_client_secret": os.getenv("YOUTUBE_CLIENT_SECRET", ""),
        "youtube_refresh_token": os.getenv("YOUTUBE_REFRESH_TOKEN", ""),
        "default_llm": os.getenv("DEFAULT_LLM", "openai"),
        "default_tts": os.getenv("DEFAULT_TTS", "openai"),
        "default_video_provider": os.getenv("DEFAULT_VIDEO_PROVIDER", "stock"),
        "veo_model": os.getenv("VEO_MODEL", "veo-3.0-generate-001"),
        "local_clips_dir": _path_from_env("LOCAL_CLIPS_DIR", "assets/clips"),
        "music_library_dir": _path_from_env("MUSIC_LIBRARY_DIR", "assets/music"),
        "output_pending": ROOT / "assets/output/pending_review",
        "output_approved": ROOT / "assets/output/approved",
        "output_rejected": ROOT / "assets/output/rejected",
        "jobs_db": ROOT / "data/jobs.db",
        "competitor_cache": ROOT / "data/competitor_cache.json",
    }


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_brand() -> dict:
    return load_yaml(ROOT / "config/brand.yaml")


def load_niche(name: str = "fitness_warmup") -> dict:
    return load_yaml(ROOT / "config/niches" / f"{name}.yaml")


def load_prompt(rel_path: str) -> str:
    path = ROOT / "prompts" / rel_path
    return path.read_text(encoding="utf-8")
