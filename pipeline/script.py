from __future__ import annotations

import json

from pipeline.config import load_brand, load_niche, load_prompt
from pipeline.llm import get_llm
from pipeline.models import VideoScript


def _scene_guidance(duration_minutes: int) -> str:
    if duration_minutes <= 1:
        return (
            "Use exactly 3-4 scenes totaling about 60 seconds. "
            "Intro ~10s, one or two exercises ~20-25s each, cool-down ~10s."
        )
    if duration_minutes <= 3:
        return "Use 4-6 scenes."
    if duration_minutes <= 8:
        return "Use 6-10 scenes."
    return f"Use 8-14 scenes for a {duration_minutes} minute video."


def generate_script(
    topic: str,
    duration_minutes: int = 12,
    audio_mode: str = "music_only",
    niche_name: str = "fitness_warmup",
) -> VideoScript:
    niche = load_niche(niche_name)
    brand = load_brand()
    system = load_prompt("niches/fitness_warmup/script_system.md")

    user = f"""
Topic: {topic}
Target duration: {duration_minutes} minutes
Audio mode: {audio_mode}
Niche audience: {niche.get('audience')}
Tone: {niche.get('tone')}
Brand channel: {brand.get('channel_name')}
Content pillars (for variety): {', '.join(niche.get('content_pillars', []))}

Return JSON with this exact structure:
{{
  "title_draft": "string",
  "topic": "string",
  "total_duration_sec": number,
  "audio_mode": "{audio_mode}",
  "scenes": [
    {{
      "id": 1,
      "exercise": "string",
      "duration_sec": number,
      "on_screen_text": "string",
      "voiceover": "string",
      "visual_prompt": "string",
      "negative_prompt": "string",
      "provider": "stock",
      "stock_query": "string"
    }}
  ]
}}
{_scene_guidance(duration_minutes)} First scene: intro. Last scene: cool-down.
"""

    raw = get_llm().complete_json(system, user)
    raw["topic"] = topic
    raw["audio_mode"] = audio_mode
    return VideoScript.model_validate(raw)


def script_to_json(script: VideoScript) -> str:
    return script.model_dump_json(indent=2)
