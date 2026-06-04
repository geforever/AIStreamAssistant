"""Viewer 事件 sink 抽象 — Orchestrator 推 expression / motion / audio 的统一出口。

实现:
- NoopViewerSink: server.enabled=False 时用,所有 push 都是 no-op
- WSViewerSink:  WebSocket 实现,广播给所有连接的 viewer
"""
from __future__ import annotations

from typing import Protocol

from g_chan.tts.base import TTSAudio


class ViewerSink(Protocol):
    """所有 push_* 都 fire-and-forget,任何异常应在实现内吞掉,不能影响 chat 路径。"""

    async def push_expression(self, name: str) -> None: ...

    async def push_motion(self, name: str) -> None: ...

    async def push_audio(self, audio: TTSAudio, *, user: str, text: str) -> None: ...


class NoopViewerSink:
    """server.enabled=False 时用 — 所有 push 不做任何事。"""

    async def push_expression(self, name: str) -> None:
        return

    async def push_motion(self, name: str) -> None:
        return

    async def push_audio(self, audio: TTSAudio, *, user: str, text: str) -> None:
        return
