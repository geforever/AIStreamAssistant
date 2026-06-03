"""Edge TTS provider — 包 edge_tts。"""
from __future__ import annotations

import asyncio
import logging

import edge_tts

from g_chan.tts.base import (
    TTSAudio,
    TTSEngine,
    TTSServerError,
    TTSTimeoutError,
)

log = logging.getLogger(__name__)


class EdgeTTSEngine(TTSEngine):
    def __init__(self, *, voice: str, rate: str = "+0%", pitch: str = "+0Hz"):
        self._voice = voice
        self._rate = rate
        self._pitch = pitch

    async def synthesize(self, text: str, *, timeout_s: float = 10.0) -> TTSAudio:
        async def _do() -> bytes:
            communicate = edge_tts.Communicate(
                text, self._voice, rate=self._rate, pitch=self._pitch
            )
            buf = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        try:
            data = await asyncio.wait_for(_do(), timeout=timeout_s)
        except asyncio.TimeoutError as e:
            raise TTSTimeoutError(f"Edge TTS timeout after {timeout_s}s") from e
        except Exception as e:  # noqa: BLE001
            raise TTSServerError(f"Edge TTS error: {e}") from e

        return TTSAudio(
            data=data,
            format="mp3",
            voice=self._voice,
            duration_ms=None,
        )
