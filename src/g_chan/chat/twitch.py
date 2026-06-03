"""Twitch IRC chat 适配 — twitchio 包装。"""
from __future__ import annotations

import logging

import twitchio

from g_chan.chat.base import ChatAdapter, ChatHandler, ChatMessage

log = logging.getLogger(__name__)


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
