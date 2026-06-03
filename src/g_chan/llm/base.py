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


# 给 Gemini/Claude/OpenAI JSON mode 用的输出 schema。各 provider 翻译成自己的格式。
LLM_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "回复正文,只包含会被朗读的内容。不要在里面写颜文字或括号注解。",
        },
        "kaomoji": {
            "type": "string",
            "description": "颜文字(可选,可空)。仅作为弹幕视觉装饰,不会被朗读。",
        },
        "mood": {
            "type": "string",
            "enum": list(MOOD_VALUES),
            "description": "情绪标签,Phase 3 用于驱动 Live2D 表情。",
        },
    },
    "required": ["text", "mood"],
}


def parse_llm_json(raw: str) -> tuple[str, str, Mood]:
    """解析 LLM 的 JSON 输出 → (text, kaomoji, mood)。

    任何解析失败 → 全文当 text,kaomoji 空,mood='happy'。
    未知 mood 字符串 → 'happy'。
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        log.warning("LLM JSON parse failed: %s, raw=%r", e, raw)
        return (raw or "").strip(), "", "happy"

    if not isinstance(data, dict):
        log.warning("LLM JSON is not an object: %r", raw)
        return (raw or "").strip(), "", "happy"

    text = str(data.get("text", "")).strip()
    kaomoji = str(data.get("kaomoji", "")).strip()
    mood_raw = data.get("mood", "happy")
    if mood_raw in MOOD_VALUES:
        mood: Mood = mood_raw  # type: ignore[assignment]
    else:
        log.warning("LLM returned unknown mood: %r", mood_raw)
        mood = "happy"
    return text, kaomoji, mood


@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMReply:
    text: str          # 主回复正文 — TTS 朗读这个
    kaomoji: str       # 颜文字(可空)— chat 拼接展示用,不进 TTS
    mood: Mood         # 情绪标签 — Phase 3 驱动 Live2D 表情
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
