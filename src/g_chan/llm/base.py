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
) -> tuple[str, str, Mood, Language]:
    """解析 LLM 的 JSON 输出 → (text, kaomoji, mood, language)。

    任何解析失败(无效 JSON、非对象、空 text)→ 返回 fallback 四元组。
    未知 mood/language 字符串 → 用 fallback。
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        log.warning("LLM JSON parse failed: %s, raw=%r", e, raw)
        return fallback_text, fallback_kaomoji, fallback_mood, fallback_language

    if not isinstance(data, dict):
        log.warning("LLM JSON is not an object: %r", raw)
        return fallback_text, fallback_kaomoji, fallback_mood, fallback_language

    text = str(data.get("text", "")).strip()
    if not text:
        log.warning("LLM JSON has empty/missing text field: %r", raw)
        return fallback_text, fallback_kaomoji, fallback_mood, fallback_language

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

    return text, kaomoji, mood, language


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
