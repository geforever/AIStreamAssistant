import pytest

from g_chan.llm.base import LLMTimeoutError
from g_chan.orchestrator import Orchestrator
from g_chan.persona.loader import StreamContext
from tests.conftest import FakeAudioSink, FakeChat, FakeLLM, FakeTTS, make_reply


class FixedPersona:
    def __init__(self, ctx: StreamContext | None = None):
        self._ctx = ctx
    def assemble(self, *, stream_ctx):  # noqa: ARG002
        return "你是 G 酱。"


class FixedStreamCtx:
    def __init__(self, ctx: StreamContext | None):
        self._ctx = ctx
    def current(self):
        return self._ctx


# 测试用默认 fallback — 跟生产配置无关,测试只关心"fallback 触发时这个值会被用上"
_FB_TEXT = "FB_TEXT"
_FB_KAOMOJI = "FB_KAOMOJI"
_FB_MOOD = "dizzy"
_FB_KWARGS = {
    "fallback_text": _FB_TEXT,
    "fallback_kaomoji": _FB_KAOMOJI,
    "fallback_mood": _FB_MOOD,
}


@pytest.mark.asyncio
async def test_happy_path_sends_at_reply():
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊~", mood="happy")
    orch = Orchestrator(
        chat=chat,
        llm=llm,
        persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        rate_limit_ms=0,
        busy_reply="...",
    **_FB_KWARGS,
    )
    orch.wire()

    await chat.emit("alice", "嗨")
    assert chat.sent == ["@alice 好啊~"]
    assert len(llm.calls) == 1
    sent_msgs = llm.calls[0]
    assert sent_msgs[0].role == "system"
    assert sent_msgs[-1].role == "user"
    assert "alice" in sent_msgs[-1].content  # 把 user name 也带进去


@pytest.mark.asyncio
async def test_rate_limited_sends_busy_reply():
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("ok", mood="happy")
    orch = Orchestrator(
        chat=chat, llm=llm, persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        rate_limit_ms=60_000,   # 大窗口,第 2 条必拒
        busy_reply="晕XD",
    **_FB_KWARGS,
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    await chat.emit("bob", "嗨")
    assert chat.sent == ["@alice ok", "@bob 晕XD"]
    assert len(llm.calls) == 1   # 只调过一次 LLM


@pytest.mark.asyncio
async def test_llm_failure_uses_configured_fallback():
    """LLM 调用失败 → 用 fallback 三元组拼成 LLMReply,chat 发送 text + kaomoji。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.should_raise = LLMTimeoutError("boom")
    orch = Orchestrator(
        chat=chat, llm=llm, persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        rate_limit_ms=0,
        busy_reply="...",
    **_FB_KWARGS,
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    # chat: fallback_text + fallback_kaomoji 拼接
    assert chat.sent == [f"@alice {_FB_TEXT} {_FB_KAOMOJI}"]


@pytest.mark.asyncio
async def test_passes_stream_context_to_persona(monkeypatch):
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("我在玩原神 [mood:happy]", mood="happy")
    ctx = StreamContext(title="深夜原神", game_name="Genshin Impact")
    persona_called_with = []
    class Spy:
        def assemble(self, *, stream_ctx):
            persona_called_with.append(stream_ctx)
            return "system"
    orch = Orchestrator(
        chat=chat, llm=llm, persona=Spy(),
        stream_ctx=FixedStreamCtx(ctx),
        rate_limit_ms=0,
        busy_reply="...",
    **_FB_KWARGS,
    )
    orch.wire()
    await chat.emit("alice", "在玩啥?")
    assert persona_called_with == [ctx]


@pytest.mark.asyncio
async def test_no_tts_when_engine_not_provided():
    """Phase 1 行为兼容 — 不传 tts/sink 时不应影响 chat 路径。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊~", mood="happy")
    orch = Orchestrator(
        chat=chat, llm=llm, persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        rate_limit_ms=0,
        busy_reply="...",
    **_FB_KWARGS,
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    assert chat.sent == ["@alice 好啊~"]


@pytest.mark.asyncio
async def test_tts_synthesized_and_saved_in_parallel_with_chat():
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("哼,本小姐才不要呢", mood="tsundere")
    tts = FakeTTS()
    sink = FakeAudioSink()
    orch = Orchestrator(
        chat=chat, llm=llm, persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        rate_limit_ms=0,
        busy_reply="...",
        **_FB_KWARGS,
        tts=tts,
        audio_sink=sink,
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    assert chat.sent == ["@alice 哼,本小姐才不要呢"]
    assert tts.calls == ["哼,本小姐才不要呢"]
    assert len(sink.writes) == 1
    audio, user = sink.writes[0]
    assert audio.data == b"FAKEAUDIO"
    assert user == "alice"


@pytest.mark.asyncio
async def test_tts_failure_does_not_block_chat():
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊", mood="happy")
    tts = FakeTTS()
    tts.should_raise = RuntimeError("tts boom")
    sink = FakeAudioSink()
    orch = Orchestrator(
        chat=chat, llm=llm, persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        rate_limit_ms=0,
        busy_reply="...",
        **_FB_KWARGS,
        tts=tts,
        audio_sink=sink,
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    # chat 路径必须完成
    assert chat.sent == ["@alice 好啊"]
    # sink 没被调用(synth 失败)
    assert sink.writes == []


@pytest.mark.asyncio
async def test_sink_failure_does_not_block_chat():
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊", mood="happy")
    tts = FakeTTS()
    sink = FakeAudioSink()
    sink.should_raise = OSError("disk full")
    orch = Orchestrator(
        chat=chat, llm=llm, persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        rate_limit_ms=0,
        busy_reply="...",
        **_FB_KWARGS,
        tts=tts,
        audio_sink=sink,
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    assert chat.sent == ["@alice 好啊"]
    assert tts.calls == ["好啊"]   # synth 成功了
    # sink 写文件失败了,但 chat 路径不受影响


@pytest.mark.asyncio
async def test_llm_failure_still_runs_tts_with_fallback():
    """LLM 失败时也走 TTS 路径 — fallback text 也会被朗读 + 写音频文件。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.should_raise = LLMTimeoutError("llm boom")
    tts = FakeTTS()
    sink = FakeAudioSink()
    orch = Orchestrator(
        chat=chat, llm=llm, persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        rate_limit_ms=0,
        busy_reply="...",
        **_FB_KWARGS,
        tts=tts,
        audio_sink=sink,
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    assert chat.sent == [f"@alice {_FB_TEXT} {_FB_KAOMOJI}"]
    assert tts.calls == [_FB_TEXT]          # TTS 也朗读了 fallback text
    assert len(sink.writes) == 1            # 也写了 mp3 文件


@pytest.mark.asyncio
async def test_chat_send_happens_after_tts_completes():
    """串行: TTS 完成(成功或失败)之后才发 chat,避免文字先到声音晚到的脱节感。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊", mood="happy")
    tts = FakeTTS()
    sink = FakeAudioSink()

    events: list[str] = []
    orig_synth = tts.synthesize
    orig_send = chat.send
    orig_write = sink.write

    async def synth(text, *, timeout_s=10.0):
        events.append("tts_start")
        result = await orig_synth(text, timeout_s=timeout_s)
        events.append("tts_done")
        return result

    async def write(audio, *, user):
        events.append("sink_write")
        return await orig_write(audio, user=user)

    async def send(text):
        events.append("chat_send")
        return await orig_send(text)

    tts.synthesize = synth        # type: ignore[method-assign]
    sink.write = write            # type: ignore[method-assign]
    chat.send = send              # type: ignore[method-assign]

    orch = Orchestrator(
        chat=chat, llm=llm, persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        rate_limit_ms=0,
        busy_reply="...",
        **_FB_KWARGS,
        tts=tts,
        audio_sink=sink,
    )
    orch.wire()
    await chat.emit("alice", "嗨")

    # tts → write → chat 严格顺序
    assert events == ["tts_start", "tts_done", "sink_write", "chat_send"]


@pytest.mark.asyncio
async def test_chat_appends_kaomoji_tts_uses_text_only():
    """正常路径:LLM 分离返回 text + kaomoji,chat 拼接展示,TTS 只用 text。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply(
        "哼,本小姐才没有", mood="tsundere", kaomoji="(›´ω`‹)"
    )
    tts = FakeTTS()
    sink = FakeAudioSink()
    orch = Orchestrator(
        chat=chat, llm=llm, persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        rate_limit_ms=0,
        busy_reply="...",
        **_FB_KWARGS,
        tts=tts,
        audio_sink=sink,
    )
    orch.wire()
    await chat.emit("alice", "嗨")

    # chat: text + kaomoji 拼接
    assert chat.sent == ["@alice 哼,本小姐才没有 (›´ω`‹)"]
    # tts: 只用 text
    assert tts.calls == ["哼,本小姐才没有"]


@pytest.mark.asyncio
async def test_chat_no_trailing_space_when_kaomoji_empty():
    """kaomoji 为空时,chat 不应有多余空格。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好的,知道了", mood="happy", kaomoji="")
    orch = Orchestrator(
        chat=chat, llm=llm, persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        rate_limit_ms=0,
        busy_reply="...",
    **_FB_KWARGS,
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    assert chat.sent == ["@alice 好的,知道了"]


@pytest.mark.asyncio
async def test_tts_skipped_when_text_is_blank():
    """text 全空白时跳过 TTS — 边界情况,chat 仍发送(可能只有 kaomoji)。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("   ", mood="happy", kaomoji="(=ω=)")
    tts = FakeTTS()
    sink = FakeAudioSink()
    orch = Orchestrator(
        chat=chat, llm=llm, persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        rate_limit_ms=0,
        busy_reply="...",
        **_FB_KWARGS,
        tts=tts,
        audio_sink=sink,
    )
    orch.wire()
    await chat.emit("alice", "嗨")

    assert tts.calls == []        # 没调 synth
    assert sink.writes == []      # 也没写文件
    assert len(chat.sent) == 1    # chat 还是发了
