from __future__ import annotations

from pipeline.config import get_settings
from pipeline.llm.anthropic_provider import AnthropicProvider
from pipeline.llm.base import LLMProvider
from pipeline.llm.openai_provider import OpenAIProvider


def get_llm(provider: str | None = None) -> LLMProvider:
    name = (provider or get_settings()["default_llm"]).lower()
    if name == "anthropic":
        return AnthropicProvider()
    return OpenAIProvider()
