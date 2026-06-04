"""LLM provider 抽象层 — 接口、类型、JSON 解析。"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

log = logging.getLogger(__name__)

Mood = Literal[
    "happy", "angry", "sad", "surprised",
    "shy",   "thinking", "tsundere", "dizzy",
]

MOOD_VALUES: tuple[Mood, ...] = (
    "happy", "angry", "sad", "surprised",
    "shy",   "thinking", "tsundere", "dizzy",
)

Language = Literal["zh", "en", "ja"]
LANGUAGE_VALUES: tuple[Language, ...] = ("zh", "en", "ja")


def parse_llm_json(
    raw: str,
    *,
    fallback_text: str,
    fallback_kaomoji: str,
    fallback_mood: Mood,
    fallback_language: Language,
    fallback_expression: str = "",
    fallback_motion: str = "",
    available_expressions: list[str] | None = None,
    available_motions: list[str] | None = None,
) -> tuple[str, str, Mood, Language, str, str]:
    """解析 LLM JSON → (text, kaomoji, mood, language, expression, motion)。

    expression / motion 行为:
    - available_* 是 None 或空 list → Live2D disabled,返回 ""(忽略 JSON 里的值)
    - LLM 输出 "None" 字符串 → 规范化为 ""
    - LLM 输出 "" 或不在 available 里 → 回退到 fallback_*
    """
    available_expressions = available_expressions or []
    available_motions = available_motions or []

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        log.warning("LLM JSON parse failed: %s, raw=%r", e, raw)
        return (
            fallback_text, fallback_kaomoji, fallback_mood, fallback_language,
            _normalize_or_fallback(None, available_expressions, fallback_expression),
            _normalize_or_fallback(None, available_motions, fallback_motion),
        )

    if not isinstance(data, dict):
        log.warning("LLM JSON is not an object: %r", raw)
        return (
            fallback_text, fallback_kaomoji, fallback_mood, fallback_language,
            _normalize_or_fallback(None, available_expressions, fallback_expression),
            _normalize_or_fallback(None, available_motions, fallback_motion),
        )

    text = str(data.get("text", "")).strip()
    if not text:
        log.warning("LLM JSON has empty/missing text field: %r", raw)
        return (
            fallback_text, fallback_kaomoji, fallback_mood, fallback_language,
            _normalize_or_fallback(None, available_expressions, fallback_expression),
            _normalize_or_fallback(None, available_motions, fallback_motion),
        )

    kaomoji = str(data.get("kaomoji", "")).strip()

    mood_raw = data.get("mood", "happy")
    if mood_raw in MOOD_VALUES:
        mood: Mood = mood_raw  # type: ignore[assignment]
    else:
        log.warning("LLM returned unknown mood: %r", mood_raw)
        mood = "happy"

    lang_raw = data.get("language", fallback_language)
    if lang_raw in LANGUAGE_VALUES:
        language: Language = lang_raw  # type: ignore[assignment]
    else:
        log.warning("LLM returned unknown language: %r", lang_raw)
        language = fallback_language

    # expression / motion:Live2D 禁用时返回 ""
    expression = _normalize_or_fallback(
        data.get("expression"), available_expressions, fallback_expression,
    )
    motion = _normalize_or_fallback(
        data.get("motion"), available_motions, fallback_motion,
    )

    return text, kaomoji, mood, language, expression, motion


def _normalize_or_fallback(raw, available, fallback) -> str:
    """规范化 LLM 输出的 expression/motion 值(项目约定:全小写)。

    available 假定已经全部小写(model_loader 入库时已规范化)。
    LLM 输出和 fallback 入参做防御性 lower() 后比对。

    - available 为空(Live2D 没模型) → 总返回 ""
    - raw 是 None / "" / "none"(任意大小写)→ 规范化为 ""
    - raw 在 available 里 → 返回小写化的 raw
    - raw 不在 → 用 fallback(也要在 available 里,不然 "")
    """
    if not available:
        return ""

    raw_lower = raw.lower() if isinstance(raw, str) else ""
    if raw_lower in ("", "none"):
        normalized = ""
    elif raw_lower in available:
        return raw_lower
    else:
        normalized = ""

    if normalized == "" and fallback:
        fb_lower = fallback.lower() if isinstance(fallback, str) else ""
        if fb_lower in ("", "none"):
            return ""
        if fb_lower in available:
            return fb_lower
        return ""
    return normalized


@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMReply:
    text: str          # 主回复正文 — TTS 朗读这个
    kaomoji: str       # 颜文字(可空)— chat 拼接展示用,不进 TTS
    mood: Mood         # 情绪标签 — Phase 3 驱动 Live2D 表情
    language: Language # 文本语言 — TTS 据此选 voice
    raw: str           # 原始 JSON 字符串(日志/调试)
    latency_ms: int
    tokens_in: int
    tokens_out: int
    # Phase 2.6 新增 — Live2D 物理表情和动作("" = 无变化 / Live2D disabled)
    expression: str = ""
    motion: str = ""


class LLMError(Exception): ...
class LLMTimeoutError(LLMError): ...
class LLMRateLimitError(LLMError): ...
class LLMServerError(LLMError): ...


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.9,
        max_tokens: int = 300,
        timeout_s: float = 10.0,
    ) -> LLMReply: ...
