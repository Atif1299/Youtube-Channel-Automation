from __future__ import annotations



from pipeline.config import get_settings, load_niche

from pipeline.models import VideoScript





def _veo_scene_indices(scene_count: int, max_veo: int) -> set[int]:

    """Pick intro, outro, and evenly spaced key scenes for Veo."""

    if scene_count <= 0 or max_veo <= 0:

        return set()

    indices = {0, scene_count - 1}

    remaining = max_veo - len(indices)

    if remaining <= 0:

        return set(sorted(indices)[:max_veo])

    middle = list(range(1, scene_count - 1))

    if not middle:

        return indices

    step = max(1, len(middle) // remaining)

    for i in range(0, len(middle), step):

        if len(indices) >= max_veo:

            break

        indices.add(middle[i])

    return set(sorted(indices)[:max_veo])





def assign_providers(script: VideoScript, video_mode: str) -> tuple[VideoScript, str | None]:

    """Set per-scene provider from video_mode. Returns optional warning message."""

    settings = get_settings()

    niche = load_niche()

    has_gemini = bool(settings.get("gemini_api_key"))

    warning = None



    if video_mode == "premium" and not has_gemini:

        warning = "Premium unavailable — add GEMINI_API_KEY; using Pexels stock"

        video_mode = "stock"



    max_veo = int(niche.get("max_ai_clips_per_video", 5))

    use_veo = video_mode == "premium" and has_gemini

    veo_indices = _veo_scene_indices(len(script.scenes), max_veo) if use_veo else set()



    for i, scene in enumerate(script.scenes):

        scene.provider = "veo" if i in veo_indices else "stock"



    return script, warning

