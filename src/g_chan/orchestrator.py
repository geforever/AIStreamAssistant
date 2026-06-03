"""Orchestrator — 把 chat / persona / llm / rate_limit / tts 串成一条对话路径。"""
from __future__ import annotations

import logging
from typing import Protocol

from g_chan.chat.base import ChatAdapter, ChatMessage
from g_chan.llm.base import LLMError, LLMMessage, LLMProvider, LLMReply, Mood
from g_chan.persona.loader import StreamContext
from g_chan.rate_limiter import RateLimiter
from g_chan.tts.base import AudioSink, TTSEngine, TTSError

log = logging.getLogger(__name__)


class PersonaLike(Protocol):
    def assemble(self, *, stream_ctx: StreamContext | None) -> str: ...


class StreamCtxLike(Protocol):
    def current(self) -> StreamContext | None: ...


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
        fallback_text: str,
        fallback_kaomoji: str,
        fallback_mood: Mood,
        tts: TTSEngine | None = None,
        audio_sink: AudioSink | None = None,
    ):
        self._chat = chat
        self._llm = llm
        self._persona = persona
        self._stream_ctx = stream_ctx
        self._rl = RateLimiter(window_ms=rate_limit_ms)
        self._busy_reply = busy_reply
        self._fallback_text = fallback_text
        self._fallback_kaomoji = fallback_kaomoji
        self._fallback_mood = fallback_mood
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
            # LLM 调用本身失败(超时、网络、5xx)→ 构造 fallback LLMReply 走完整路径。
            # 这样 fallback 路径也有 TTS 和 mood,跟"LLM 返回了 bad JSON"的回退体验一致。
            log.warning("llm failed: %s — using fallback reply", e)
            reply = LLMReply(
                text=self._fallback_text,
                kaomoji=self._fallback_kaomoji,
                mood=self._fallback_mood,
                raw="",
                latency_ms=0,
                tokens_in=0,
                tokens_out=0,
            )

        log.info(
            "reply: mood=%s latency=%dms tokens=%d/%d text=%r kaomoji=%r",
            reply.mood, reply.latency_ms, reply.tokens_in, reply.tokens_out,
            reply.text, reply.kaomoji,
        )

        # 串行: 先 TTS(只用 text,不含颜文字),完成后再发 chat(text + kaomoji 拼接)。
        # 目的:让观众看到文字的同时听到声音,不会出现"文字先到、声音晚 1s"的脱节感。
        # TTS 任何异常都被 _do_tts 内部吞,不影响 chat 路径。
        await self._do_tts(reply.text, user=msg.user)
        chat_body = f"{reply.text} {reply.kaomoji}".strip() if reply.kaomoji else reply.text
        await self._chat.send(f"@{msg.user} {chat_body}")

    async def _do_tts(self, text: str, *, user: str) -> None:
        if self._tts is None or self._audio_sink is None:
            return
        if not text.strip():
            log.info("tts text is empty, skipping synthesis")
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
