# G 酱 — Phase 2 Implementation Plan(加 TTS — 后端写 mp3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Phase 1 基础上,LLM 回复后**并行**调 Edge TTS 把回复文本合成成音频,写到 `out/<ts>_<user>.mp3` 文件。Chat 文字回复路径不被 TTS 阻塞。前端 Live2D / WS 推送留到 Phase 3。

**Architecture:** 新增 `g_chan.tts` 子包,定义 `TTSEngine` ABC + `EdgeTTSEngine` 实现 + `AudioSink` Protocol + `FileAudioSink` 实现。Orchestrator 接受可选的 `tts` 和 `audio_sink`,在 LLM 回复后用 `asyncio.gather` 让 chat.send 和 (tts.synthesize → audio_sink.write) **并行**跑 — 任一路径失败不影响另一条。

**Tech Stack:** `edge-tts`(微软 Edge 同源 TTS,免费、词边界支持、动漫感声线)+ Python asyncio。其余沿用 Phase 1 栈。

**用户偏好:** 此项目不提交 git。所有 task 跳过 commit 步骤,只做"写测试 → 跑红 → 实现 → 跑绿"。

**Phase 2 不做:** WebSocket 服务、Live2D viewer、口型同步、表情切换、TTS 文件清理/轮转、多 voice、按 mood 切 voice。

---

## 文件结构(Phase 2 新增/修改)

```
新增:
  src/g_chan/tts/
    __init__.py
    base.py          # TTSAudio, TTSEngine ABC, TTSError, AudioSink Protocol
    edge.py          # EdgeTTSEngine
    file_sink.py     # FileAudioSink (写 out/<ts>_<user>.mp3)
  tests/
    test_edge_tts.py
    test_file_sink.py

修改:
  pyproject.toml             # +edge-tts
  config.example.yaml        # +tts: 块
  src/g_chan/config.py       # +TTSConfig dataclass, +AppConfig.tts
  tests/test_config.py       # 测试 yaml 里加 tts: 块
  src/g_chan/orchestrator.py # 接受可选 tts/audio_sink,并行 send + synthesize
  tests/test_orchestrator.py # 增加 TTS 集成 test
  src/g_chan/__main__.py     # 装配 EdgeTTSEngine + FileAudioSink
  tests/conftest.py          # +FakeTTS, +FakeAudioSink fixtures
```

---

## Task 1: 加 edge-tts 依赖

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1.1: 编辑 `pyproject.toml`,在 `dependencies` 数组里加一行 `"edge-tts>=6.1.0",`(放在 `google-genai` 那行下面,保持字母序大致合理即可)**

最终 `dependencies` 列表应包含(顺序不强求):
```toml
dependencies = [
    "twitchio>=2.10,<3.0",
    "twitchapi>=4.0.0",
    "google-genai>=0.3.0",
    "edge-tts>=6.1.0",
    "httpx[socks]>=0.27",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "rich>=13.7",
]
```

- [ ] **Step 1.2: 同步**

```bash
uv sync
```
Expected: 安装 `edge-tts`(及其依赖 aiohttp 等已经在了)。输出末尾包含 `+ edge-tts==x.y.z`。

- [ ] **Step 1.3: 验证 import**

```bash
uv run python -c "import edge_tts; print('edge-tts:', edge_tts.__version__ if hasattr(edge_tts, '__version__') else 'ok')"
```
Expected: 输出 `edge-tts: x.y.z` 或 `edge-tts: ok`,不报错。

---

## Task 2: 添加 TTS 配置

**Files:**
- Modify: `src/g_chan/config.py`
- Modify: `config.example.yaml`
- Modify: `tests/test_config.py`

- [ ] **Step 2.1: 写新测试(放在 `tests/test_config.py` 末尾)— 验证 tts 块能被解析**

把这段追加到 `tests/test_config.py` 末尾:

```python
def test_loads_tts_config(tmp_path, monkeypatch):
    monkeypatch.setenv("TWITCH_OAUTH", "oauth:abc")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "cid")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "csec")
    monkeypatch.setenv("GEMINI_API_KEY", "gkey")
    cfg_path = write_yaml(tmp_path, """
twitch:
  channel: "alice"
  bot_username: "g_bot"
  trigger: "@G酱"
rate_limit:
  global_window_ms: 5000
  busy_reply: "晕"
llm:
  provider: "gemini"
  model: "gemini-2.5-flash"
  temperature: 0.9
  max_tokens: 300
  timeout_s: 10
persona:
  prompt_file: "prompts/default.md"
  include_stream_context: true
stream_context:
  poll_interval_ms: 30000
tts:
  enabled: true
  voice: "zh-CN-XiaoyiNeural"
  rate: "+10%"
  pitch: "+5Hz"
  output_dir: "out"
  timeout_s: 10
logging:
  level: "info"
  file: "logs/g.log"
""")
    cfg = load_config(cfg_path)
    assert cfg.tts.enabled is True
    assert cfg.tts.voice == "zh-CN-XiaoyiNeural"
    assert cfg.tts.rate == "+10%"
    assert cfg.tts.pitch == "+5Hz"
    assert cfg.tts.output_dir == "out"
    assert cfg.tts.timeout_s == 10


def test_tts_defaults_when_section_missing(tmp_path, monkeypatch):
    """tts: 块在 yaml 中可缺省 — 用默认值。"""
    monkeypatch.setenv("TWITCH_OAUTH", "x")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "x")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    cfg_path = write_yaml(tmp_path, """
twitch:
  channel: "alice"
  bot_username: "g_bot"
  trigger: "@G酱"
rate_limit:
  global_window_ms: 5000
  busy_reply: "晕"
llm:
  provider: "gemini"
  model: "gemini-2.5-flash"
  temperature: 0.9
  max_tokens: 300
  timeout_s: 10
persona:
  prompt_file: "prompts/default.md"
  include_stream_context: true
stream_context:
  poll_interval_ms: 30000
logging:
  level: "info"
  file: "logs/g.log"
""")
    cfg = load_config(cfg_path)
    assert cfg.tts.enabled is True
    assert cfg.tts.voice == "zh-CN-XiaoyiNeural"
    assert cfg.tts.output_dir == "out"
```

- [ ] **Step 2.2: 跑测试,确认红**

```bash
uv run pytest tests/test_config.py::test_loads_tts_config tests/test_config.py::test_tts_defaults_when_section_missing -v
```
Expected: FAIL,因为 `cfg.tts` 不存在(AttributeError 或类似)。

- [ ] **Step 2.3: 编辑 `src/g_chan/config.py`,添加 `TTSConfig` dataclass 并接到 `AppConfig`**

在 `LoggingConfig` 类**之前**加:

```python
class TTSConfig(BaseModel):
    enabled: bool = True
    voice: str = "zh-CN-XiaoyiNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    output_dir: str = "out"
    timeout_s: float = 10.0
```

然后在 `AppConfig` 里(`stream_context: StreamContextConfig` 那行之后,`logging` 之前)加:

```python
    tts: TTSConfig = Field(default_factory=TTSConfig)
```

`AppConfig` 现在应该长这样:

```python
class AppConfig(BaseModel):
    twitch: TwitchConfig
    rate_limit: RateLimitConfig
    llm: LLMConfig
    persona: PersonaConfig
    stream_context: StreamContextConfig
    tts: TTSConfig = Field(default_factory=TTSConfig)
    logging: LoggingConfig
```

- [ ] **Step 2.4: 跑测试,确认绿**

```bash
uv run pytest tests/test_config.py -v
```
Expected: 5 passed(原 3 + 新 2)。

- [ ] **Step 2.5: 同步 `config.example.yaml`**

在 `stream_context:` 块**之后**、`logging:` 块**之前**插入:

```yaml
tts:
  enabled: true
  voice: "zh-CN-XiaoyiNeural"   # 备选: zh-CN-XiaoxiaoNeural / zh-CN-XiaoshuangNeural / ja-JP-NanamiNeural
  rate: "+10%"
  pitch: "+5Hz"
  output_dir: "out"
  timeout_s: 10
```

(用户已有的 `config.yaml` 不会被覆盖 — 那是 gitignore 的本地副本,Task 7 末尾会提醒用户同步进去。)

---

## Task 3: TTS Base 接口

**Files:**
- Create: `src/g_chan/tts/__init__.py` (空)
- Create: `src/g_chan/tts/base.py`

无单元测试 — 纯接口 + dataclass。

- [ ] **Step 3.1: 创建 `src/g_chan/tts/__init__.py`(空文件)**

```bash
touch src/g_chan/tts/__init__.py
```

- [ ] **Step 3.2: 写 `src/g_chan/tts/base.py`**

```python
"""TTS 抽象层 — 接口、类型、异常。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class TTSAudio:
    data: bytes              # 音频字节流
    format: str              # "mp3" / "wav" 等
    voice: str               # 实际使用的 voice 名(便于日志)
    duration_ms: int | None  # 可选,部分引擎不返回


class TTSError(Exception): ...
class TTSTimeoutError(TTSError): ...
class TTSServerError(TTSError): ...


class TTSEngine(ABC):
    @abstractmethod
    async def synthesize(self, text: str, *, timeout_s: float = 10.0) -> TTSAudio: ...


class AudioSink(Protocol):
    """音频接收方 — Phase 2 写文件,Phase 3 推 WebSocket。"""
    async def write(self, audio: TTSAudio, *, user: str) -> Path | str: ...
```

- [ ] **Step 3.3: 验证 import**

```bash
uv run python -c "from g_chan.tts.base import TTSAudio, TTSEngine, TTSError, AudioSink; print('ok')"
```
Expected: `ok`.

- [ ] **Step 3.4: 全套测试不应受影响**

```bash
uv run pytest 2>&1 | tail -3
```
Expected: still 40 passed(38 原 + 2 Task 2 新)。

---

## Task 4: EdgeTTSEngine 实现(TDD)

**Files:**
- Create: `src/g_chan/tts/edge.py`
- Create: `tests/test_edge_tts.py`

- [ ] **Step 4.1: 写测试 `tests/test_edge_tts.py`**

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from g_chan.tts.base import TTSTimeoutError
from g_chan.tts.edge import EdgeTTSEngine


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

    engine = EdgeTTSEngine(voice="zh-CN-XiaoyiNeural", rate="+10%", pitch="+5Hz")
    audio = await engine.synthesize("你好世界")
    assert audio.data == b"AAABBBCCC"
    assert audio.format == "mp3"
    assert audio.voice == "zh-CN-XiaoyiNeural"


@pytest.mark.asyncio
async def test_synthesize_passes_voice_rate_pitch(monkeypatch):
    captured = {}

    def fake_ctor(text, voice, rate, pitch):
        captured["text"] = text
        captured["voice"] = voice
        captured["rate"] = rate
        captured["pitch"] = pitch
        return _fake_communicate([{"type": "audio", "data": b"X"}])

    monkeypatch.setattr("g_chan.tts.edge.edge_tts.Communicate", fake_ctor)

    engine = EdgeTTSEngine(voice="ja-JP-NanamiNeural", rate="-5%", pitch="+0Hz")
    await engine.synthesize("こんにちは")
    assert captured == {
        "text": "こんにちは",
        "voice": "ja-JP-NanamiNeural",
        "rate": "-5%",
        "pitch": "+0Hz",
    }


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

    engine = EdgeTTSEngine(voice="zh-CN-XiaoyiNeural")
    with pytest.raises(TTSTimeoutError):
        await engine.synthesize("hello", timeout_s=0.05)


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

    engine = EdgeTTSEngine(voice="zh-CN-XiaoyiNeural")
    audio = await engine.synthesize("x")
    assert audio.data == b""
    assert audio.format == "mp3"
```

- [ ] **Step 4.2: 跑测试,确认红**

```bash
uv run pytest tests/test_edge_tts.py -v
```
Expected: ImportError。

- [ ] **Step 4.3: 写 `src/g_chan/tts/edge.py`**

```python
"""Edge TTS provider — 包 edge_tts。"""
from __future__ import annotations

import asyncio
import logging

import edge_tts

from g_chan.tts.base import (
    TTSAudio,
    TTSEngine,
    TTSServerError,
    TTSTimeoutError,
)

log = logging.getLogger(__name__)


class EdgeTTSEngine(TTSEngine):
    def __init__(self, *, voice: str, rate: str = "+0%", pitch: str = "+0Hz"):
        self._voice = voice
        self._rate = rate
        self._pitch = pitch

    async def synthesize(self, text: str, *, timeout_s: float = 10.0) -> TTSAudio:
        async def _do() -> bytes:
            communicate = edge_tts.Communicate(
                text, self._voice, rate=self._rate, pitch=self._pitch
            )
            buf = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio":
                    buf.extend(chunk["data"])
            return bytes(buf)

        try:
            data = await asyncio.wait_for(_do(), timeout=timeout_s)
        except asyncio.TimeoutError as e:
            raise TTSTimeoutError(f"Edge TTS timeout after {timeout_s}s") from e
        except Exception as e:  # noqa: BLE001
            raise TTSServerError(f"Edge TTS error: {e}") from e

        return TTSAudio(
            data=data,
            format="mp3",
            voice=self._voice,
            duration_ms=None,
        )
```

- [ ] **Step 4.4: 跑测试,确认绿**

```bash
uv run pytest tests/test_edge_tts.py -v
```
Expected: 4 passed.

- [ ] **Step 4.5: 全套测试**

```bash
uv run pytest 2>&1 | tail -3
```
Expected: 44 passed(40 之前 + 4 新)。

---

## Task 5: FileAudioSink 实现(TDD)

**Files:**
- Create: `src/g_chan/tts/file_sink.py`
- Create: `tests/test_file_sink.py`

写到 `<output_dir>/<YYYYMMDD-HHMMSS-mmm>_<user>.mp3`。文件系统安全(无 `:` 等 Windows 禁字符)。

- [ ] **Step 5.1: 写测试 `tests/test_file_sink.py`**

```python
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
```

- [ ] **Step 5.2: 跑测试,确认红**

```bash
uv run pytest tests/test_file_sink.py -v
```
Expected: ImportError.

- [ ] **Step 5.3: 写 `src/g_chan/tts/file_sink.py`**

```python
"""文件 sink — 把 TTSAudio 写到 <output_dir>/<ts>_<user>.<ext>。"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path

from g_chan.tts.base import AudioSink, TTSAudio

log = logging.getLogger(__name__)

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_\-]")


def _sanitize(s: str) -> str:
    cleaned = _UNSAFE_CHARS.sub("_", s)
    return cleaned or "unknown"


class FileAudioSink(AudioSink):
    def __init__(self, output_dir: str):
        self._dir = Path(output_dir)

    async def write(self, audio: TTSAudio, *, user: str) -> Path:
        self._dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        ts = now.strftime("%Y%m%d-%H%M%S-") + f"{now.microsecond // 1000:03d}"
        safe_user = _sanitize(user)
        filename = f"{ts}_{safe_user}.{audio.format}"
        path = self._dir / filename
        path.write_bytes(audio.data)
        log.info("wrote audio: %s (%d bytes, voice=%s)",
                 path, len(audio.data), audio.voice)
        return path
```

- [ ] **Step 5.4: 跑测试,确认绿**

```bash
uv run pytest tests/test_file_sink.py -v
```
Expected: 4 passed.

- [ ] **Step 5.5: 全套测试**

```bash
uv run pytest 2>&1 | tail -3
```
Expected: 48 passed.

---

## Task 6: Orchestrator 集成 TTS

**Files:**
- Modify: `src/g_chan/orchestrator.py`
- Modify: `tests/conftest.py`
- Modify: `tests/test_orchestrator.py`

新增可选 `tts` + `audio_sink` 参数。如果都提供,LLM 回复后**并行**做 chat.send 和 (synthesize → audio_sink.write)。任一路径异常不影响另一条。

- [ ] **Step 6.1: 在 `tests/conftest.py` 末尾追加 `FakeTTS` 和 `FakeAudioSink`**

```python
from g_chan.tts.base import AudioSink, TTSAudio, TTSEngine


class FakeTTS(TTSEngine):
    def __init__(self):
        self.calls: list[str] = []
        self.next_audio: TTSAudio | None = TTSAudio(
            data=b"FAKEAUDIO", format="mp3", voice="fake", duration_ms=None
        )
        self.should_raise: Exception | None = None

    async def synthesize(self, text: str, *, timeout_s: float = 10.0) -> TTSAudio:
        self.calls.append(text)
        if self.should_raise:
            raise self.should_raise
        assert self.next_audio is not None
        return self.next_audio


class FakeAudioSink(AudioSink):
    def __init__(self):
        self.writes: list[tuple[TTSAudio, str]] = []
        self.should_raise: Exception | None = None

    async def write(self, audio: TTSAudio, *, user: str) -> str:
        self.writes.append((audio, user))
        if self.should_raise:
            raise self.should_raise
        return f"/fake/path/{user}.mp3"
```

- [ ] **Step 6.2: 写新测试(追加到 `tests/test_orchestrator.py` 末尾)**

```python
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
```

- [ ] **Step 6.3: 跑新测试,确认红**

```bash
uv run pytest tests/test_orchestrator.py -v
```
Expected: 之前的 4 个 pass,新的 5 个 fail(`Orchestrator.__init__` 不接受 tts/audio_sink kwargs)。

- [ ] **Step 6.4: 修改 `src/g_chan/orchestrator.py`**

完整替换文件内容:

```python
"""Orchestrator — 把 chat / persona / llm / rate_limit / tts 串成一条对话路径。"""
from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from g_chan.chat.base import ChatAdapter, ChatMessage
from g_chan.llm.base import LLMError, LLMMessage, LLMProvider
from g_chan.persona.loader import StreamContext
from g_chan.rate_limiter import RateLimiter
from g_chan.tts.base import AudioSink, TTSEngine, TTSError

log = logging.getLogger(__name__)


class PersonaLike(Protocol):
    def assemble(self, *, stream_ctx: StreamContext | None) -> str: ...


class StreamCtxLike(Protocol):
    def current(self) -> StreamContext | None: ...


_FALLBACK_TEXT = "诶呀脑子卡了一下,你再说一遍?"


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
        tts: TTSEngine | None = None,
        audio_sink: AudioSink | None = None,
    ):
        self._chat = chat
        self._llm = llm
        self._persona = persona
        self._stream_ctx = stream_ctx
        self._rl = RateLimiter(window_ms=rate_limit_ms)
        self._busy_reply = busy_reply
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
            log.warning("llm failed: %s", e)
            await self._chat.send(f"@{msg.user} {_FALLBACK_TEXT}")
            return

        log.info(
            "reply: mood=%s latency=%dms tokens=%d/%d text=%r",
            reply.mood, reply.latency_ms, reply.tokens_in, reply.tokens_out,
            reply.text,
        )

        # 并行: chat 文本 + TTS 合成保存。任一异常不影响另一条。
        chat_task = self._chat.send(f"@{msg.user} {reply.text}")
        tts_task = self._do_tts(reply.text, user=msg.user)
        await asyncio.gather(chat_task, tts_task, return_exceptions=False)
        # 注:gather(return_exceptions=False) + 内部 _do_tts 已 catch 所有异常
        # → 这里不会因 TTS 失败而抛

    async def _do_tts(self, text: str, *, user: str) -> None:
        if self._tts is None or self._audio_sink is None:
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
```

- [ ] **Step 6.5: 跑测试,确认全绿**

```bash
uv run pytest tests/test_orchestrator.py -v
```
Expected: 9 passed(原 4 + 新 5)。

- [ ] **Step 6.6: 跑全套**

```bash
uv run pytest 2>&1 | tail -3
```
Expected: 53 passed.

---

## Task 7: 装配到 `__main__.py`

**Files:**
- Modify: `src/g_chan/__main__.py`

- [ ] **Step 7.1: 在 imports 区(其他 g_chan 导入之间)添加**

```python
from g_chan.tts.edge import EdgeTTSEngine
from g_chan.tts.file_sink import FileAudioSink
```

- [ ] **Step 7.2: 在 `Orchestrator(...)` 调用**之前**,加入 TTS 装配**

把这段插到 `orch = Orchestrator(...)` 那行的**正上方**:

```python
    tts_engine: EdgeTTSEngine | None = None
    audio_sink: FileAudioSink | None = None
    if cfg.tts.enabled:
        tts_engine = EdgeTTSEngine(
            voice=cfg.tts.voice,
            rate=cfg.tts.rate,
            pitch=cfg.tts.pitch,
        )
        audio_sink = FileAudioSink(output_dir=cfg.tts.output_dir)
        log.info("tts enabled — voice=%s, output_dir=%s",
                 cfg.tts.voice, cfg.tts.output_dir)
    else:
        log.info("tts disabled (config.tts.enabled=false)")
```

- [ ] **Step 7.3: 把 `tts` 和 `audio_sink` 传给 Orchestrator**

把现有的:

```python
    orch = Orchestrator(
        chat=chat, llm=llm, persona=persona, stream_ctx=sctx,
        rate_limit_ms=cfg.rate_limit.global_window_ms,
        busy_reply=cfg.rate_limit.busy_reply,
    )
```

改为:

```python
    orch = Orchestrator(
        chat=chat, llm=llm, persona=persona, stream_ctx=sctx,
        rate_limit_ms=cfg.rate_limit.global_window_ms,
        busy_reply=cfg.rate_limit.busy_reply,
        tts=tts_engine,
        audio_sink=audio_sink,
    )
```

- [ ] **Step 7.4: smoke check — 启动失败应该是配置缺失,不是 ImportError**

```bash
mv config.yaml config.yaml.bak 2>/dev/null
uv run python -m g_chan
mv config.yaml.bak config.yaml 2>/dev/null
```
Expected: `FileNotFoundError: [Errno 2] No such file or directory: 'config.yaml'`(不是 ImportError 或 NameError)。

- [ ] **Step 7.5: 提醒用户:同步本地 `config.yaml`**

向用户报告时注明:**本地 `config.yaml` 是 gitignore 的,自动模板更新不会覆盖你的。需要手动添加 `tts:` 块:**

```yaml
tts:
  enabled: true
  voice: "zh-CN-XiaoyiNeural"
  rate: "+10%"
  pitch: "+5Hz"
  output_dir: "out"
  timeout_s: 10
```

(如果用户没加 tts 块,`AppConfig.tts` 有默认值,程序仍可启动 — 用默认 voice/rate/pitch/output_dir。)

- [ ] **Step 7.6: 全套测试 + ruff**

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```
Expected:
- pytest: 53 passed
- ruff: `All checks passed!`(如果新代码有小问题,`uv run ruff check --fix src tests`)

---

## Task 8: 真实 Edge TTS 烟雾测试(可选,验证 SDK 实际工作)

**Files:** 无新增。这是一次性命令验证,不固化到 tests/(避免单元测试依赖网络)。

- [ ] **Step 8.1: 不走 bot,直接调一次 Edge TTS,确认能拿到真音频**

```bash
uv run python -c "
import asyncio
from pathlib import Path
from g_chan.tts.edge import EdgeTTSEngine

async def main():
    engine = EdgeTTSEngine(voice='zh-CN-XiaoyiNeural', rate='+10%', pitch='+5Hz')
    audio = await engine.synthesize('哼,本小姐才不是在等你呢,笨蛋!')
    Path('out').mkdir(exist_ok=True)
    out = Path('out/smoke_test.mp3')
    out.write_bytes(audio.data)
    print(f'wrote {out} ({len(audio.data)} bytes)')

asyncio.run(main())
"
```
Expected:
- 输出 `wrote out/smoke_test.mp3 (XXXXX bytes)`,bytes 数应 > 5000
- `out/smoke_test.mp3` 文件存在

- [ ] **Step 8.2: 用系统默认播放器试听**

```bash
afplay out/smoke_test.mp3   # macOS
# 或:open out/smoke_test.mp3
```
Expected: 听到 G 酱说出"哼,本小姐才不是在等你呢,笨蛋!",声线为 zh-CN-XiaoyiNeural(年轻女声,略带活泼)。

如果觉得不够"傲娇",改 voice 试试:
- `zh-CN-XiaoxiaoNeural` — 标准甜美
- `zh-CN-XiaoshuangNeural` — 偏童声
- `zh-CN-XiaohanNeural` — 偏冷淡

---

## Task 9: 端到端验证(连接 Twitch + 真实 chat)

**Files:** 无新增。

- [ ] **Step 9.1: 启动 bot**

```bash
uv run python -m g_chan
```
Expected 启动日志多了:
- `tts enabled — voice=zh-CN-XiaoyiNeural, output_dir=out`(如果 enabled)
- 或 `tts disabled (config.tts.enabled=false)`

- [ ] **Step 9.2: 在 Twitch chat 测试**

发 `@G酱 嗨`,**两件事应同时发生:**

1. **Chat 立刻收到文字回复**(跟 Phase 1 体验一致)
2. **`out/` 目录里多一个新 mp3**,文件名形如 `20260603-104530-123_<你的用户名>.mp3`

```bash
ls -la out/
```

- [ ] **Step 9.3: 试听最新的 mp3**

```bash
afplay "$(ls -t out/*.mp3 | head -1)"
```
Expected: 听到 G 酱用本次回复的内容说话。

- [ ] **Step 9.4: 测 chat 路径不被 TTS 阻塞**

发一条比较长的消息 `@G酱 给我讲一个超级超级长的关于傲娇女孩的故事`。
- chat 文字回复应该在 ~1 秒内出现
- mp3 文件几秒后才出现(TTS 合成需要更长时间)

如果 chat 文字回复也变慢到 5+ 秒才出现,说明 gather 串行了 — 检查 Orchestrator._handle 实现。

- [ ] **Step 9.5: 测 TTS 失败不影响 chat**

临时把 `.env` 里的 Gemini key 改掉(让 TTS 那条路 OK 但模拟个错)... 实际操作有点复杂,跳过本步,以集成测试为准。

---

## Phase 2 完成定义(Definition of Done)

- [ ] `uv run pytest` 全绿,~53 个 test cases(45 原 + 4 edge_tts + 4 file_sink + 5 orchestrator 新)
- [ ] `uv run ruff check src tests` 干净
- [ ] `uv run python -m g_chan` 启动日志包含 `tts enabled ...`
- [ ] Task 8.1 smoke test 拿到 ≥ 5KB 的 mp3,听起来像中文女声
- [ ] Task 9.2 在 Twitch 触发后,chat 收到文字 + `out/` 多一个 mp3
- [ ] Task 9.3 mp3 试听内容 = 本次回复文本
- [ ] Task 9.4 chat 文字回复速度不受 TTS 影响
