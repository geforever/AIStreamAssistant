"""LLM provider factory — 按 config 返回具体实现。

Phase 2.6: 接 Live2DModel + Live2DConfig 来动态构造 schema。
"""
from __future__ import annotations

from g_chan.config import Live2DConfig, LLMConfig
from g_chan.live2d.model_loader import Live2DModel
from g_chan.llm.base import LLMProvider
from g_chan.llm.gemini import GeminiProvider
from g_chan.llm.schemas import build_chat_reply_schema


def create_provider(
    cfg: LLMConfig,
    *,
    live2d_cfg: Live2DConfig,
    live2d_model: Live2DModel | None = None,
) -> LLMProvider:
    """构造 LLM provider。

    live2d_model 为 None(或 live2d_cfg.enabled=False 时不加载) → expressions/motions 为空,
    schema 的 expression/motion enum 只含 "None",LLM 被迫输出 "None",parse 后归一化为 ""。
    live2d_cfg 仍用于读取 default_expression / default_motion 作为 fallback。
    """
    expressions = live2d_model.expressions if live2d_model else []
    motions = live2d_model.motions if live2d_model else []

    schema = build_chat_reply_schema(
        expressions=expressions,
        motions=motions,
    )

    name = cfg.provider
    if name == "gemini":
        return GeminiProvider(
            api_key=cfg.api_key,
            model=cfg.model,
            schema=schema,
            fallback_text=cfg.fallback.text,
            fallback_kaomoji=cfg.fallback.kaomoji,
            fallback_mood=cfg.fallback.mood,
            fallback_language=cfg.fallback.language,
            fallback_expression=live2d_cfg.default_expression,
            fallback_motion=live2d_cfg.default_motion,
            available_expressions=expressions,
            available_motions=motions,
        )
    if name in ("claude", "openai", "qwen"):
        raise NotImplementedError(
            f"LLM provider {name!r} not implemented yet — coming in a later phase."
        )
    raise ValueError(f"unknown provider: {name!r}")
