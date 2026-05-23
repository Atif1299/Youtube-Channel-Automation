from __future__ import annotations

import random
from collections.abc import Callable
from pathlib import Path

from pipeline.assets.tts import synthesize_voice
from pipeline.config import get_settings, load_brand, load_niche
from pipeline.models import Scene, VideoScript
from pipeline.render.ffmpeg_util import probe_duration, require_ffmpeg, run_ffmpeg
from pipeline.video_providers.router import resolve_clip_for_scene


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _truncate_label(text: str, max_len: int = 48) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _video_filter(
    width: int,
    height: int,
    label: str,
    font_size: int,
    text_color: str,
    primary_color: str,
) -> str:
    safe_bottom = 140
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"drawtext=text='{label}':fontsize={font_size}:fontcolor={text_color}:"
        f"box=1:boxcolor={primary_color}@0.85:boxborderw=12:"
        f"x=(w-text_w)/2:y=h-{safe_bottom}"
    )


def _prepare_scene_segment(
    scene: Scene,
    source: Path,
    out_path: Path,
    width: int,
    height: int,
    primary_color: str,
    font_size: int,
    text_color: str,
    loop: bool = True,
) -> None:
    label = _escape_drawtext(_truncate_label(scene.on_screen_text))
    vf = _video_filter(width, height, label, font_size, text_color, primary_color)
    cmd = []
    if loop:
        cmd.extend(["-stream_loop", "-1"])
    cmd.extend(
        [
            "-i",
            str(source),
            "-t",
            str(scene.duration_sec),
            "-vf",
            vf,
            "-an",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            "fast",
            "-pix_fmt",
            "yuv420p",
            str(out_path),
        ]
    )
    run_ffmpeg(cmd)


def _concat_segments(
    segment_paths: list[Path],
    out_path: Path,
    transition_sec: float = 0.0,
    segment_durations: list[float] | None = None,
) -> None:
    if not segment_paths:
        raise ValueError("No segments to concat")
    if len(segment_paths) == 1 or transition_sec <= 0:
        list_file = out_path.parent / "concat_list.txt"
        lines = [f"file '{p.resolve().as_posix()}'" for p in segment_paths]
        list_file.write_text("\n".join(lines), encoding="utf-8")
        run_ffmpeg(
            [
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                str(list_file),
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-preset",
                "fast",
                "-pix_fmt",
                "yuv420p",
                "-an",
                "-movflags",
                "+faststart",
                str(out_path),
            ]
        )
        return

    if not segment_durations or len(segment_durations) != len(segment_paths):
        segment_durations = [probe_duration(p) or 10.0 for p in segment_paths]

    inputs: list[str] = []
    for p in segment_paths:
        inputs.extend(["-i", str(p)])

    filter_parts: list[str] = []
    prev = "[0:v]"
    offset = 0.0
    for i in range(1, len(segment_paths)):
        offset += max(0.1, segment_durations[i - 1] - transition_sec)
        out_label = f"[v{i}]" if i < len(segment_paths) - 1 else "[vout]"
        filter_parts.append(
            f"{prev}[{i}:v]xfade=transition=fade:duration={transition_sec}:offset={offset:.3f}{out_label}"
        )
        prev = out_label

    cmd = inputs + [
        "-filter_complex",
        ";".join(filter_parts),
        "-map",
        "[vout]",
        "-r",
        "30",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-pix_fmt",
        "yuv420p",
        "-an",
        "-movflags",
        "+faststart",
        str(out_path),
    ]
    run_ffmpeg(cmd)


def _pick_music() -> Path | None:
    music_dir: Path = get_settings()["music_library_dir"]
    tracks = list(music_dir.glob("*.mp3")) + list(music_dir.glob("*.wav"))
    return random.choice(tracks) if tracks else None


def _fit_voice_clip(src: Path, dest: Path, duration_sec: float) -> None:
    """Trim or pad a voice clip so it matches the on-screen scene length."""
    dur = max(0.1, float(duration_sec))
    run_ffmpeg(
        [
            "-i",
            str(src),
            "-af",
            f"atrim=duration={dur},apad=whole_dur={dur}",
            "-t",
            str(dur),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(dest),
        ]
    )


def _silence_clip(dest: Path, duration_sec: float) -> None:
    dur = max(0.1, float(duration_sec))
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            "anullsrc=r=44100:cl=mono",
            "-t",
            str(dur),
            "-c:a",
            "libmp3lame",
            "-q:a",
            "4",
            str(dest),
        ]
    )


def _mix_audio(
    video_path: Path,
    output_path: Path,
    voice_path: Path | None,
    music_path: Path | None,
) -> None:
    if not voice_path and not music_path:
        run_ffmpeg(
            [
                "-i",
                str(video_path),
                "-c",
                "copy",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        return

    inputs = ["-i", str(video_path)]
    filter_parts: list[str] = []
    maps: list[str] = []

    if voice_path:
        inputs.extend(["-i", str(voice_path)])
    if music_path:
        inputs.extend(["-i", str(music_path)])

    use_shortest = False
    if voice_path and music_path:
        filter_parts.append("[1:a]aformat=sample_rates=44100:channel_layouts=mono[v]")
        filter_parts.append(
            "[2:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            "aloop=loop=-1:size=2e+09,volume=0.18[m]"
        )
        filter_parts.append("[v][m]amix=inputs=2:duration=first:dropout_transition=2[aout]")
        maps = ["-map", "0:v", "-map", "[aout]"]
        use_shortest = True
    elif voice_path:
        filter_parts.append(
            "[1:a]aformat=sample_rates=44100:channel_layouts=mono[aout]"
        )
        maps = ["-map", "0:v", "-map", "[aout]"]
        use_shortest = True
    elif music_path:
        filter_parts.append(
            "[1:a]aformat=sample_rates=44100:channel_layouts=stereo,"
            "aloop=loop=-1:size=2e+09,volume=0.25[aout]"
        )
        maps = ["-map", "0:v", "-map", "[aout]"]
        use_shortest = True

    cmd = inputs.copy()
    if filter_parts:
        cmd.extend(["-filter_complex", ";".join(filter_parts)])
    cmd.extend(maps)
    tail = ["-c:v", "copy", "-c:a", "aac", "-b:a", "192k"]
    if use_shortest:
        tail.append("-shortest")
    tail.extend(["-movflags", "+faststart", str(output_path)])
    cmd.extend(tail)
    run_ffmpeg(cmd)


def _build_voiceover(
    script: VideoScript,
    work_dir: Path,
    on_stage: Callable[[str, str, int], None] | None = None,
) -> Path | None:
    if script.audio_mode != "coach_voice":
        return None
    parts: list[Path] = []
    scenes = script.scenes
    for i, scene in enumerate(scenes):
        if on_stage:
            pct = 55 + int(20 * (i + 1) / max(len(scenes), 1))
            on_stage("tts", f"Voiceover scene {i + 1}/{len(scenes)}…", pct)
        synced = work_dir / f"voice_synced_{scene.id:02d}.mp3"
        if scene.voiceover.strip():
            raw = work_dir / f"voice_{scene.id}.mp3"
            synthesize_voice(scene.voiceover, raw)
            _fit_voice_clip(raw, synced, scene.duration_sec)
        else:
            _silence_clip(synced, scene.duration_sec)
        parts.append(synced)
    if not parts:
        return None
    if len(parts) == 1:
        return parts[0]
    list_file = work_dir / "voice_concat.txt"
    list_file.write_text(
        "\n".join(f"file '{p.resolve().as_posix()}'" for p in parts),
        encoding="utf-8",
    )
    combined = work_dir / "voiceover.mp3"
    run_ffmpeg(
        [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(list_file),
            "-c",
            "copy",
            str(combined),
        ]
    )
    return combined


def render_fitness_tv(
    script: VideoScript,
    work_dir: Path,
    on_stage: Callable[[str, str, int], None] | None = None,
) -> Path:
    require_ffmpeg()
    niche = load_niche()
    brand = load_brand()
    res = niche.get("resolution", "1920x1080")
    width, height = (int(x) for x in res.split("x"))
    primary = brand.get("primary_color", "#7B2CBF")
    font_size = int(brand.get("font_size", 48))
    text_color = brand.get("text_color", "#FFFFFF")
    transition_sec = float(niche.get("segment_transition_sec", 0) or 0)

    work_dir.mkdir(parents=True, exist_ok=True)
    segments_dir = work_dir / "segments"
    segments_dir.mkdir(exist_ok=True)

    total = len(script.scenes)
    segment_paths: list[Path] = []
    prior: Scene | None = None
    for i, scene in enumerate(script.scenes):
        if on_stage:
            pct = 25 + int(30 * (i + 1) / max(total, 1))
            if scene.provider == "veo":
                on_stage(
                    "veo",
                    f"Scene {i + 1}/{total}: Veo 3 generating clip (1–2 min)…",
                    pct,
                )
            else:
                on_stage(
                    "clips",
                    f"Scene {i + 1}/{total}: fetching stock clip…",
                    pct,
                )
        clip = resolve_clip_for_scene(
            scene,
            work_dir,
            topic=script.topic,
            visual_bible=script.visual_bible,
            prior_scene=prior,
        )
        seg_out = segments_dir / f"scene_{scene.id:02d}.mp4"
        if clip and clip.exists():
            clip_dur = probe_duration(clip)
            use_loop = clip_dur is None or clip_dur < scene.duration_sec - 0.5
            _prepare_scene_segment(
                scene,
                clip,
                seg_out,
                width,
                height,
                primary,
                font_size,
                text_color,
                loop=use_loop,
            )
        else:
            _render_placeholder(
                scene, seg_out, width, height, primary, font_size, text_color
            )
        segment_paths.append(seg_out)
        prior = scene

    if on_stage:
        on_stage("render", "Concatenating segments…", 58)

    concat_out = work_dir / "video_no_audio.mp4"
    scene_durations = [float(s.duration_sec) for s in script.scenes]
    _concat_segments(
        segment_paths,
        concat_out,
        transition_sec=transition_sec,
        segment_durations=scene_durations,
    )

    voice = _build_voiceover(script, work_dir, on_stage=on_stage)
    music = _pick_music()
    if script.audio_mode == "music_only" and not music and not voice:
        print(
            "WARNING: music_only but assets/music/ is empty — video will be silent. "
            "Add MP3 files to assets/music/ or use coach_voice."
        )
    if on_stage:
        on_stage("mix", "Mixing audio…", 80)
    final = work_dir / "final.mp4"
    _mix_audio(concat_out, final, voice, music)
    return final


def _render_placeholder(
    scene: Scene,
    out_path: Path,
    width: int,
    height: int,
    primary: str,
    font_size: int,
    text_color: str,
) -> None:
    label = _escape_drawtext(_truncate_label(scene.on_screen_text))
    safe_bottom = 140
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x2d1b4e:s={width}x{height}:d={scene.duration_sec}",
            "-vf",
            f"drawtext=text='{label}':fontsize={font_size}:fontcolor={text_color}:"
            f"box=1:boxcolor={primary}@0.85:boxborderw=12:"
            f"x=(w-text_w)/2:y=h-{safe_bottom}",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(out_path),
        ]
    )
