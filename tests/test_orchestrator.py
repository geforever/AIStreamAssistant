import pytest

from g_chan.llm.base import LLMTimeoutError
from g_chan.orchestrator import Orchestrator
from g_chan.persona.loader import StreamContext
from tests.conftest import FakeChat, FakeLLM, make_reply


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
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    await chat.emit("bob", "嗨")
    assert chat.sent == ["@alice ok", "@bob 晕XD"]
    assert len(llm.calls) == 1   # 只调过一次 LLM


@pytest.mark.asyncio
async def test_llm_failure_falls_back():
    chat = FakeChat()
    llm = FakeLLM()
    llm.should_raise = LLMTimeoutError("boom")
    orch = Orchestrator(
        chat=chat, llm=llm, persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        rate_limit_ms=0,
        busy_reply="...",
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    assert len(chat.sent) == 1
    msg = chat.sent[0]
    assert msg.startswith("@alice ")
    assert "卡了一下" in msg or "脑子" in msg  # fallback 文本特征


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
    )
    orch.wire()
    await chat.emit("alice", "在玩啥?")
    assert persona_called_with == [ctx]


from tests.conftest import FakeAudioSink, FakeTTS


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
        tts=tts,
        audio_sink=sink,
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    assert chat.sent == ["@alice 好啊"]
    assert tts.calls == ["好啊"]   # synth 成功了
    # sink 写文件失败了,但 chat 路径不受影响


@pytest.mark.asyncio
async def test_no_tts_when_llm_fails():
    """LLM 失败时只发 fallback chat,不调 TTS(没有有效回复内容)。"""
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
        tts=tts,
        audio_sink=sink,
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    assert len(chat.sent) == 1
    assert tts.calls == []
    assert sink.writes == []
