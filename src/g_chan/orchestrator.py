"""Orchestrator — VIP 即时路径 + 普通观众批处理路径 + Live2D 频率裁剪。"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Callable
from typing import Protocol

from g_chan.chat.base import ChatAdapter, ChatMessage
from g_chan.interaction.buffer import MessageBuffer
from g_chan.llm.base import Language, LLMError, LLMMessage, LLMProvider, LLMReply, Mood
from g_chan.persona.loader import StreamContext
from g_chan.prompts import build_batch_user_message
from g_chan.rate_limiter import RateLimiter
from g_chan.tts.base import AudioSink, TTSEngine, TTSError
from g_chan.viewer_sink import NoopViewerSink, ViewerSink

log = logging.getLogger(__name__)


class PersonaLike(Protocol):
    def assemble(self, *, stream_ctx: StreamContext | None) -> str: ...


class StreamCtxLike(Protocol):
    def current(self) -> StreamContext | None: ...


def _default_now_ms() -> float:
    return time.monotonic() * 1000


class Orchestrator:
    def __init__(
        self,
        *,
        chat: ChatAdapter,
        llm: LLMProvider,
        persona: PersonaLike,
        stream_ctx: StreamCtxLike,
        vip_window_ms: int,
        batch_window_s: float,
        batch_cooldown_ms: int,
        buffer_size: int,
        fallback_text: str,
        fallback_kaomoji: str,
        fallback_mood: Mood,
        fallback_language: Language,
        # Phase 2.6 新增
        default_expression: str = "",
        default_motion: str = "",
        expression_change_frequency: float = 1.0,
        motion_change_frequency: float = 1.0,
        tts: TTSEngine | None = None,
        audio_sink: AudioSink | None = None,
        viewer_sink: ViewerSink | None = None,
        now_ms: Callable[[], float] = _default_now_ms,
        random_fn: Callable[[], float] = random.random,
    ):
        self._chat = chat
        self._llm = llm
        self._persona = persona
        self._stream_ctx = stream_ctx
        self._vip_rl = RateLimiter(window_ms=vip_window_ms, now_ms=now_ms)
        self._batch_window_s = batch_window_s
        self._batch_cooldown_ms = batch_cooldown_ms
        self._buffer = MessageBuffer(max_size=buffer_size)
        self._prompt_max = buffer_size if buffer_size > 0 else 1_000_000
        self._fallback_text = fallback_text
        self._fallback_kaomoji = fallback_kaomoji
        self._fallback_mood = fallback_mood
        self._fallback_language = fallback_language
        self._default_expression = default_expression
        self._default_motion = default_motion
        self._expression_change_frequency = expression_change_frequency
        self._motion_change_frequency = motion_change_frequency
        self._tts = tts
        self._audio_sink = audio_sink
        self._viewer_sink: ViewerSink = viewer_sink or NoopViewerSink()
        self._now_ms = now_ms
        self._random_fn = random_fn
        self._last_batch_started_at_ms: float = -float("inf")
        self._batch_in_flight: bool = False

    def wire(self) -> None:
        self._chat.on_trigger(self._on_trigger)

    async def _on_trigger(self, msg: ChatMessage) -> None:
        log.info("trigger: user=%s priority=%s body=%r",
                 msg.user, msg.is_priority, msg.body)
        if msg.is_priority:
            asyncio.create_task(self._handle_priority(msg))
        else:
            await self._handle_regular(msg)

    # --------------------- VIP ---------------------

    async def _handle_priority(self, msg: ChatMessage) -> None:
        if not self._vip_rl.try_acquire():
            log.info("vip rate-limited, drop: user=%s", msg.user)
            return

        try:
            reply = await self._llm.generate(self._build_single_messages(msg))
        except LLMError as e:
            log.warning("vip llm failed: %s — using fallback", e)
            reply = self._fallback_reply()

        expression, motion = self._apply_frequency(reply)
        log.info(
            "vip reply: user=%s mood=%s lang=%s text=%r kaomoji=%r expr=%r motion=%r",
            msg.user, reply.mood, reply.language, reply.text, reply.kaomoji,
            expression, motion,
        )

        # 先合成音频(慢),再几乎同时推 expression/motion/audio + 发 chat
        # → viewer 端看到的表情切换、嘴动、聊天消息时间几乎一致
        audio = await self._synthesize_audio(reply.text, language=reply.language)
        await self._viewer_sink.push_expression(expression)
        await self._viewer_sink.push_motion(motion)
        if audio is not None:
            await self._emit_audio(audio, user=msg.user, text=reply.text)
        chat_body = (
            f"{reply.text} {reply.kaomoji}".strip() if reply.kaomoji else reply.text
        )
        await self._chat.send(f"@{msg.user} {chat_body}")

    # --------------------- 普通观众 ---------------------

    async def _handle_regular(self, msg: ChatMessage) -> None:
        if self._batch_window_s <= 0:
            log.debug("batch path disabled, drop regular")
            return

        now = self._now_ms()
        if now - self._last_batch_started_at_ms < self._batch_cooldown_ms:
            log.debug("regular @ during cooldown, drop: user=%s", msg.user)
            return
        if self._batch_in_flight:
            log.debug("regular @ during batch in-flight, drop: user=%s", msg.user)
            return

        was_empty = self._buffer.is_empty()
        self._buffer.add(msg, now_ms=now)
        if was_empty:
            asyncio.create_task(self._scheduled_flush())

    async def _scheduled_flush(self) -> None:
        first_at = self._buffer.first_at_ms()
        if first_at is None:
            return
        now = self._now_ms()
        elapsed_ms = now - first_at
        target_ms = self._batch_window_s * 1000
        sleep_s = max(0.0, (target_ms - elapsed_ms) / 1000)
        if sleep_s > 0:
            await asyncio.sleep(sleep_s)

        if self._buffer.is_empty() or self._batch_in_flight:
            return

        self._batch_in_flight = True
        self._last_batch_started_at_ms = self._now_ms()
        try:
            messages = self._buffer.latest_n(self._prompt_max)
            self._buffer.clear()
            await self._process_batch(messages)
        finally:
            self._batch_in_flight = False

    async def _process_batch(self, messages: list[ChatMessage]) -> None:
        try:
            reply = await self._llm.generate(self._build_batch_messages(messages))
        except LLMError as e:
            log.warning("batch llm failed: %s — using fallback", e)
            reply = self._fallback_reply()

        if not reply.text.strip():
            log.info("batch result: silence (batch_size=%d)", len(messages))
            return

        expression, motion = self._apply_frequency(reply)
        log.info(
            "batch reply: batch_size=%d mood=%s lang=%s text=%r kaomoji=%r expr=%r motion=%r",
            len(messages), reply.mood, reply.language, reply.text, reply.kaomoji,
            expression, motion,
        )

        audio = await self._synthesize_audio(reply.text, language=reply.language)
        await self._viewer_sink.push_expression(expression)
        await self._viewer_sink.push_motion(motion)
        if audio is not None:
            await self._emit_audio(audio, user="batch", text=reply.text)
        chat_body = (
            f"{reply.text} {reply.kaomoji}".strip() if reply.kaomoji else reply.text
        )
        await self._chat.send(chat_body)

    # --------------------- 共用 ---------------------

    def _apply_frequency(self, reply: LLMReply) -> tuple[str, str]:
        """根据 frequency 决定用 LLM 选的还是 default。

        random_fn() < frequency  → 用 LLM 选的
        random_fn() >= frequency → 用 default(包括沉默 "")
        """
        if self._random_fn() < self._expression_change_frequency:
            expression = reply.expression
        else:
            expression = self._default_expression
        if self._random_fn() < self._motion_change_frequency:
            motion = reply.motion
        else:
            motion = self._default_motion
        return expression, motion

    async def _synthesize_audio(self, text: str, *, language: Language):
        """合成音频但不写出 / 不推送 — 让 caller 决定推送时机。

        text 为空或 TTS 未启用 / 失败时返回 None。
        """
        if self._tts is None or not text.strip():
            return None
        try:
            return await self._tts.synthesize(text, language=language)
        except TTSError as e:
            log.warning("tts synth failed: %s", e)
            return None
        except Exception as e:  # noqa: BLE001
            log.exception("tts synth crashed: %s", e)
            return None

    async def _emit_audio(self, audio, *, user: str, text: str) -> None:
        """合成好的音频:写文件 sink(可选)+ 推 viewer。"""
        if self._audio_sink is not None:
            try:
                await self._audio_sink.write(audio, user=user)
            except Exception as e:  # noqa: BLE001
                log.warning("audio sink write failed: %s", e)
        await self._viewer_sink.push_audio(audio, user=user, text=text)

    def _fallback_reply(self) -> LLMReply:
        return LLMReply(
            text=self._fallback_text,
            kaomoji=self._fallback_kaomoji,
            mood=self._fallback_mood,
            language=self._fallback_language,
            raw="",
            latency_ms=0,
            tokens_in=0,
            tokens_out=0,
            expression=self._default_expression,
            motion=self._default_motion,
        )

    def _build_single_messages(self, msg: ChatMessage) -> list[LLMMessage]:
        system = self._persona.assemble(stream_ctx=self._stream_ctx.current())
        return [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=f"{msg.user}: {msg.body}"),
        ]

    def _build_batch_messages(self, messages: list[ChatMessage]) -> list[LLMMessage]:
        system = self._persona.assemble(stream_ctx=self._stream_ctx.current())
        return [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=build_batch_user_message(messages)),
        ]
