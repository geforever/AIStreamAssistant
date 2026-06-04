"""WebSocket 客户端连接管理 — 维护连接集合 + 广播。

实装上故意做成 protocol-loose:任何有 `accept` / `send_json` 方法的对象都能用,
这样测试可以用 FakeWS,生产用 FastAPI 的 WebSocket。
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

log = logging.getLogger(__name__)


class _WSLike(Protocol):
    async def accept(self) -> None: ...
    async def send_json(self, payload: Any) -> None: ...


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[_WSLike] = set()

    async def connect(self, ws: _WSLike) -> None:
        await ws.accept()
        self._clients.add(ws)
        log.info("ws client connected, total=%d", len(self._clients))

    def disconnect(self, ws: _WSLike) -> None:
        self._clients.discard(ws)
        log.info("ws client disconnected, total=%d", len(self._clients))

    def client_count(self) -> int:
        return len(self._clients)

    async def broadcast(self, payload: dict) -> None:
        if not self._clients:
            return
        dead: list[_WSLike] = []
        for ws in self._clients:
            try:
                await ws.send_json(payload)
            except Exception as e:  # noqa: BLE001 — 客户端断开/网络异常都视为掉线
                log.debug("ws send failed, dropping client: %s", e)
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)
        if dead:
            log.info("ws clients dropped: %d, remaining=%d",
                     len(dead), len(self._clients))
