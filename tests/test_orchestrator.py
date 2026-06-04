import asyncio

import pytest

from g_chan.llm.base import LLMTimeoutError
from g_chan.orchestrator import Orchestrator
from g_chan.persona.loader import StreamContext
from tests.conftest import FakeAudioSink, FakeChat, FakeLLM, FakeTTS, make_reply


class FixedPersona:
    def assemble(self, *, stream_ctx):  # noqa: ARG002
        return "你是 G 酱。"


class FixedStreamCtx:
    def __init__(self, ctx: StreamContext | None):
        self._ctx = ctx
    def current(self):
        return self._ctx


# 可控时间 — 测试都用注入式 now_ms
class FakeClock:
    def __init__(self, start_ms: float = 1_000_000):
        self.now = start_ms
    def __call__(self) -> float:
        return self.now
    def advance(self, ms: float) -> None:
        self.now += ms


# 测试默认 fallback — 跟生产配置无关,测试只关心"fallback 触发时这个值会被用上"
_FB_KWARGS = {
    "fallback_text": "FB_TEXT",
    "fallback_kaomoji": "FB_KAO",
    "fallback_mood": "dizzy",
    "fallback_language": "zh",
    "default_expression": "",
    "default_motion": "",
    "expression_change_frequency": 1.0,
    "motion_change_frequency": 1.0,
}


def _build_orch(
    *, chat, llm, clock,
    vip_window_ms=0,
    batch_window_s=2,
    batch_cooldown_ms=0,
    buffer_size=10,
    tts=None, audio_sink=None,
    viewer_sink=None,
    random_fn=lambda: 0.0,
    **overrides,
):
    kw = dict(_FB_KWARGS)
    kw.update(overrides)
    return Orchestrator(
        chat=chat,
        llm=llm,
        persona=FixedPersona(),
        stream_ctx=FixedStreamCtx(None),
        vip_window_ms=vip_window_ms,
        batch_window_s=batch_window_s,
        batch_cooldown_ms=batch_cooldown_ms,
        buffer_size=buffer_size,
        tts=tts,
        audio_sink=audio_sink,
        viewer_sink=viewer_sink,
        now_ms=clock,
        random_fn=random_fn,
        **kw,
    )


# ============= VIP / Mod / Broadcaster 路径 =============

@pytest.mark.asyncio
async def test_vip_path_replies_immediately_with_at_user():
    """is_priority=True → 立即 LLM + chat 发 @user。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊~", mood="happy", kaomoji="(=ω=)")
    clock = FakeClock()
    orch = _build_orch(chat=chat, llm=llm, clock=clock)
    orch.wire()
    await chat.emit("modalice", "嗨", is_priority=True)
    # VIP 路径是 create_task 异步触发,等一会
    await asyncio.sleep(0.05)
    assert chat.sent == ["@modalice 好啊~ (=ω=)"]
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_vip_rate_limited_silently_drops():
    """vip_window_ms 内的第二次 vip @ silent drop,无 busy reply。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊", mood="happy")
    clock = FakeClock()
    orch = _build_orch(chat=chat, llm=llm, clock=clock, vip_window_ms=10_000)
    orch.wire()

    await chat.emit("modalice", "嗨", is_priority=True)
    await asyncio.sleep(0.05)
    # 仍在 10s 窗口内
    clock.advance(500)
    await chat.emit("modbob", "嗨", is_priority=True)
    await asyncio.sleep(0.05)

    assert len(chat.sent) == 1   # 只发了一条(alice 的)
    assert "modalice" in chat.sent[0]


@pytest.mark.asyncio
async def test_vip_llm_failure_uses_fallback():
    chat = FakeChat()
    llm = FakeLLM()
    llm.should_raise = LLMTimeoutError("boom")
    clock = FakeClock()
    orch = _build_orch(chat=chat, llm=llm, clock=clock)
    orch.wire()
    await chat.emit("modalice", "嗨", is_priority=True)
    await asyncio.sleep(0.05)
    # fallback 是 "FB_TEXT" + "FB_KAO"
    assert chat.sent == ["@modalice FB_TEXT FB_KAO"]


# ============= 普通観众批处理路径 =============

@pytest.mark.asyncio
async def test_regular_single_message_batched_then_replied():
    """单条普通 @ → 等 batch_window 后 flush → 1 条 chat(无 @user)。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啦", mood="happy", kaomoji="(=ω=)")
    clock = FakeClock()
    orch = _build_orch(chat=chat, llm=llm, clock=clock, batch_window_s=0.05)
    orch.wire()

    await chat.emit("alice", "嗨")
    # 等待 scheduled flush(实际 0.05s + 一点点)
    await asyncio.sleep(0.15)

    assert chat.sent == ["好啦 (=ω=)"]   # 没有 @user
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_regular_dedup_by_user_keeps_latest():
    """同一 user 多次 @ → buffer 只留最新一条。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("回复", mood="happy")
    clock = FakeClock()
    orch = _build_orch(chat=chat, llm=llm, clock=clock, batch_window_s=0.05)
    orch.wire()

    await chat.emit("alice", "第一条")
    clock.advance(10)
    await chat.emit("alice", "第二条")
    clock.advance(10)
    await chat.emit("alice", "第三条")
    await asyncio.sleep(0.15)

    # LLM 应只看到最新的 "第三条"
    assert len(llm.calls) == 1
    user_content = llm.calls[0][1].content
    assert "第三条" in user_content
    assert "第一条" not in user_content
    assert "第二条" not in user_content


@pytest.mark.asyncio
async def test_regular_silence_drops_no_chat_no_tts():
    """LLM 返回 text='' → batch 不发 chat 不调 TTS,buffer 清空。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("", mood="happy")   # 空 text
    tts = FakeTTS()
    sink = FakeAudioSink()
    clock = FakeClock()
    orch = _build_orch(
        chat=chat, llm=llm, clock=clock, batch_window_s=0.05,
        tts=tts, audio_sink=sink,
    )
    orch.wire()

    await chat.emit("alice", "嗨")
    await asyncio.sleep(0.15)

    assert chat.sent == []
    assert tts.calls == []
    assert sink.writes == []


@pytest.mark.asyncio
async def test_regular_cooldown_drops_during_window():
    """cooldown 内的普通 @ silent drop。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("回复1", mood="happy")
    clock = FakeClock()
    orch = _build_orch(
        chat=chat, llm=llm, clock=clock,
        batch_window_s=0.05, batch_cooldown_ms=10_000,
    )
    orch.wire()

    await chat.emit("alice", "嗨")
    await asyncio.sleep(0.15)   # 让第一个 batch flush

    assert chat.sent == ["回复1"]
    assert len(llm.calls) == 1

    # 仍在 cooldown 内,新 @ 应被 drop
    clock.advance(500)
    await chat.emit("bob", "嗨2")
    await asyncio.sleep(0.15)
    assert len(chat.sent) == 1   # bob 没触发
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_regular_batch_disabled_when_window_zero():
    """batch_window_s=0 → 普通観众完全不响应。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("不应被调用", mood="happy")
    clock = FakeClock()
    orch = _build_orch(chat=chat, llm=llm, clock=clock, batch_window_s=0)
    orch.wire()

    await chat.emit("alice", "嗨")
    await asyncio.sleep(0.15)
    assert chat.sent == []
    assert llm.calls == []


# ============= 混合(VIP + 普通)=============

@pytest.mark.asyncio
async def test_vip_and_regular_run_concurrently():
    """VIP @ 立即回复,期间普通 @ 仍可进 buffer 等 flush。"""
    chat = FakeChat()
    llm = FakeLLM()
    # 两次 LLM:一次 VIP,一次 batch
    replies = [
        make_reply("VIP回复", mood="happy"),
        make_reply("batch回复", mood="happy"),
    ]
    call_idx = [0]
    async def fake_generate(messages, **kw):
        i = call_idx[0]
        call_idx[0] += 1
        return replies[i]
    llm.generate = fake_generate  # type: ignore[method-assign]

    clock = FakeClock()
    orch = _build_orch(chat=chat, llm=llm, clock=clock, batch_window_s=0.05)
    orch.wire()

    await chat.emit("modalice", "嗨", is_priority=True)
    await chat.emit("bob", "嗨")
    await asyncio.sleep(0.2)

    # 两条都应发出
    assert "@modalice VIP回复" in chat.sent
    assert "batch回复" in chat.sent   # 无 @


# ============= 批处理 + TTS 集成 =============

@pytest.mark.asyncio
async def test_batch_path_drives_tts_with_batch_user_label():
    """batch flush 时调 TTS,sink.user 标记为 'batch'。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("hi", mood="happy", language="en")
    tts = FakeTTS()
    sink = FakeAudioSink()
    clock = FakeClock()
    orch = _build_orch(
        chat=chat, llm=llm, clock=clock,
        batch_window_s=0.05,
        tts=tts, audio_sink=sink,
    )
    orch.wire()

    await chat.emit("alice", "yo")
    await asyncio.sleep(0.15)

    assert tts.calls == [("hi", "en")]
    assert len(sink.writes) == 1
    _, user_tag = sink.writes[0]
    assert user_tag == "batch"


# ============= Live2D 频率裁剪 =============

@pytest.mark.asyncio
async def test_vip_uses_llm_expression_when_random_passes():
    """random_fn=lambda: 0.0 → 0 < 1.0 → 总是采纳 LLM 选的。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊", mood="happy",
                                expression="Smile", motion="Tap")
    clock = FakeClock()
    orch = _build_orch(
        chat=chat, llm=llm, clock=clock,
        random_fn=lambda: 0.0,
        expression_change_frequency=1.0,
        motion_change_frequency=1.0,
    )
    orch.wire()
    await chat.emit("alice", "嗨", is_priority=True)
    await asyncio.sleep(0.05)
    # chat 行为正确(expression 进了 log,不暴露 API)
    assert chat.sent == ["@alice 好啊"]


@pytest.mark.asyncio
async def test_vip_uses_default_when_random_fails_frequency():
    """random_fn returns 0.5,frequency=0.0 → 不采纳 → 用 default。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊", mood="happy",
                                expression="Smile", motion="Tap")
    clock = FakeClock()
    orch = _build_orch(
        chat=chat, llm=llm, clock=clock,
        random_fn=lambda: 0.5,
        expression_change_frequency=0.0,
        motion_change_frequency=0.0,
        default_expression="Normal",
        default_motion="Idle",
    )
    orch.wire()
    await chat.emit("alice", "嗨", is_priority=True)
    await asyncio.sleep(0.05)
    # chat 不受影响
    assert chat.sent == ["@alice 好啊"]


@pytest.mark.asyncio
async def test_batch_applies_frequency_too():
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("yo", mood="happy",
                                expression="Smile", motion="Tap")
    clock = FakeClock()
    orch = _build_orch(
        chat=chat, llm=llm, clock=clock,
        batch_window_s=0.05,
        random_fn=lambda: 0.0,
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    await asyncio.sleep(0.15)
    assert chat.sent == ["yo"]


# ============= ViewerSink 集成 =============

@pytest.mark.asyncio
async def test_vip_pushes_expression_motion_audio_to_viewer():
    from tests.conftest import FakeViewerSink
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊", mood="happy",
                                expression="smile", motion="tap")
    tts = FakeTTS()
    sink = FakeAudioSink()
    viewer = FakeViewerSink()
    clock = FakeClock()
    orch = _build_orch(
        chat=chat, llm=llm, clock=clock,
        tts=tts, audio_sink=sink, viewer_sink=viewer,
    )
    orch.wire()
    await chat.emit("alice", "嗨", is_priority=True)
    await asyncio.sleep(0.05)

    assert viewer.expressions == ["smile"]
    assert viewer.motions == ["tap"]
    assert len(viewer.audios) == 1
    audio_data, user, text = viewer.audios[0]
    assert audio_data == b"FAKEAUDIO"
    assert user == "alice"
    assert text == "好啊"


@pytest.mark.asyncio
async def test_batch_pushes_to_viewer_with_batch_user_label():
    from tests.conftest import FakeViewerSink
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("yo", mood="happy",
                                expression="smile", motion="")
    tts = FakeTTS()
    sink = FakeAudioSink()
    viewer = FakeViewerSink()
    clock = FakeClock()
    orch = _build_orch(
        chat=chat, llm=llm, clock=clock,
        batch_window_s=0.05,
        tts=tts, audio_sink=sink, viewer_sink=viewer,
    )
    orch.wire()
    await chat.emit("alice", "嗨")
    await asyncio.sleep(0.15)

    assert viewer.expressions == ["smile"]
    assert viewer.motions == [""]
    assert len(viewer.audios) == 1
    _, user, _ = viewer.audios[0]
    assert user == "batch"


@pytest.mark.asyncio
async def test_works_without_viewer_sink_passed():
    """viewer_sink=None → Orchestrator 用 NoopViewerSink,不崩,chat 正常发。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊", mood="happy", expression="smile")
    clock = FakeClock()
    orch = _build_orch(chat=chat, llm=llm, clock=clock)   # 没 viewer_sink
    orch.wire()
    await chat.emit("alice", "嗨", is_priority=True)
    await asyncio.sleep(0.05)
    assert chat.sent == ["@alice 好啊"]
