from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
    provider: Literal["stock", "veo", "hailuo", "kling"] = "stock"
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
