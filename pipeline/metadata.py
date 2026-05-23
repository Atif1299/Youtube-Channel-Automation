from __future__ import annotations

import json

from pipeline.config import load_brand, load_niche, load_prompt
from pipeline.llm import get_llm
from pipeline.models import VideoMetadata, VideoScript


def generate_metadata(script: VideoScript, used_ai_clips: bool = False) -> VideoMetadata:
    niche = load_niche()
    brand = load_brand()
    system = (
        "You write YouTube SEO metadata for fitness warm-up videos. "
        "Return JSON only with keys: title, description, tags (array), chapters (array of {time, title})."
    )
    user = f"""
Video title draft: {script.title_draft}
Topic: {script.topic}
Duration seconds: {script.total_duration_sec}
Keywords: {', '.join(niche.get('keywords_seed', []))}
Channel: {brand.get('channel_name')}
Disclaimer to append in description:
{brand.get('disclaimer')}
CTA: {niche.get('cta')}

Exercises in order:
{json.dumps([s.exercise for s in script.scenes], indent=2)}

Title pattern examples (do not copy exactly):
- "12 Min Morning Full Body Warm Up | Low Impact No Equipment"
- "15 Min Desk Stretch Mobility Routine | Follow Along"

Generate chapters with MM:SS timestamps starting at 0:00 for intro.
"""
    raw = get_llm().complete_json(system, user)
    return VideoMetadata(
        title=raw.get("title", script.title_draft),
        description=raw.get("description", ""),
        tags=raw.get("tags", niche.get("keywords_seed", [])[:10]),
        contains_synthetic_media=used_ai_clips,
        chapters=raw.get("chapters", []),
    )
