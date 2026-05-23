from __future__ import annotations

from pathlib import Path

from pipeline.assets.stock import resolve_scene_clip
from pipeline.models import Scene
from pipeline.video_providers.base import VideoProvider


class StockProvider(VideoProvider):
    name = "stock"

    def generate_clip(self, scene: Scene, work_dir: Path) -> Path | None:
        query = scene.stock_query or scene.exercise
        return resolve_scene_clip(query, min_duration=min(5, scene.duration_sec))
