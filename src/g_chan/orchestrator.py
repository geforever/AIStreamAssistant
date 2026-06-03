"""Orchestrator — 把 chat / persona / llm / rate_limit / tts 串成一条对话路径。"""
from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from g_chan.chat.base import ChatAdapter, ChatMessage
from g_chan.llm.base import LLMError, LLMMessage, LLMProvider
from g_chan.persona.loader import StreamContext
from g_chan.rate_limiter import RateLimiter
from g_chan.tts.base import AudioSink, TTSEngine, TTSError

log = logging.getLogger(__name__)


class PersonaLike(Protocol):
    def assemble(self, *, stream_ctx: StreamContext | None) -> str: ...


class StreamCtxLike(Protocol):
    def current(self) -> StreamContext | None: ...


_FALLBACK_TEXT = "诶呀脑子卡了一下,你再说一遍?"


class Orchestrator:
    def __init__(
        self,
        *,
        chat: ChatAdapter,
        llm: LLMProvider,
        persona: PersonaLike,
        stream_ctx: StreamCtxLike,
        rate_limit_ms: int,
        busy_reply: str,
        tts: TTSEngine | None = None,
        audio_sink: AudioSink | None = None,
    ):
        self._chat = chat
        self._llm = llm
        self._persona = persona
        self._stream_ctx = stream_ctx
        self._rl = RateLimiter(window_ms=rate_limit_ms)
        self._busy_reply = busy_reply
        self._tts = tts
        self._audio_sink = audio_sink

    def wire(self) -> None:
        """挂上 chat 触发回调。"""
        self._chat.on_trigger(self._handle)

    async def _handle(self, msg: ChatMessage) -> None:
        log.info("trigger: user=%s body=%r", msg.user, msg.body)

        if not self._rl.try_acquire():
            await self._chat.send(f"@{msg.user} {self._busy_reply}")
            return

        try:
            reply = await self._llm.generate(self._build_messages(msg))
        except LLMError as e:
            log.warning("llm failed: %s", e)
            await self._chat.send(f"@{msg.user} {_FALLBACK_TEXT}")
            return

        log.info(
            "reply: mood=%s latency=%dms tokens=%d/%d text=%r",
            reply.mood, reply.latency_ms, reply.tokens_in, reply.tokens_out,
            reply.text,
        )

        # 并行: chat 文本 + TTS 合成保存。任一异常不影响另一条。
        # _do_tts 内部已 catch 所有异常,所以 gather 不会因 TTS 抛
        chat_task = self._chat.send(f"@{msg.user} {reply.text}")
        tts_task = self._do_tts(reply.text, user=msg.user)
        await asyncio.gather(chat_task, tts_task)

    async def _do_tts(self, text: str, *, user: str) -> None:
        if self._tts is None or self._audio_sink is None:
            return
        try:
            audio = await self._tts.synthesize(text)
        except TTSError as e:
            log.warning("tts synth failed: %s", e)
            return
        except Exception as e:  # noqa: BLE001 — 任何意外也吞,不能影响 chat
            log.exception("tts synth crashed unexpectedly: %s", e)
            return
        try:
            await self._audio_sink.write(audio, user=user)
        except Exception as e:  # noqa: BLE001
            log.warning("audio sink write failed: %s", e)

    def _build_messages(self, msg: ChatMessage) -> list[LLMMessage]:
        system = self._persona.assemble(stream_ctx=self._stream_ctx.current())
        return [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=f"{msg.user}: {msg.body}"),
        ]
