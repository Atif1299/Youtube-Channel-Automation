from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Scene(BaseModel):
    id: int
    exercise: str
    duration_sec: int = Field(ge=5, le=180)
    on_screen_text: str
    voiceover: str = ""
    visual_prompt: str = ""
    negative_prompt: str = "warped limbs, blurry, watermark"
    provider: Literal["stock", "veo", "hailuo", "kling"] = "stock"
    stock_query: str = ""


class VideoScript(BaseModel):
    title_draft: str
    topic: str
    total_duration_sec: int
    audio_mode: Literal["music_only", "coach_voice"] = "music_only"
    scenes: list[Scene]


class VideoMetadata(BaseModel):
    title: str
    description: str
    tags: list[str]
    category_id: str = "17"
    contains_synthetic_media: bool = False
    chapters: list[dict] = Field(default_factory=list)
