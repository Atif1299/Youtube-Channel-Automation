from __future__ import annotations

import json

from openai import OpenAI

from pipeline.config import get_settings
from pipeline.llm.base import LLMProvider


class OpenAIProvider(LLMProvider):
    def __init__(self) -> None:
        settings = get_settings()
        if not settings["openai_api_key"]:
            raise ValueError("OPENAI_API_KEY is not set in .env")
        self.client = OpenAI(api_key=settings["openai_api_key"])

    def complete_json(self, system: str, user: str) -> dict:
        response = self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        content = response.choices[0].message.content or "{}"
        return json.loads(content)
