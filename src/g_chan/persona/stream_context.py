"""直播频道上下文 — 后台轮询 Helix,缓存 title/game。"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

from g_chan.persona.loader import StreamContext

log = logging.getLogger(__name__)


class HelixClient(ABC):
    @abstractmethod
    async def fetch_channel(self, channel: str) -> StreamContext: ...


class StreamContextProvider:
    """周期性拉取频道信息,缓存最近一次成功结果。"""

    def __init__(self, channel: str, helix: HelixClient):
        self._channel = channel
        self._helix = helix
        self._cached: StreamContext | None = None
        self._task: asyncio.Task | None = None

    def current(self) -> StreamContext | None:
        return self._cached

    async def refresh(self) -> None:
        try:
            self._cached = await self._helix.fetch_channel(self._channel)
        except Exception as e:  # noqa: BLE001
            log.warning("StreamContext refresh failed: %s (using last cached: %r)",
                        e, self._cached)

    async def start_polling(self, interval_ms: int) -> None:
        """阻塞地按 interval 不断刷新;意在用 asyncio.create_task 包起来。"""
        await self.refresh()
        while True:
            await asyncio.sleep(interval_ms / 1000)
            await self.refresh()


class TwitchHelixClient(HelixClient):
    """twitchAPI 包装。需要 App Access Token(Client Credentials)。"""

    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._api = None  # 懒加载

    async def _ensure(self):
        if self._api is None:
            from twitchAPI.twitch import Twitch
            self._api = await Twitch(self._client_id, self._client_secret)
        return self._api

    async def fetch_channel(self, channel: str) -> StreamContext:
        api = await self._ensure()
        # 1) channel login → user_id
        users = []
        async for u in api.get_users(logins=[channel]):
            users.append(u)
        if not users:
            raise RuntimeError(f"twitch channel not found: {channel}")
        user_id = users[0].id
        # 2) channel info
        infos = []
        async for c in api.get_channel_information(broadcaster_id=user_id):
            infos.append(c)
        if not infos:
            raise RuntimeError(f"no channel info for {channel}")
        info = infos[0]
        return StreamContext(title=info.title or "", game_name=info.game_name or "")
