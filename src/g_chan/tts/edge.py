"""Edge TTS provider — 包 edge_tts,支持多语言 voice 映射。"""
from __future__ import annotations

import asyncio
import logging

import edge_tts

from g_chan.llm.base import Language
from g_chan.tts.base import (
    TTSAudio,
    TTSEngine,
    TTSServerError,
    TTSTimeoutError,
)

log = logging.getLogger(__name__)


class EdgeTTSEngine(TTSEngine):
    def __init__(
        self,
        *,
        voices: dict[Language, str],
        rate: str = "+0%",
        pitch: str = "+0Hz",
    ):
        if not voices:
            raise ValueError("EdgeTTSEngine requires at least one voice mapping")
        self._voices = voices
        self._rate = rate
        self._pitch = pitch

    def _pick_voice(self, language: Language) -> str:
        voice = self._voices.get(language)
        if voice is None:
            # 配置里没这个语言的 voice → 退到 dict 第一个可用的
            fallback_lang, fallback_voice = next(iter(self._voices.items()))
            log.warning(
                "no voice configured for language=%s, falling back to %s (%s)",
                language, fallback_lang, fallback_voice,
            )
            return fallback_voice
        return voice

    async def synthesize(
        self,
        text: str,
        *,
        language: Language = "zh",
        timeout_s: float = 10.0,
    ) -> TTSAudio:
        voice = self._pick_voice(language)

        async def _do() -> bytes:
            communicate = edge_tts.Communicate(
                text, voice, rate=self._rate, pitch=self._pitch
            )
            buf = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        try:
            data = await asyncio.wait_for(_do(), timeout=timeout_s)
        except TimeoutError as e:
            raise TTSTimeoutError(f"Edge TTS timeout after {timeout_s}s") from e
        except Exception as e:  # noqa: BLE001
            raise TTSServerError(f"Edge TTS error: {e}") from e

        return TTSAudio(
            data=data,
            format="mp3",
            voice=voice,
            duration_ms=None,
        )
