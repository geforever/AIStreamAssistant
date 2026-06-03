import re
from pathlib import Path

import pytest

from g_chan.tts.base import TTSAudio
from g_chan.tts.file_sink import FileAudioSink


def _audio(data: bytes = b"FAKEMP3") -> TTSAudio:
    return TTSAudio(data=data, format="mp3", voice="zh-CN-XiaoyiNeural", duration_ms=None)


@pytest.mark.asyncio
async def test_write_creates_file_with_correct_content(tmp_path):
    sink = FileAudioSink(output_dir=str(tmp_path))
    path = await sink.write(_audio(b"HELLO"), user="alice")
    p = Path(path)
    assert p.exists()
    assert p.read_bytes() == b"HELLO"
    assert p.suffix == ".mp3"


@pytest.mark.asyncio
async def test_filename_includes_user_and_timestamp(tmp_path):
    sink = FileAudioSink(output_dir=str(tmp_path))
    path = await sink.write(_audio(), user="alice")
    p = Path(path)
    # 形如 20260603-104530-123_alice.mp3
    assert re.fullmatch(r"\d{8}-\d{6}-\d{3}_alice\.mp3", p.name), p.name


@pytest.mark.asyncio
async def test_creates_output_dir_if_missing(tmp_path):
    sub = tmp_path / "deep" / "nested" / "out"
    sink = FileAudioSink(output_dir=str(sub))
    path = await sink.write(_audio(), user="bob")
    assert Path(path).exists()
    assert sub.is_dir()


@pytest.mark.asyncio
async def test_sanitizes_unsafe_user_chars(tmp_path):
    """聊天 username 理论上不会有 / 但防御一下;非字母数字下划线连字符都替换为 _。"""
    sink = FileAudioSink(output_dir=str(tmp_path))
    path = await sink.write(_audio(), user="evil/../hax")
    name = Path(path).name
    # 不应含路径分隔符 / 或 ..
    assert "/" not in name
    assert ".." not in name
    # 末尾应该是 _<sanitized>.mp3
    assert name.endswith(".mp3")
