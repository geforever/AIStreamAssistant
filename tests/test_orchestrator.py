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
