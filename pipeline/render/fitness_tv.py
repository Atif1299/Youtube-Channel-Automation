from __future__ import annotations

import random
import subprocess
from pathlib import Path

from pipeline.assets.tts import synthesize_voice
from pipeline.config import get_settings, load_brand, load_niche
from pipeline.models import Scene, VideoScript
from pipeline.render.ffmpeg_util import require_ffmpeg, run_ffmpeg
from pipeline.video_providers.router import resolve_clip_for_scene


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _prepare_scene_segment(
    scene: Scene,
    source: Path,
    out_path: Path,
    width: int,
    height: int,
    primary_color: str,
) -> None:
    label = _escape_drawtext(scene.on_screen_text)
    vf = (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"drawtext=text='{label}':fontsize=42:fontcolor=white:"
        f"box=1:boxcolor={primary_color}@0.85:boxborderw=12:"
        f"x=(w-text_w)/2:y=h-120"
    )
    # Loop short stock clips until scene.duration_sec is filled
    run_ffmpeg(
        [
            "-stream_loop",
            "-1",
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


def _concat_segments(segment_paths: list[Path], out_path: Path) -> None:
    list_file = out_path.parent / "concat_list.txt"
    lines = [f"file '{p.resolve().as_posix()}'" for p in segment_paths]
    list_file.write_text("\n".join(lines), encoding="utf-8")
  # Re-encode for consistent fps (avoids browser stopping after ~10s)
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


def _pick_music() -> Path | None:
    music_dir: Path = get_settings()["music_library_dir"]
    tracks = list(music_dir.glob("*.mp3")) + list(music_dir.glob("*.wav"))
    return random.choice(tracks) if tracks else None


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
        filter_parts.append("[2:a]aformat=sample_rates=44100:channel_layouts=stereo,aloop=loop=-1:size=2e+09,volume=0.18[m]")
        filter_parts.append("[v][m]amix=inputs=2:duration=longest,apad[aout]")
        maps = ["-map", "0:v", "-map", "[aout]"]
        use_shortest = True
    elif voice_path:
        filter_parts.append(
            "[1:a]aformat=sample_rates=44100:channel_layouts=mono,apad[aout]"
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


def _build_voiceover(script: VideoScript, work_dir: Path) -> Path | None:
    if script.audio_mode != "coach_voice":
        return None
    parts: list[Path] = []
    for scene in script.scenes:
        if not scene.voiceover.strip():
            continue
        part = work_dir / f"voice_{scene.id}.mp3"
        synthesize_voice(scene.voiceover, part)
        parts.append(part)
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


def render_fitness_tv(script: VideoScript, work_dir: Path) -> Path:
    require_ffmpeg()
    niche = load_niche()
    brand = load_brand()
    res = niche.get("resolution", "1920x1080")
    width, height = (int(x) for x in res.split("x"))
    primary = brand.get("primary_color", "#7B2CBF")

    work_dir.mkdir(parents=True, exist_ok=True)
    segments_dir = work_dir / "segments"
    segments_dir.mkdir(exist_ok=True)

    segment_paths: list[Path] = []
    for scene in script.scenes:
        clip = resolve_clip_for_scene(scene, work_dir)
        seg_out = segments_dir / f"scene_{scene.id:02d}.mp4"
        if clip and clip.exists():
            _prepare_scene_segment(scene, clip, seg_out, width, height, primary)
        else:
            _render_placeholder(scene, seg_out, width, height, primary)
        segment_paths.append(seg_out)

    concat_out = work_dir / "video_no_audio.mp4"
    _concat_segments(segment_paths, concat_out)

    voice = _build_voiceover(script, work_dir)
    music = _pick_music()
    if script.audio_mode == "music_only" and not music and not voice:
        print(
            "WARNING: music_only but assets/music/ is empty — video will be silent. "
            "Add MP3 files to assets/music/ or use coach_voice."
        )
    final = work_dir / "final.mp4"
    _mix_audio(concat_out, final, voice, music)
    return final


def _render_placeholder(
    scene: Scene, out_path: Path, width: int, height: int, primary: str
) -> None:
    label = _escape_drawtext(scene.on_screen_text)
    run_ffmpeg(
        [
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x2d1b4e:s={width}x{height}:d={scene.duration_sec}",
            "-vf",
            f"drawtext=text='{label}':fontsize=48:fontcolor=white:x=(w-text_w)/2:y=(h-text_h)/2",
            "-r",
            "30",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(out_path),
        ]
    )
