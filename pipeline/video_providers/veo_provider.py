from __future__ import annotations



import logging

import time

from pathlib import Path



from pipeline.config import get_settings, load_prompt

from pipeline.models import Scene, VisualBible

from pipeline.video_providers.base import VideoProvider

from pipeline.video_providers.stock_provider import StockProvider



log = logging.getLogger(__name__)





def _format_bible(bible: VisualBible | None) -> str:

    if not bible:

        return ""

    parts = []

    for key in ("setting", "subject", "wardrobe", "camera_style", "lighting", "color_palette"):

        val = getattr(bible, key, "")

        if val:

            parts.append(f"{key.replace('_', ' ').title()}: {val}")

    if not parts:

        return ""

    return "VISUAL BIBLE (keep consistent across all scenes):\n" + "\n".join(parts) + "\n\n"





def _format_prior(prior: Scene | None) -> str:

    if not prior:

        return ""

    summary = prior.visual_prompt or prior.exercise

    return f"PREVIOUS SCENE: {prior.on_screen_text} — {summary}\n\n"





class VeoProvider(VideoProvider):

    """Gemini Veo clip generation. Falls back to stock if API unavailable."""



    name = "veo"



    def generate_clip(

        self,

        scene: Scene,

        work_dir: Path,

        topic: str = "",

        *,

        visual_bible: VisualBible | None = None,

        prior_scene: Scene | None = None,

    ) -> Path | None:

        settings = get_settings()

        api_key = settings.get("gemini_api_key")

        if not api_key:

            log.warning("Veo skipped scene %s: GEMINI_API_KEY not set", scene.id)

            return StockProvider().generate_clip(scene, work_dir, topic)



        try:

            from google import genai

            from google.genai import types

        except ImportError:

            log.warning("Veo skipped scene %s: google-genai not installed", scene.id)

            return StockProvider().generate_clip(scene, work_dir, topic)



        model = settings.get("veo_model", "veo-3.0-generate-001")

        style = load_prompt("niches/fitness_warmup/visual_veo.md")

        scene_desc = scene.visual_prompt or scene.exercise

        on_screen = scene.on_screen_text or scene.exercise

        topic_block = f"TOPIC (overall video): {topic}\n" if topic else ""

        continuity = ""

        if scene.continuity_note:

            continuity = f"CONTINUITY: {scene.continuity_note}\n\n"

        prompt = (

            f"{style}\n\n"

            f"{_format_bible(visual_bible)}"

            f"{_format_prior(prior_scene)}"

            f"{topic_block}"

            f"{continuity}"

            f"THIS SCENE ({scene.duration_sec}s): {on_screen}\n"

            f"Focus: {scene_desc}\n\n"

            f"Generate one cohesive clip that clearly shows this moment in the context of the topic. "

            f"Do not default to a generic gym or office unless the topic calls for it."

        )

        out = work_dir / f"veo_scene_{scene.id}.mp4"

        if out.exists():

            return out



        client = genai.Client(api_key=api_key)

        config_kwargs: dict = {"negative_prompt": scene.negative_prompt}

        try:

            config_kwargs["aspect_ratio"] = "16:9"

            config = types.GenerateVideosConfig(**config_kwargs)

        except TypeError:

            config = types.GenerateVideosConfig(negative_prompt=scene.negative_prompt)



        try:

            log.info("Veo scene %s: starting %s", scene.id, model)

            operation = client.models.generate_videos(

                model=model,

                prompt=prompt,

                config=config,

            )

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

            return StockProvider().generate_clip(scene, work_dir, topic)

