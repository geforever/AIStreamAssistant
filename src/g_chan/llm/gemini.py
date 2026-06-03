"""Gemini provider — google-genai 适配。"""
from __future__ import annotations

import asyncio
import time

from google import genai

from g_chan.llm.base import (
    LLMMessage,
    LLMProvider,
    LLMReply,
    LLMServerError,
    LLMTimeoutError,
    parse_mood,
)


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(api_key=api_key)
        self._model = model

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
        config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system:
            config["system_instruction"] = system

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
        text, mood = parse_mood(raw)
        usage = getattr(resp, "usage_metadata", None)
        return LLMReply(
            text=text,
            mood=mood,
            raw=raw,
            latency_ms=latency_ms,
            tokens_in=getattr(usage, "prompt_token_count", 0) if usage else 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) if usage else 0,
        )
