import asyncio
from unittest.mock import MagicMock

import pytest

from g_chan.tts.base import TTSTimeoutError
from g_chan.tts.edge import EdgeTTSEngine

_VOICES = {
    "zh": "zh-CN-XiaoyiNeural",
    "en": "en-US-AvaNeural",
    "ja": "ja-JP-NanamiNeural",
}


def _fake_communicate(chunks: list[dict]):
    """构造一个 fake edge_tts.Communicate 实例,stream() 异步产出指定 chunks。"""
    fake = MagicMock()

    async def stream():
        for c in chunks:
            yield c

    fake.stream = stream
    return fake


@pytest.mark.asyncio
async def test_synthesize_concatenates_audio_chunks(monkeypatch):
    chunks = [
        {"type": "audio", "data": b"AAA"},
        {"type": "WordBoundary", "offset": 0, "duration": 100, "text": "你好"},
        {"type": "audio", "data": b"BBB"},
        {"type": "audio", "data": b"CCC"},
    ]
    fake = _fake_communicate(chunks)
    monkeypatch.setattr(
        "g_chan.tts.edge.edge_tts.Communicate",
        lambda text, voice, rate, pitch: fake,
    )

    engine = EdgeTTSEngine(voices=_VOICES, rate="+10%", pitch="+5Hz")
    audio = await engine.synthesize("你好世界", language="zh")
    assert audio.data == b"AAABBBCCC"
    assert audio.format == "mp3"
    assert audio.voice == _VOICES["zh"]


@pytest.mark.asyncio
async def test_synthesize_picks_voice_per_language(monkeypatch):
    """同一个 engine 不同 language 调用 → 选不同 voice。"""
    captured: list[str] = []

    def fake_ctor(text, voice, rate, pitch):
        captured.append(voice)
        return _fake_communicate([{"type": "audio", "data": b"X"}])

    monkeypatch.setattr("g_chan.tts.edge.edge_tts.Communicate", fake_ctor)

    engine = EdgeTTSEngine(voices=_VOICES)
    await engine.synthesize("你好", language="zh")
    await engine.synthesize("hello", language="en")
    await engine.synthesize("こんにちは", language="ja")

    assert captured == [_VOICES["zh"], _VOICES["en"], _VOICES["ja"]]


@pytest.mark.asyncio
async def test_synthesize_passes_text_rate_pitch(monkeypatch):
    captured = {}

    def fake_ctor(text, voice, rate, pitch):
        captured["text"] = text
        captured["voice"] = voice
        captured["rate"] = rate
        captured["pitch"] = pitch
        return _fake_communicate([{"type": "audio", "data": b"X"}])

    monkeypatch.setattr("g_chan.tts.edge.edge_tts.Communicate", fake_ctor)

    engine = EdgeTTSEngine(voices=_VOICES, rate="-5%", pitch="+0Hz")
    await engine.synthesize("こんにちは", language="ja")
    assert captured == {
        "text": "こんにちは",
        "voice": _VOICES["ja"],
        "rate": "-5%",
        "pitch": "+0Hz",
    }


@pytest.mark.asyncio
async def test_synthesize_falls_back_when_language_voice_missing(monkeypatch):
    """voices 没配某语言时退到 dict 第一个 voice + 打 warn。"""
    captured: list[str] = []

    def fake_ctor(text, voice, rate, pitch):
        captured.append(voice)
        return _fake_communicate([{"type": "audio", "data": b"X"}])

    monkeypatch.setattr("g_chan.tts.edge.edge_tts.Communicate", fake_ctor)

    engine = EdgeTTSEngine(voices={"zh": "zh-CN-XiaoyiNeural"})
    await engine.synthesize("hello", language="en")   # en 没配
    assert captured == ["zh-CN-XiaoyiNeural"]


def test_engine_requires_at_least_one_voice():
    with pytest.raises(ValueError, match="at least one voice"):
        EdgeTTSEngine(voices={})


@pytest.mark.asyncio
async def test_synthesize_timeout_raises(monkeypatch):
    """模拟 stream() 卡死,超时应抛 TTSTimeoutError。"""
    fake = MagicMock()

    async def hangs():
        await asyncio.sleep(10)
        yield {"type": "audio", "data": b"X"}

    fake.stream = hangs
    monkeypatch.setattr(
        "g_chan.tts.edge.edge_tts.Communicate",
        lambda text, voice, rate, pitch: fake,
    )

    engine = EdgeTTSEngine(voices=_VOICES)
    with pytest.raises(TTSTimeoutError):
        await engine.synthesize("hello", language="en", timeout_s=0.05)


@pytest.mark.asyncio
async def test_synthesize_returns_empty_when_no_audio_chunks(monkeypatch):
    """如果 edge_tts 只返回 WordBoundary 不返回 audio,应得空音频(不崩)。"""
    fake = _fake_communicate([
        {"type": "WordBoundary", "offset": 0, "duration": 100, "text": "a"},
    ])
    monkeypatch.setattr(
        "g_chan.tts.edge.edge_tts.Communicate",
        lambda text, voice, rate, pitch: fake,
    )

    engine = EdgeTTSEngine(voices=_VOICES)
    audio = await engine.synthesize("x", language="zh")
    assert audio.data == b""
    assert audio.format == "mp3"
