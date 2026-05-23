from __future__ import annotations

from pathlib import Path

from openai import OpenAI

from pipeline.config import get_settings


def synthesize_voice(text: str, output_path: Path, voice: str = "alloy") -> Path:
    settings = get_settings()
    if not settings["openai_api_key"]:
        raise ValueError("OPENAI_API_KEY required for TTS")
    client = OpenAI(api_key=settings["openai_api_key"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with client.audio.speech.with_streaming_response.create(
        model="tts-1",
        voice=voice,
        input=text,
    ) as response:
        response.stream_to_file(output_path)
    return output_path
