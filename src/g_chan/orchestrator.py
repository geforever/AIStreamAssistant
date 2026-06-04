"""Orchestrator — VIP 即时路径 + 普通観众批处理路径。

VIP 路径(mod/broadcaster/vip):
- 走 vip_window_ms 限流(0 = 无限流)
- 立即 spawn 独立 task,LLM → TTS → chat 发 "@user 内容 颜文字"
- 跟 batch 路径完全并发(不互相阻塞)

普通観众路径:
- @ 进入 MessageBuffer(per-user dedup,LRU,max buffer_size)
- 第一条 @ 触发 first_at 标记并启动 scheduled_flush task
- scheduled_flush 等到 first_at + batch_window_s 时 flush 给 LLM
- LLM 在 batch prompt 下挑 1 条(或合并多条 / 沉默)输出
- chat 发 "内容 颜文字"(无 @user)
- cooldown(batch_cooldown_ms)从 flush 开始计时,期间普通 @ 全部 silent drop
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Protocol

from g_chan.chat.base import ChatAdapter, ChatMessage
from g_chan.interaction.buffer import MessageBuffer
from g_chan.llm.base import Language, LLMError, LLMMessage, LLMProvider, LLMReply, Mood
from g_chan.persona.loader import StreamContext
from g_chan.prompts import build_batch_user_message
from g_chan.rate_limiter import RateLimiter
from g_chan.tts.base import AudioSink, TTSEngine, TTSError

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
        # interaction config
        vip_window_ms: int,
        batch_window_s: float,
        batch_cooldown_ms: int,
        buffer_size: int,
        # fallback config
        fallback_text: str,
        fallback_kaomoji: str,
        fallback_mood: Mood,
        fallback_language: Language,
        # optional
        tts: TTSEngine | None = None,
        audio_sink: AudioSink | None = None,
        now_ms=_default_now_ms,
    ):
        self._chat = chat
        self._llm = llm
        self._persona = persona
        self._stream_ctx = stream_ctx
        self._vip_rl = RateLimiter(window_ms=vip_window_ms, now_ms=now_ms)
        self._batch_window_s = batch_window_s
        self._batch_cooldown_ms = batch_cooldown_ms
        self._buffer = MessageBuffer(max_size=buffer_size)
        # 用于 prompt 截取:0 = 不限,实际用大数代替
        self._prompt_max = buffer_size if buffer_size > 0 else 1_000_000
        self._fallback_text = fallback_text
        self._fallback_kaomoji = fallback_kaomoji
        self._fallback_mood = fallback_mood
        self._fallback_language = fallback_language
        self._tts = tts
        self._audio_sink = audio_sink
        self._now_ms = now_ms
        # batch 状态
        self._last_batch_started_at_ms: float = -float("inf")
        self._batch_in_flight: bool = False

    def wire(self) -> None:
        """挂上 chat 触发回调。"""
        self._chat.on_trigger(self._on_trigger)

    async def _on_trigger(self, msg: ChatMessage) -> None:
        log.info("trigger: user=%s priority=%s body=%r",
                 msg.user, msg.is_priority, msg.body)
        if msg.is_priority:
            # VIP 路径:独立 task,跟 batch 完全并发
            asyncio.create_task(self._handle_priority(msg))
        else:
            await self._handle_regular(msg)

    # --------------------- VIP / Mod / Broadcaster ---------------------

    async def _handle_priority(self, msg: ChatMessage) -> None:
        if not self._vip_rl.try_acquire():
            log.info("vip rate-limited, drop: user=%s", msg.user)
            return

        try:
            reply = await self._llm.generate(self._build_single_messages(msg))
        except LLMError as e:
            log.warning("vip llm failed: %s — using fallback", e)
            reply = self._fallback_reply()

        log.info("vip reply: user=%s mood=%s lang=%s text=%r kaomoji=%r",
                 msg.user, reply.mood, reply.language, reply.text, reply.kaomoji)

        # 串行: TTS 完成后才发 chat
        await self._do_tts(reply.text, language=reply.language, user=msg.user)
        chat_body = (
            f"{reply.text} {reply.kaomoji}".strip() if reply.kaomoji else reply.text
        )
        await self._chat.send(f"@{msg.user} {chat_body}")

    # --------------------- 普通観众 ---------------------

    async def _handle_regular(self, msg: ChatMessage) -> None:
        # batch_window_s=0 → 普通路径完全禁用
        if self._batch_window_s <= 0:
            log.debug("batch path disabled (batch_window_s=0), drop regular")
            return

        now = self._now_ms()

        # cooldown: 距上次 flush 开始 < batch_cooldown_ms → silent drop
        if now - self._last_batch_started_at_ms < self._batch_cooldown_ms:
            log.debug("regular @ during cooldown, drop: user=%s", msg.user)
            return

        # 处理中 → silent drop
        if self._batch_in_flight:
            log.debug("regular @ during batch in-flight, drop: user=%s", msg.user)
            return

        # 加入 buffer。如果是空 buffer 的第一条,触发 scheduled_flush
        was_empty = self._buffer.is_empty()
        self._buffer.add(msg, now_ms=now)
        if was_empty:
            asyncio.create_task(self._scheduled_flush())

    async def _scheduled_flush(self) -> None:
        """在 first_at + batch_window_s 时 flush buffer。"""
        first_at = self._buffer.first_at_ms()
        if first_at is None:
            return  # 防御:已被清空

        # 计算还要等多久
        now = self._now_ms()
        elapsed_ms = now - first_at
        target_ms = self._batch_window_s * 1000
        sleep_s = max(0.0, (target_ms - elapsed_ms) / 1000)
        if sleep_s > 0:
            await asyncio.sleep(sleep_s)

        # 重新检查:buffer 可能已被 clear,或已有别人在 flush
        if self._buffer.is_empty():
            return
        if self._batch_in_flight:
            return

        # 启动 flush
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

        # 沉默:不发 chat 不调 TTS
        if not reply.text.strip():
            log.info("batch result: silence (batch_size=%d)", len(messages))
            return

        log.info("batch reply: batch_size=%d mood=%s lang=%s text=%r kaomoji=%r",
                 len(messages), reply.mood, reply.language, reply.text, reply.kaomoji)

        # batch 回复用 "batch" 作为 sink 的 user 标识
        await self._do_tts(reply.text, language=reply.language, user="batch")
        chat_body = (
            f"{reply.text} {reply.kaomoji}".strip() if reply.kaomoji else reply.text
        )
        await self._chat.send(chat_body)  # 注意:无 @user

    # --------------------- 共用 ---------------------

    async def _do_tts(self, text: str, *, language: Language, user: str) -> None:
        if self._tts is None or self._audio_sink is None:
            return
        if not text.strip():
            log.info("tts text is empty, skipping synthesis")
            return
        try:
            audio = await self._tts.synthesize(text, language=language)
        except TTSError as e:
            log.warning("tts synth failed: %s", e)
            return
        except Exception as e:  # noqa: BLE001
            log.exception("tts synth crashed unexpectedly: %s", e)
            return
        try:
            await self._audio_sink.write(audio, user=user)
        except Exception as e:  # noqa: BLE001
            log.warning("audio sink write failed: %s", e)

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
