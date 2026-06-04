import base64

import pytest

from g_chan.tts.base import TTSAudio
from g_chan.viewer_sink.ws_sink import WSViewerSink


class FakeCM:
    def __init__(self):
        self.broadcasts: list[dict] = []

    async def broadcast(self, payload: dict) -> None:
        self.broadcasts.append(payload)


@pytest.mark.asyncio
async def test_push_expression_broadcasts_lowercase_payload():
    cm = FakeCM()
    sink = WSViewerSink(cm)
    await sink.push_expression("smile")
    assert cm.broadcasts == [{"type": "expression", "name": "smile"}]


@pytest.mark.asyncio
async def test_push_motion_broadcasts_payload():
    cm = FakeCM()
    sink = WSViewerSink(cm)
    await sink.push_motion("tap")
    assert cm.broadcasts == [{"type": "motion", "name": "tap"}]


@pytest.mark.asyncio
async def test_push_empty_expression_sends_none():
    """空字符串 = 维持当前状态,但 viewer 协议用 'None' 显式表达。"""
    cm = FakeCM()
    sink = WSViewerSink(cm)
    await sink.push_expression("")
    assert cm.broadcasts == [{"type": "expression", "name": "None"}]


@pytest.mark.asyncio
async def test_push_audio_base64_encodes_and_includes_text():
    cm = FakeCM()
    sink = WSViewerSink(cm)
    audio = TTSAudio(data=b"FAKEMP3BYTES", format="mp3", voice="x", duration_ms=None)
    await sink.push_audio(audio, user="alice", text="hello")
    assert len(cm.broadcasts) == 1
    msg = cm.broadcasts[0]
    assert msg["type"] == "speak"
    assert msg["format"] == "mp3"
    assert msg["text"] == "hello"
    assert base64.b64decode(msg["audio"]) == b"FAKEMP3BYTES"


@pytest.mark.asyncio
async def test_push_methods_swallow_broadcast_errors():
    """任何 broadcast 异常都不能往上抛,否则会冒进 orchestrator 影响 chat。"""
    class BrokenCM:
        async def broadcast(self, payload):
            raise RuntimeError("network down")

    sink = WSViewerSink(BrokenCM())
    await sink.push_expression("smile")
    await sink.push_motion("tap")
    await sink.push_audio(
        TTSAudio(data=b"x", format="mp3", voice="y", duration_ms=None),
        user="a", text="b",
    )
