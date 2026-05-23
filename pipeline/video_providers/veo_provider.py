from __future__ import annotations

import time
from pathlib import Path

from pipeline.config import get_settings, load_prompt
from pipeline.models import Scene
from pipeline.video_providers.base import VideoProvider
from pipeline.video_providers.stock_provider import StockProvider


class VeoProvider(VideoProvider):
    """Gemini Veo clip generation. Falls back to stock if API unavailable."""

    name = "veo"

    def generate_clip(self, scene: Scene, work_dir: Path) -> Path | None:
        settings = get_settings()
        api_key = settings.get("gemini_api_key")
        if not api_key:
            return StockProvider().generate_clip(scene, work_dir)

        try:
            from google import genai
            from google.genai import types
        except ImportError:
            return StockProvider().generate_clip(scene, work_dir)

        style = load_prompt("niches/fitness_warmup/visual_veo.md")
        prompt = f"{style}\n\n{scene.visual_prompt or scene.exercise}"
        out = work_dir / f"veo_scene_{scene.id}.mp4"
        if out.exists():
            return out

        client = genai.Client(api_key=api_key)
        try:
            operation = client.models.generate_videos(
                model="veo-3.0-generate-preview",
                prompt=prompt,
                config=types.GenerateVideosConfig(
                    negative_prompt=scene.negative_prompt,
                ),
            )
            while not operation.done:
                time.sleep(15)
                operation = client.operations.get(operation)

            generated = operation.response.generated_videos[0]
            client.files.download(file=generated.video)
            generated.video.save(str(out))
            return out
        except Exception:
            return StockProvider().generate_clip(scene, work_dir)
