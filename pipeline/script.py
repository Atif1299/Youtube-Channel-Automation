from __future__ import annotations

from pipeline.config import load_brand, load_niche, load_prompt
from pipeline.llm import get_llm
from pipeline.models import VideoScript
from pipeline.research.competitor import load_competitor_context


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


def _duration_valid(script: VideoScript) -> bool:
    scene_total = sum(s.duration_sec for s in script.scenes)
    return scene_total == script.total_duration_sec


def _fix_duration_mismatch(script: VideoScript) -> VideoScript:
    """Adjust last scene so scene durations sum to total_duration_sec."""
    if not script.scenes:
        return script
    scene_total = sum(s.duration_sec for s in script.scenes)
    target = script.total_duration_sec
    if scene_total == target:
        return script
    diff = target - scene_total
    last = script.scenes[-1]
    last.duration_sec = max(5, min(180, last.duration_sec + diff))
    script.total_duration_sec = sum(s.duration_sec for s in script.scenes)
    return script


def generate_script(
    topic: str,
    duration_minutes: int = 12,
    audio_mode: str = "music_only",
    niche_name: str = "fitness_warmup",
    extra_context: str = "",
) -> VideoScript:
    niche = load_niche(niche_name)
    brand = load_brand()
    system = load_prompt("niches/fitness_warmup/script_system.md")
    competitor_ctx = load_competitor_context()

    context_block = ""
    if competitor_ctx:
        context_block += f"\nCompetitor research (emulate title/structure patterns, not copy titles):\n{competitor_ctx}\n"
    if extra_context.strip():
        context_block += f"\nAdditional context:\n{extra_context.strip()}\n"

    user = f"""
Topic: {topic}
Target duration: {duration_minutes} minutes
Audio mode: {audio_mode}
Niche audience: {niche.get('audience')}
Tone: {niche.get('tone')}
Brand channel: {brand.get('channel_name')}
Content pillars (for variety): {', '.join(niche.get('content_pillars', []))}
{context_block}
Return JSON with this exact structure:
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
      "voiceover": "string (must fit naturally within duration_sec)",
      "visual_prompt": "string (2-4 sentences: subject, setting, action, camera, lighting — must match topic and visual_bible)",
      "continuity_note": "string (optional link to bible or prior scene)",
      "negative_prompt": "string",
      "stock_query": "string (3-6 words, Pexels fallback for this scene)"
    }}
  ]
}}
{_scene_guidance(duration_minutes)} First scene: intro. Last scene: closing.
Each scene's voiceover must be short enough to speak within that scene's duration_sec.
Sum of all duration_sec MUST equal total_duration_sec exactly.
Every visual_prompt and stock_query must be specific to the typed topic — not reused generic phrases across unrelated topics.
Each visual_prompt must describe a distinct, relatable moment that fits the topic; scenes should flow as one coherent video.
"""

    llm = get_llm()
    raw = llm.complete_json(system, user)
    raw["topic"] = topic
    raw["audio_mode"] = audio_mode
    script = VideoScript.model_validate(raw)
    if not _duration_valid(script):
        raw = llm.complete_json(
            system,
            user
            + "\n\nCORRECTION REQUIRED: scene duration_sec values must sum exactly to total_duration_sec. Fix and return valid JSON.",
        )
        raw["topic"] = topic
        raw["audio_mode"] = audio_mode
        script = VideoScript.model_validate(raw)
        if not _duration_valid(script):
            script = _fix_duration_mismatch(script)
    return script


def script_to_json(script: VideoScript) -> str:
    return script.model_dump_json(indent=2)
