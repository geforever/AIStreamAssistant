"""Gemini provider — google-genai 适配,使用 JSON mode + responseSchema 约束输出。"""
from __future__ import annotations

import asyncio
import time

from google import genai
from google.genai import types

from g_chan.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMReply,
    LLMServerError,
    LLMTimeoutError,
    Mood,
    parse_llm_json,
)
from g_chan.llm.schemas import CHAT_REPLY_SCHEMA


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        fallback_text: str,
        fallback_kaomoji: str,
        fallback_mood: Mood,
    ):
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._fallback_text = fallback_text
        self._fallback_kaomoji = fallback_kaomoji
        self._fallback_mood = fallback_mood

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.9,
        max_tokens: int = 300,
        timeout_s: float = 10.0,
    ) -> LLMReply:
        system = next((m.content for m in messages if m.role == "system"), None)
        contents = [
            {"role": "user" if m.role == "user" else "model",
             "parts": [{"text": m.content}]}
            for m in messages if m.role != "system"
        ]
        # google-genai 字段名是 camelCase。用显式 GenerateContentConfig 避免 dict 写法被忽略
        # thinkingBudget=0 关闭 2.5 系列默认的内部推理 — 短聊场景不需要,
        # 关掉可节省 token + 降低延迟,也避免 JSON 输出被 thinking 占用 token 截断
        config = types.GenerateContentConfig(
            temperature=temperature,
            maxOutputTokens=max_tokens,
            responseMimeType="application/json",
            responseSchema=CHAT_REPLY_SCHEMA,
            systemInstruction=system,
            thinkingConfig=types.ThinkingConfig(thinkingBudget=0),
        )

        t0 = time.monotonic()
        try:
            resp = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                ),
                timeout=timeout_s,
            )
        except TimeoutError as e:
            raise LLMTimeoutError(f"Gemini timeout after {timeout_s}s") from e
        except Exception as e:  # noqa: BLE001
            raise LLMServerError(f"Gemini error: {e}") from e
        latency_ms = int((time.monotonic() - t0) * 1000)

        raw = resp.text or ""
        text, kaomoji, mood = parse_llm_json(
            raw,
            fallback_text=self._fallback_text,
            fallback_kaomoji=self._fallback_kaomoji,
            fallback_mood=self._fallback_mood,
        )
        usage = getattr(resp, "usage_metadata", None)
        return LLMReply(
            text=text,
            kaomoji=kaomoji,
            mood=mood,
            raw=raw,
            latency_ms=latency_ms,
            tokens_in=getattr(usage, "prompt_token_count", 0) if usage else 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) if usage else 0,
        )
