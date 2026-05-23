from __future__ import annotations

import json

import anthropic

from pipeline.config import get_settings
from pipeline.llm.base import LLMProvider


class AnthropicProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings["anthropic_api_key"]:
            raise ValueError("ANTHROPIC_API_KEY is not set in .env")
        self.client = anthropic.Anthropic(api_key=settings["anthropic_api_key"])

    def complete_json(self, system: str, user: str) -> dict:
        response = self.client.messages.create(
            model="claude-3-5-haiku-latest",
            max_tokens=8192,
            system=system + "\nRespond with valid JSON only.",
            messages=[{"role": "user", "content": user}],
        )
        text = response.content[0].text
        return json.loads(text)
