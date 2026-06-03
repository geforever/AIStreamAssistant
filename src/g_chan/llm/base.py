"""LLM provider 抽象层 — 接口、类型、共用解析。"""
from __future__ import annotations

import logging
import re
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

_MOOD_RE = re.compile(
    r"\[mood:(" + "|".join(MOOD_VALUES) + r")\]\s*$"
)


def parse_mood(raw: str) -> tuple[str, Mood]:
    """从 LLM 原始输出尾部抠 [mood:xx] 标签;无/未知标签 → ('原文', 'happy')。"""
    m = _MOOD_RE.search(raw)
    if not m:
        log.warning("LLM did not emit valid mood tag: %r", raw)
        return raw.strip(), "happy"
    return _MOOD_RE.sub("", raw).strip(), m.group(1)  # type: ignore[return-value]


@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMReply:
    text: str          # 已剥掉 [mood:xx]
    mood: Mood
    raw: str           # 原始输出
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
