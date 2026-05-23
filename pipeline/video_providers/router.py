from __future__ import annotations

from pathlib import Path

from pipeline.models import Scene
from pipeline.video_providers.stock_provider import StockProvider
from pipeline.video_providers.veo_provider import VeoProvider

_PROVIDERS = {
    "stock": StockProvider(),
    "veo": VeoProvider(),
    "hailuo": StockProvider(),
    "kling": StockProvider(),
}


def resolve_clip_for_scene(scene: Scene, work_dir: Path) -> Path | None:
    provider_name = scene.provider or "stock"
    provider = _PROVIDERS.get(provider_name, StockProvider())
    return provider.generate_clip(scene, work_dir)
