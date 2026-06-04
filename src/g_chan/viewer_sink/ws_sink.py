"""WebSocket 実装の ViewerSink — ConnectionManager 経由で全接続 viewer にブロードキャスト。"""
from __future__ import annotations

import base64
import logging
from typing import Protocol

from g_chan.tts.base import TTSAudio

log = logging.getLogger(__name__)


class _CMLike(Protocol):
    async def broadcast(self, payload: dict) -> None: ...


def _name_or_none(name: str) -> str:
    """空字符串规范化为 'None' — viewer 协议显式表达"维持当前"。"""
    return name if name else "None"


class WSViewerSink:
    def __init__(self, connection_manager: _CMLike):
        self._cm = connection_manager

    async def push_expression(self, name: str) -> None:
        try:
            await self._cm.broadcast({"type": "expression", "name": _name_or_none(name)})
        except Exception as e:  # noqa: BLE001
            log.warning("WSViewerSink push_expression failed: %s", e)

    async def push_motion(self, name: str) -> None:
        try:
            await self._cm.broadcast({"type": "motion", "name": _name_or_none(name)})
        except Exception as e:  # noqa: BLE001
            log.warning("WSViewerSink push_motion failed: %s", e)

    async def push_audio(self, audio: TTSAudio, *, user: str, text: str) -> None:
        try:
            await self._cm.broadcast({
                "type": "speak",
                "audio": base64.b64encode(audio.data).decode("ascii"),
                "format": audio.format,
                "text": text,
            })
        except Exception as e:  # noqa: BLE001
            log.warning("WSViewerSink push_audio failed (user=%s): %s", user, e)
