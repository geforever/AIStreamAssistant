"""Gemini provider — google-genai 适配,使用 JSON mode + responseSchema 约束输出。"""
from __future__ import annotations

import asyncio
import time

from google import genai
from google.genai import types

from g_chan.llm.base import (
    Language,
    LLMMessage,
    LLMProvider,
    LLMReply,
    LLMServerError,
    LLMTimeoutError,
    Mood,
    parse_llm_json,
)


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        schema: dict,
        fallback_text: str,
        fallback_kaomoji: str,
        fallback_mood: Mood,
        fallback_language: Language,
        fallback_expression: str = "",
        fallback_motion: str = "",
        available_expressions: list[str] | None = None,
        available_motions: list[str] | None = None,
    ):
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._schema = schema
        self._fallback_text = fallback_text
        self._fallback_kaomoji = fallback_kaomoji
        self._fallback_mood = fallback_mood
        self._fallback_language = fallback_language
        self._fallback_expression = fallback_expression
        self._fallback_motion = fallback_motion
        self._available_expressions = available_expressions or []
        self._available_motions = available_motions or []

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
        config = types.GenerateContentConfig(
            temperature=temperature,
            maxOutputTokens=max_tokens,
            responseMimeType="application/json",
            responseSchema=self._schema,
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
        text, kaomoji, mood, language, expression, motion = parse_llm_json(
            raw,
            fallback_text=self._fallback_text,
            fallback_kaomoji=self._fallback_kaomoji,
            fallback_mood=self._fallback_mood,
            fallback_language=self._fallback_language,
            fallback_expression=self._fallback_expression,
            fallback_motion=self._fallback_motion,
            available_expressions=self._available_expressions,
            available_motions=self._available_motions,
        )
        usage = getattr(resp, "usage_metadata", None)
        return LLMReply(
            text=text,
            kaomoji=kaomoji,
            mood=mood,
            language=language,
            expression=expression,
            motion=motion,
            raw=raw,
            latency_ms=latency_ms,
            tokens_in=getattr(usage, "prompt_token_count", 0) if usage else 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) if usage else 0,
        )
