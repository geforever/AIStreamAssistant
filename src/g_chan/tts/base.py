"""TTS 抽象层 — 接口、类型、异常。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from g_chan.llm.base import Language


@dataclass
class TTSAudio:
    data: bytes              # 音频字节流
    format: str              # "mp3" / "wav" 等
    voice: str               # 实际使用的 voice 名(便于日志)
    duration_ms: int | None  # 可选,部分引擎不返回


class TTSError(Exception): ...
class TTSTimeoutError(TTSError): ...
class TTSServerError(TTSError): ...


class TTSEngine(ABC):
    @abstractmethod
    async def synthesize(
        self,
        text: str,
        *,
        language: Language = "zh",
        timeout_s: float = 10.0,
    ) -> TTSAudio: ...


class AudioSink(Protocol):
    """音频接收方 — Phase 2 写文件,Phase 3 推 WebSocket。"""
    async def write(self, audio: TTSAudio, *, user: str) -> Path | str: ...
