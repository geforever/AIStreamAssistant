"""LLM provider factory — 按 config 返回具体实现。"""
from __future__ import annotations

from g_chan.config import LLMConfig
from g_chan.llm.base import LLMProvider
from g_chan.llm.gemini import GeminiProvider


def create_provider(cfg: LLMConfig) -> LLMProvider:
    name = cfg.provider
    if name == "gemini":
        return GeminiProvider(
            api_key=cfg.api_key,
            model=cfg.model,
            fallback_text=cfg.fallback.text,
            fallback_kaomoji=cfg.fallback.kaomoji,
            fallback_mood=cfg.fallback.mood,
            fallback_language=cfg.fallback.language,
        )
    if name in ("claude", "openai", "qwen"):
        raise NotImplementedError(
            f"LLM provider {name!r} not implemented yet — coming in a later phase."
        )
    raise ValueError(f"unknown provider: {name!r}")
