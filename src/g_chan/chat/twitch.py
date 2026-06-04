"""Twitch IRC chat 适配 — twitchio 包装。"""
from __future__ import annotations

import logging

import twitchio

from g_chan.chat.base import ChatAdapter, ChatHandler, ChatMessage

log = logging.getLogger(__name__)


def _is_priority(author: object) -> bool:
    """检测发言者是否走即时路径 — mod / broadcaster / vip。"""
    if author is None:
        return False
    # twitchio v2 Chatter 暴露这些 bool
    if getattr(author, "is_mod", False):
        return True
    if getattr(author, "is_broadcaster", False):
        return True
    # 部分 twitchio 版本暴露 is_vip
    if getattr(author, "is_vip", False):
        return True
    # 兜底:badges 字典
    badges = getattr(author, "badges", None) or {}
    if isinstance(badges, dict) and "vip" in badges:
        return True
    return False


class TwitchChatAdapter(ChatAdapter):
    def __init__(
        self,
        *,
        channel: str,
        bot_username: str,
        oauth_token: str,
        trigger: str,
    ):
        self._channel = channel
        self._bot_username = bot_username
        self._trigger = trigger
        self._handler: ChatHandler | None = None
        self._client = twitchio.Client(
            token=oauth_token,
            initial_channels=[channel],
        )
        self._setup_events()

    def _setup_events(self) -> None:
        @self._client.event()
        async def event_ready():  # noqa: ARG001
            log.info("twitch chat connected as %s in #%s",
                     self._bot_username, self._channel)

        @self._client.event()
        async def event_message(message: twitchio.Message):
            if message.echo:  # 自己发的
                return
            body = (message.content or "").strip()
            if not body.startswith(self._trigger):
                return
            if self._handler is None:
                log.debug("no handler registered, dropping message")
                return
            stripped = body[len(self._trigger):].strip()
            msg = ChatMessage(
                user=message.author.name if message.author else "unknown",
                body=stripped,
                raw=body,
                is_priority=_is_priority(message.author),
            )
            try:
                await self._handler(msg)
            except Exception:  # noqa: BLE001
                log.exception("chat handler raised")

    def on_trigger(self, handler: ChatHandler) -> None:
        self._handler = handler

    async def connect(self) -> None:
        # twitchio v2: start() 是阻塞的 — 建连接后驻留事件循环直到 close()/disconnect
        await self._client.start()

    async def disconnect(self) -> None:
        await self._client.close()

    async def send(self, text: str) -> None:
        chan = self._client.get_channel(self._channel)
        if chan is None:
            log.warning("channel #%s not joined yet, dropping send", self._channel)
            return
        await chan.send(text)
