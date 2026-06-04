# G 酱 — Phase 3a Implementation Plan(WebSocket 后端基础设施)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 后端起一个 FastAPI + WebSocket 服务,Orchestrator 通过 `ViewerSink` 抽象把 `expression` / `motion` / `audio` 事件推给所有连接的浏览器客户端(Phase 3b 实现 viewer)。`FileAudioSink` 保留作 debug,新加 `WSViewerSink` 并行运行。

**Architecture:** 新增 `g_chan.server`(FastAPI app + ConnectionManager + WS endpoint)和 `g_chan.viewer_sink`(`ViewerSink` Protocol + `NoopViewerSink` + `WSViewerSink`)。`Orchestrator` 接受可选 `viewer_sink`,在 VIP 和 batch 两条路径里都调 push_expression / push_motion / push_audio。`__main__` 用 `uvicorn.Server.serve()` 跟 Twitch chat 并行跑(都是 asyncio task)。

**Tech Stack:** FastAPI + uvicorn[standard] + websockets(WS server)+ 已有 Phase 2 栈。前端 0 行(Phase 3b)。

**用户偏好:** 此项目不提交 git。所有 task 跳过 commit 步骤。

**Phase 3a 不做:** 实际渲染 Live2D(Phase 3b)、客户端消息处理(speak_done / ready / pong — Phase 3b)、热重载、HTTPS / WSS。

---

## WS 协议(本 plan 实现 server → client 一半;client → server 留给 3b)

```typescript
// Server → Client (Phase 3a 实现 push)
type ServerMessage =
  | { type: "expression", name: string }   // lowercase / "none"
  | { type: "motion",     name: string }   // lowercase / "none"
  | { type: "speak",      audio: string /* base64 mp3 */, format: "mp3", text: string }
  | { type: "ping" };

// Client → Server (Phase 3a 仅 log 收到的消息,3b 实际处理)
type ClientMessage =
  | { type: "ready", modelLoaded: boolean }
  | { type: "speak_done", text: string }
  | { type: "error", message: string }
  | { type: "pong" };
```

---

## 文件结构(Phase 3a 新增/修改)

```
新增:
  src/g_chan/server/
    __init__.py
    app.py              # create_app() — FastAPI app factory
    connection_manager.py  # ConnectionManager (维护 WS 客户端集合 + broadcast)
  src/g_chan/viewer_sink/
    __init__.py
    base.py             # ViewerSink Protocol + NoopViewerSink
    ws_sink.py          # WSViewerSink(用 ConnectionManager)
  tests/
    test_connection_manager.py
    test_ws_viewer_sink.py
    test_server_app.py   # WS endpoint 集成测试

修改:
  pyproject.toml                  # + fastapi, uvicorn[standard], websockets
  src/g_chan/config.py            # + ServerConfig
  config.example.yaml             # + server 块
  src/g_chan/orchestrator.py      # + viewer_sink 参数 + push_*
  src/g_chan/__main__.py          # 启动 uvicorn server alongside chat
  tests/conftest.py               # + FakeViewerSink
  tests/test_orchestrator.py      # 测试 viewer_sink 被调用
  tests/test_config.py            # 测试 ServerConfig
```

---

## Task 1: 加 FastAPI / uvicorn 依赖

**Files:**
- Modify: `pyproject.toml`

### Step 1.1: 在 `pyproject.toml` 的 `dependencies` 列表加 3 行

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
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "websockets>=12",
]
```

### Step 1.2: 同步依赖

```bash
uv sync
```
Expected: 安装 fastapi / uvicorn / websockets / starlette 等。输出末尾包含 `+ fastapi==...` 等。

### Step 1.3: 验证 import + httpx 用于测试

```bash
uv run python -c "import fastapi, uvicorn, websockets; from fastapi.testclient import TestClient; print('ok')"
```
Expected: `ok`.

### Step 1.4: 全套测试不退步

```bash
uv run pytest 2>&1 | tail -3
```
Expected: 111 passed.

## Self-Review

- [ ] 3 个依赖添加到 pyproject.toml
- [ ] uv sync 成功
- [ ] import smoke 通过
- [ ] 现有 111 tests 仍绿
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- 实际安装版本(fastapi / uvicorn / websockets)
- 任何 concerns

---

## Task 2: ServerConfig

**Files:**
- Modify: `src/g_chan/config.py`
- Modify: `config.example.yaml`
- Modify: `tests/test_config.py`

### Step 2.1: 写新测试,追加到 `tests/test_config.py` 末尾

```python
def test_loads_server_config(tmp_path, monkeypatch):
    monkeypatch.setenv("TWITCH_OAUTH", "x")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "x")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    cfg_path = write_yaml(tmp_path, """
twitch:
  channel: "alice"
  bot_username: "g_bot"
  trigger: "@G酱"
llm:
  provider: "gemini"
  model: "gemini-2.5-flash"
  temperature: 0.9
  max_tokens: 300
  timeout_s: 10
persona:
  prompt_file: "prompts/default.md"
stream_context:
  poll_interval_ms: 30000
server:
  enabled: true
  host: "0.0.0.0"
  port: 9000
  static_dir: "viewer/dist"
logging:
  level: "info"
  file: "logs/g.log"
""")
    cfg = load_config(cfg_path)
    assert cfg.server.enabled is True
    assert cfg.server.host == "0.0.0.0"
    assert cfg.server.port == 9000
    assert cfg.server.static_dir == "viewer/dist"


def test_server_defaults_when_section_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("TWITCH_OAUTH", "x")
    monkeypatch.setenv("TWITCH_CLIENT_ID", "x")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "x")
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    cfg_path = write_yaml(tmp_path, """
twitch:
  channel: "alice"
  bot_username: "g_bot"
  trigger: "@G酱"
llm:
  provider: "gemini"
  model: "gemini-2.5-flash"
  temperature: 0.9
  max_tokens: 300
  timeout_s: 10
persona:
  prompt_file: "prompts/default.md"
stream_context:
  poll_interval_ms: 30000
logging:
  level: "info"
  file: "logs/g.log"
""")
    cfg = load_config(cfg_path)
    assert cfg.server.enabled is True
    assert cfg.server.host == "localhost"
    assert cfg.server.port == 8765
    assert cfg.server.static_dir == "viewer/dist"
```

### Step 2.2: 跑测试,确认红

```bash
uv run pytest tests/test_config.py::test_loads_server_config tests/test_config.py::test_server_defaults_when_section_missing -v
```
Expected: FAIL with `AttributeError: 'AppConfig' object has no attribute 'server'`.

### Step 2.3: 在 `src/g_chan/config.py` 加 ServerConfig 类

放在 `Live2DConfig` 之后,`LoggingConfig` 之前:

```python
class ServerConfig(BaseModel):
    """WebSocket + 静态文件 server 配置(供 viewer 连接和加载)。

    enabled=False 时:
    - 不启动 FastAPI / uvicorn
    - Orchestrator 用 NoopViewerSink,push_* 全部 no-op
    - 适合纯 chat 模式不渲染 Live2D 的场景
    """
    enabled: bool = True
    host: str = "localhost"
    port: int = 8765
    # Phase 3b viewer 构建产物的目录;不存在 = 不挂载静态文件(只服 ws 端点)
    static_dir: str = "viewer/dist"
```

### Step 2.4: 修改 `AppConfig` 加 server 字段

```python
class AppConfig(BaseModel):
    twitch: TwitchConfig
    llm: LLMConfig
    persona: PersonaConfig
    stream_context: StreamContextConfig
    tts: TTSConfig = Field(default_factory=TTSConfig)
    interaction: InteractionConfig = Field(default_factory=InteractionConfig)
    live2d: Live2DConfig = Field(default_factory=Live2DConfig)
    server: ServerConfig = Field(default_factory=ServerConfig)
    logging: LoggingConfig
```

### Step 2.5: 跑测试,确认绿

```bash
uv run pytest tests/test_config.py -v
```
Expected: 全部 pass(原 + 2 新)。

### Step 2.6: 更新 `config.example.yaml`,在 `live2d:` 后、`logging:` 前加 server 段

```yaml
# WebSocket + 静态文件 server (Phase 3a:推 expression/motion/audio 给 viewer)
server:
  # 启用 → 起 FastAPI 跟 Twitch chat 并行跑
  # 禁用 → 纯 chat 模式,LLM 仍输出 expression/motion 但不推任何地方
  enabled: true
  host: "localhost"
  port: 8765
  # viewer 构建产物的目录,目录不存在则只服 /ws 端点不挂静态文件
  static_dir: "viewer/dist"
```

### Step 2.7: 全套测试 + ruff

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```
Expected: 113 passed, ruff All checks passed.

## Self-Review

- [ ] `ServerConfig` 4 字段全有默认值
- [ ] `AppConfig.server` 用 default_factory
- [ ] 2 个新测试 pass
- [ ] config.example.yaml 含 server 段
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 3: ConnectionManager(纯逻辑,无 FastAPI 依赖)

**Files:**
- Create: `src/g_chan/server/__init__.py`(空)
- Create: `src/g_chan/server/connection_manager.py`
- Create: `tests/test_connection_manager.py`

### Step 3.1: 创建空 init

```bash
mkdir -p src/g_chan/server
touch src/g_chan/server/__init__.py
```

### Step 3.2: 写测试 `tests/test_connection_manager.py`

```python
import pytest

from g_chan.server.connection_manager import ConnectionManager


class FakeWS:
    """模拟 FastAPI WebSocket 的最小接口(connect/disconnect/send_json)。"""
    def __init__(self, *, fail_on_send: bool = False):
        self.sent: list[dict] = []
        self.accepted = False
        self.fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        if self.fail_on_send:
            raise RuntimeError("simulated disconnect")
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_connect_adds_client_and_accepts():
    cm = ConnectionManager()
    ws = FakeWS()
    await cm.connect(ws)
    assert ws.accepted is True
    assert cm.client_count() == 1


@pytest.mark.asyncio
async def test_disconnect_removes_client():
    cm = ConnectionManager()
    ws = FakeWS()
    await cm.connect(ws)
    cm.disconnect(ws)
    assert cm.client_count() == 0


@pytest.mark.asyncio
async def test_disconnect_unknown_client_does_not_raise():
    cm = ConnectionManager()
    cm.disconnect(FakeWS())   # 不在 set 里
    # 不抛就行


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_clients():
    cm = ConnectionManager()
    a = FakeWS()
    b = FakeWS()
    await cm.connect(a)
    await cm.connect(b)
    payload = {"type": "expression", "name": "smile"}
    await cm.broadcast(payload)
    assert a.sent == [payload]
    assert b.sent == [payload]


@pytest.mark.asyncio
async def test_broadcast_drops_failing_clients():
    """send 抛异常的 client 会被 evict,不影响其他 client。"""
    cm = ConnectionManager()
    good = FakeWS()
    bad = FakeWS(fail_on_send=True)
    await cm.connect(good)
    await cm.connect(bad)
    await cm.broadcast({"type": "ping"})
    assert good.sent == [{"type": "ping"}]
    assert cm.client_count() == 1   # bad 被踢


@pytest.mark.asyncio
async def test_broadcast_with_no_clients_is_noop():
    cm = ConnectionManager()
    await cm.broadcast({"type": "ping"})   # 不抛
    assert cm.client_count() == 0
```

### Step 3.3: 跑测试,确认红

```bash
uv run pytest tests/test_connection_manager.py -v
```
Expected: ImportError.

### Step 3.4: 写 `src/g_chan/server/connection_manager.py`

```python
"""WebSocket 客户端连接管理 — 维护连接集合 + 广播。

实现上故意做成 protocol-loose:任何有 `accept` / `send_json` 方法的对象都能用,
这样测试可以用 FakeWS,生产用 FastAPI 的 WebSocket。
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

log = logging.getLogger(__name__)


class _WSLike(Protocol):
    async def accept(self) -> None: ...
    async def send_json(self, payload: Any) -> None: ...


class ConnectionManager:
    def __init__(self) -> None:
        self._clients: set[_WSLike] = set()

    async def connect(self, ws: _WSLike) -> None:
        await ws.accept()
        self._clients.add(ws)
        log.info("ws client connected, total=%d", len(self._clients))

    def disconnect(self, ws: _WSLike) -> None:
        self._clients.discard(ws)
        log.info("ws client disconnected, total=%d", len(self._clients))

    def client_count(self) -> int:
        return len(self._clients)

    async def broadcast(self, payload: dict) -> None:
        if not self._clients:
            return
        dead: list[_WSLike] = []
        for ws in self._clients:
            try:
                await ws.send_json(payload)
            except Exception as e:  # noqa: BLE001 — 客户端断开/网络异常都视为掉线
                log.debug("ws send failed, dropping client: %s", e)
                dead.append(ws)
        for ws in dead:
            self._clients.discard(ws)
        if dead:
            log.info("ws clients dropped: %d, remaining=%d",
                     len(dead), len(self._clients))
```

### Step 3.5: 跑测试,确认绿

```bash
uv run pytest tests/test_connection_manager.py -v
```
Expected: 6 tests pass.

### Step 3.6: 全套 + ruff

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```
Expected: 119 passed, ruff clean.

## Self-Review

- [ ] ConnectionManager 4 个方法(connect / disconnect / broadcast / client_count)
- [ ] broadcast 失败时 evict 客户端
- [ ] 用 Protocol 解耦 FastAPI,测试用 FakeWS
- [ ] 6 测试 pass
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 4: ViewerSink Protocol + NoopViewerSink

**Files:**
- Create: `src/g_chan/viewer_sink/__init__.py`
- Create: `src/g_chan/viewer_sink/base.py`

无单元测试 — Protocol + 空实现,行为太简单不值得单测;真正用法在 Task 5 / 7 测。

### Step 4.1: 创建目录 + 写文件

```bash
mkdir -p src/g_chan/viewer_sink
touch src/g_chan/viewer_sink/__init__.py
```

写 `src/g_chan/viewer_sink/base.py`:

```python
"""Viewer 事件 sink 抽象 — Orchestrator 推 expression / motion / audio 的统一出口。

实现:
- NoopViewerSink: server.enabled=False 时用,所有 push 都是 no-op
- WSViewerSink:  WebSocket 实现,广播给所有连接的 viewer
"""
from __future__ import annotations

from typing import Protocol

from g_chan.tts.base import TTSAudio


class ViewerSink(Protocol):
    """所有 push_* 都 fire-and-forget,任何异常应在实现内吞掉,不能影响 chat 路径。"""

    async def push_expression(self, name: str) -> None: ...

    async def push_motion(self, name: str) -> None: ...

    async def push_audio(self, audio: TTSAudio, *, user: str, text: str) -> None: ...


class NoopViewerSink:
    """server.enabled=False 时用 — 所有 push 不做任何事。"""

    async def push_expression(self, name: str) -> None:
        return

    async def push_motion(self, name: str) -> None:
        return

    async def push_audio(self, audio: TTSAudio, *, user: str, text: str) -> None:
        return
```

写 `src/g_chan/viewer_sink/__init__.py`:

```python
"""Viewer 事件 sink 包入口。"""
from g_chan.viewer_sink.base import NoopViewerSink, ViewerSink

__all__ = ["NoopViewerSink", "ViewerSink"]
```

### Step 4.2: 验证

```bash
uv run python -c "
from g_chan.viewer_sink import NoopViewerSink, ViewerSink
import asyncio
async def main():
    s = NoopViewerSink()
    await s.push_expression('smile')
    await s.push_motion('tap')
    print('ok')
asyncio.run(main())
"
```
Expected: `ok`.

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```
Expected: 119 passed,ruff clean.

## Self-Review

- [ ] ViewerSink Protocol 定义 3 个 push_* 方法
- [ ] NoopViewerSink 实现 3 个方法,全部 no-op
- [ ] __init__ 重导出
- [ ] smoke 通过
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 5: WSViewerSink

**Files:**
- Create: `src/g_chan/viewer_sink/ws_sink.py`
- Modify: `src/g_chan/viewer_sink/__init__.py` 重新导出
- Create: `tests/test_ws_viewer_sink.py`

### Step 5.1: 写测试 `tests/test_ws_viewer_sink.py`

```python
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
    """空字符串 = 维持当前状态,但 viewer 协议用 'none' 显式表达。"""
    cm = FakeCM()
    sink = WSViewerSink(cm)
    await sink.push_expression("")
    assert cm.broadcasts == [{"type": "expression", "name": "none"}]


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
    # base64 解码回原文
    assert base64.b64decode(msg["audio"]) == b"FAKEMP3BYTES"


@pytest.mark.asyncio
async def test_push_methods_swallow_broadcast_errors():
    """任何 broadcast 异常都不能往上抛,否则会冒进 orchestrator 影响 chat。"""
    class BrokenCM:
        async def broadcast(self, payload):
            raise RuntimeError("network down")

    sink = WSViewerSink(BrokenCM())
    # 三个 push 都不能抛
    await sink.push_expression("smile")
    await sink.push_motion("tap")
    await sink.push_audio(
        TTSAudio(data=b"x", format="mp3", voice="y", duration_ms=None),
        user="a", text="b",
    )
```

### Step 5.2: 跑测试,确认红

```bash
uv run pytest tests/test_ws_viewer_sink.py -v
```
Expected: ImportError.

### Step 5.3: 写 `src/g_chan/viewer_sink/ws_sink.py`

```python
"""WebSocket 实现的 ViewerSink — 通过 ConnectionManager 广播给所有连接的 viewer。"""
from __future__ import annotations

import base64
import logging
from typing import Protocol

from g_chan.tts.base import TTSAudio

log = logging.getLogger(__name__)


class _CMLike(Protocol):
    async def broadcast(self, payload: dict) -> None: ...


def _name_or_none(name: str) -> str:
    """空字符串规范化为 'none' — viewer 协议显式表达"维持当前"。"""
    return name if name else "none"


class WSViewerSink:
    def __init__(self, connection_manager: _CMLike):
        self._cm = connection_manager

    async def push_expression(self, name: str) -> None:
        try:
            await self._cm.broadcast({"type": "expression", "name": _name_or_none(name)})
        except Exception as e:  # noqa: BLE001
            log.warning("WSViewerSink push_expression failed: %s", e)

    async def push_motion(self, name: str) -> None:
        try:
            await self._cm.broadcast({"type": "motion", "name": _name_or_none(name)})
        except Exception as e:  # noqa: BLE001
            log.warning("WSViewerSink push_motion failed: %s", e)

    async def push_audio(self, audio: TTSAudio, *, user: str, text: str) -> None:
        try:
            await self._cm.broadcast({
                "type": "speak",
                "audio": base64.b64encode(audio.data).decode("ascii"),
                "format": audio.format,
                "text": text,
            })
        except Exception as e:  # noqa: BLE001
            log.warning("WSViewerSink push_audio failed (user=%s): %s", user, e)
```

### Step 5.4: 更新 `src/g_chan/viewer_sink/__init__.py` 重新导出

```python
"""Viewer 事件 sink 包入口。"""
from g_chan.viewer_sink.base import NoopViewerSink, ViewerSink
from g_chan.viewer_sink.ws_sink import WSViewerSink

__all__ = ["NoopViewerSink", "ViewerSink", "WSViewerSink"]
```

### Step 5.5: 跑测试,确认绿

```bash
uv run pytest tests/test_ws_viewer_sink.py -v
```
Expected: 5 tests pass.

### Step 5.6: 全套 + ruff

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```
Expected: 124 passed, ruff clean.

## Self-Review

- [ ] WSViewerSink 实现 3 个 push_* 方法
- [ ] 空字符串规范化为 "none"
- [ ] base64 编码音频
- [ ] 所有 broadcast 异常被吞,不冒泡
- [ ] 5 测试 pass
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 6: FastAPI app + WS endpoint

**Files:**
- Create: `src/g_chan/server/app.py`
- Create: `tests/test_server_app.py`

### Step 6.1: 写测试 `tests/test_server_app.py`

```python
from fastapi.testclient import TestClient

from g_chan.server.app import create_app
from g_chan.server.connection_manager import ConnectionManager


def test_health_endpoint_returns_client_count():
    cm = ConnectionManager()
    app = create_app(cm, static_dir="non-existent-dir")
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["clients"] == 0


def test_ws_endpoint_accepts_connection_and_increments_count():
    cm = ConnectionManager()
    app = create_app(cm, static_dir="non-existent-dir")
    with TestClient(app) as client:
        # 同步 health
        assert client.get("/health").json()["clients"] == 0
        with client.websocket_connect("/ws") as ws:
            # 连上后端会 increment 计数
            r = client.get("/health")
            assert r.json()["clients"] == 1
    # 出 context 后会自动 disconnect


def test_ws_endpoint_logs_client_messages_without_crash():
    """client 发任何消息 server 都不应崩(Phase 3a 仅 log)。"""
    cm = ConnectionManager()
    app = create_app(cm, static_dir="non-existent-dir")
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "ready", "modelLoaded": True})
            # server 收到后内部 log,不回响应,连接不断


def test_ws_broadcasts_reach_connected_client():
    """从 server 端 broadcast 应能被客户端收到。"""
    cm = ConnectionManager()
    app = create_app(cm, static_dir="non-existent-dir")
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            # TestClient 把 connect 同步成功后,cm 里应该有 1 个 client
            # 直接调 cm.broadcast(同 event loop)然后客户端 receive
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                cm.broadcast({"type": "expression", "name": "smile"})
            )
            msg = ws.receive_json()
            assert msg == {"type": "expression", "name": "smile"}


def test_app_skips_static_mount_when_dir_missing():
    """static_dir 不存在 → 不挂 / 路由,只暴露 /health /ws。"""
    cm = ConnectionManager()
    app = create_app(cm, static_dir="totally/does/not/exist")
    with TestClient(app) as client:
        # / 路径返回 404(不是 500),因为没挂 StaticFiles
        r = client.get("/")
        assert r.status_code == 404
```

### Step 6.2: 跑测试,确认红

```bash
uv run pytest tests/test_server_app.py -v
```
Expected: ImportError.

### Step 6.3: 写 `src/g_chan/server/app.py`

```python
"""FastAPI app factory — /ws + /health + 可选 / (静态 viewer 产物)。"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles

from g_chan.server.connection_manager import ConnectionManager

log = logging.getLogger(__name__)


def create_app(
    connection_manager: ConnectionManager,
    *,
    static_dir: str | None = None,
) -> FastAPI:
    """构造 FastAPI app。

    static_dir 不存在时:不挂 StaticFiles,/ 路径会 404(正常,只服 /health + /ws)。
    """
    app = FastAPI(title="g_chan viewer server")

    @app.get("/health")
    async def health():
        return {"ok": True, "clients": connection_manager.client_count()}

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await connection_manager.connect(websocket)
        try:
            while True:
                # Phase 3a 仅 log client → server 消息,Phase 3b 处理 speak_done / ready 等
                msg = await websocket.receive_json()
                log.debug("ws client → server: %r", msg)
        except WebSocketDisconnect:
            log.debug("ws client disconnected cleanly")
        except Exception as e:  # noqa: BLE001
            log.warning("ws endpoint loop error: %s", e)
        finally:
            connection_manager.disconnect(websocket)

    # 静态文件挂在 / — Phase 3b 把 viewer/dist 编译产物放进去
    if static_dir and Path(static_dir).is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="viewer")
        log.info("static viewer mounted at / from %s", static_dir)
    else:
        log.info("static_dir %r not found, /ws + /health only", static_dir)

    return app
```

### Step 6.4: 跑测试,确认绿

```bash
uv run pytest tests/test_server_app.py -v
```
Expected: 5 tests pass.

### Step 6.5: 全套 + ruff

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```
Expected: 129 passed, ruff clean.

## Self-Review

- [ ] create_app 返回 FastAPI 实例
- [ ] /health 暴露 clients 数
- [ ] /ws 端点正确 accept + disconnect
- [ ] static_dir 不存在时不挂载(不崩)
- [ ] 5 测试 pass
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 7: Orchestrator 集成 viewer_sink

**Files:**
- Modify: `src/g_chan/orchestrator.py`
- Modify: `tests/conftest.py`(+ FakeViewerSink)
- Modify: `tests/test_orchestrator.py`(+ 测试 push_* 被调用)

### Step 7.1: 在 `tests/conftest.py` 末尾追加 `FakeViewerSink`

```python
from g_chan.viewer_sink import ViewerSink as _ViewerSink  # type: ignore[attr-defined]


class FakeViewerSink:
    """记录所有 push_* 调用,供 orchestrator 测试断言。"""
    def __init__(self):
        self.expressions: list[str] = []
        self.motions: list[str] = []
        self.audios: list[tuple[bytes, str, str]] = []   # (audio_data, user, text)

    async def push_expression(self, name: str) -> None:
        self.expressions.append(name)

    async def push_motion(self, name: str) -> None:
        self.motions.append(name)

    async def push_audio(self, audio, *, user: str, text: str) -> None:
        self.audios.append((audio.data, user, text))
```

### Step 7.2: 修改 `src/g_chan/orchestrator.py`

在 `__init__` 加 `viewer_sink: ViewerSink | None = None` 参数(放在 audio_sink 之后,now_ms 之前):

找到 imports 区,加:
```python
from g_chan.viewer_sink import NoopViewerSink, ViewerSink
```

`__init__` 签名加参数:
```python
        ...
        tts: TTSEngine | None = None,
        audio_sink: AudioSink | None = None,
        viewer_sink: ViewerSink | None = None,   # NEW
        now_ms: Callable[[], float] = _default_now_ms,
        random_fn: Callable[[], float] = random.random,
    ):
```

`__init__` body 加:
```python
        self._viewer_sink: ViewerSink = viewer_sink or NoopViewerSink()
```

修改 `_handle_priority`(VIP 路径)— 在 `await self._do_tts(...)` 那段之前 push expression + motion,_do_tts 之后 push audio:

找到 `_handle_priority` 末尾这段:

```python
        expression, motion = self._apply_frequency(reply)
        log.info(...)
        await self._do_tts(reply.text, language=reply.language, user=msg.user)
        chat_body = (...)
        await self._chat.send(f"@{msg.user} {chat_body}")
```

改为:

```python
        expression, motion = self._apply_frequency(reply)
        log.info(
            "vip reply: user=%s mood=%s lang=%s text=%r kaomoji=%r expr=%r motion=%r",
            msg.user, reply.mood, reply.language, reply.text, reply.kaomoji,
            expression, motion,
        )

        # push expression / motion 给 viewer(并发触发,不等 viewer 回应)
        await self._viewer_sink.push_expression(expression)
        await self._viewer_sink.push_motion(motion)

        # TTS → 同时写文件(如启用)+ 推给 viewer
        await self._do_tts(reply.text, language=reply.language, user=msg.user, text=reply.text)
        chat_body = (
            f"{reply.text} {reply.kaomoji}".strip() if reply.kaomoji else reply.text
        )
        await self._chat.send(f"@{msg.user} {chat_body}")
```

类似改 `_process_batch`(batch 路径)— 找到:

```python
        expression, motion = self._apply_frequency(reply)
        log.info(...)
        await self._do_tts(reply.text, language=reply.language, user="batch")
        chat_body = (...)
        await self._chat.send(chat_body)
```

改为:

```python
        expression, motion = self._apply_frequency(reply)
        log.info(
            "batch reply: batch_size=%d mood=%s lang=%s text=%r kaomoji=%r expr=%r motion=%r",
            len(messages), reply.mood, reply.language, reply.text, reply.kaomoji,
            expression, motion,
        )

        await self._viewer_sink.push_expression(expression)
        await self._viewer_sink.push_motion(motion)

        await self._do_tts(reply.text, language=reply.language, user="batch", text=reply.text)
        chat_body = (
            f"{reply.text} {reply.kaomoji}".strip() if reply.kaomoji else reply.text
        )
        await self._chat.send(chat_body)
```

修改 `_do_tts` 签名加 `text`,在写 audio_sink 后 push 给 viewer:

找到 `_do_tts`:

```python
    async def _do_tts(self, text: str, *, language: Language, user: str) -> None:
        if self._tts is None or self._audio_sink is None:
            return
        ...
```

改为:

```python
    async def _do_tts(
        self,
        text: str,
        *,
        language: Language,
        user: str,
        text_for_viewer: str | None = None,
    ) -> None:
        """合成音频:写 audio_sink(如存在)+ push 给 viewer_sink。

        text_for_viewer:viewer 看到的原始文字(用于显示同步)。默认 = text 本身。
        """
        if self._tts is None:
            return
        if not text.strip():
            return
        try:
            audio = await self._tts.synthesize(text, language=language)
        except TTSError as e:
            log.warning("tts synth failed: %s", e)
            return
        except Exception as e:  # noqa: BLE001
            log.exception("tts synth crashed: %s", e)
            return

        # 写文件(可选 — audio_sink 没传就跳过)
        if self._audio_sink is not None:
            try:
                await self._audio_sink.write(audio, user=user)
            except Exception as e:  # noqa: BLE001
                log.warning("audio sink write failed: %s", e)

        # 推给 viewer(NoopViewerSink 时是 no-op)
        await self._viewer_sink.push_audio(
            audio, user=user, text=text_for_viewer or text,
        )
```

注:之前 `_do_tts` 要求两个 sink 都存在才执行,现在只要 tts 存在就执行,audio_sink 可选。viewer_sink 总是 push(可能是 NoopViewerSink no-op)。

**所有调用 `_do_tts` 的地方,改为传 `text=reply.text` 作为 `text_for_viewer`(实际上调用方已经有了 reply.text,不用改)。**

哦,看仔细 — 我上面把 `_do_tts(reply.text, ..., user=...)` 改成 `_do_tts(reply.text, ..., user=..., text=reply.text)`,这里 `text` 关键字会冲突首个 positional 参数。需要改成 `text_for_viewer=reply.text` 或者把第一个参数也命名:

修正 `_handle_priority`:
```python
        await self._do_tts(reply.text, language=reply.language, user=msg.user)
```
(不传 text_for_viewer,默认用 text 本身。)

修正 `_process_batch`:
```python
        await self._do_tts(reply.text, language=reply.language, user="batch")
```

`_do_tts` 内部 `text_for_viewer or text` 会 fallback 到 text。

回退上面的"改为"段:`_handle_priority` 和 `_process_batch` 不要加 `text=reply.text`,保持原参数(只调用 `_do_tts(reply.text, language=..., user=...)`)。`_do_tts` 自己默认 text_for_viewer = text.

### Step 7.3: 改 `tests/test_orchestrator.py` 的 `_build_orch` 加 viewer_sink 参数

找到 `_build_orch`,加 `viewer_sink=None` 默认参数:

```python
def _build_orch(
    *, chat, llm, clock,
    vip_window_ms=0,
    batch_window_s=2,
    batch_cooldown_ms=0,
    buffer_size=10,
    tts=None, audio_sink=None,
    viewer_sink=None,                # NEW
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
        viewer_sink=viewer_sink,     # NEW
        now_ms=clock,
        random_fn=random_fn,
        **kw,
    )
```

### Step 7.4: 在 `tests/test_orchestrator.py` 末尾追加 3 个 viewer_sink 测试

```python
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
                                expression="smile", motion="none")
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
    assert viewer.motions == ["none"]
    assert len(viewer.audios) == 1
    _, user, _ = viewer.audios[0]
    assert user == "batch"


@pytest.mark.asyncio
async def test_works_without_viewer_sink_passed():
    """viewer_sink=None → Orchestrator 用 NoopViewerSink,不崩。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊", mood="happy", expression="smile")
    clock = FakeClock()
    orch = _build_orch(chat=chat, llm=llm, clock=clock)   # 没 viewer_sink
    orch.wire()
    await chat.emit("alice", "嗨", is_priority=True)
    await asyncio.sleep(0.05)
    assert chat.sent == ["@alice 好啊"]
```

### Step 7.5: 跑 orchestrator 测试

```bash
uv run pytest tests/test_orchestrator.py -v
```
Expected: 全 pass(原 16 + 新 3 = 19)。

### Step 7.6: 全套 + ruff

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```
Expected: 132 passed, ruff clean.

## Self-Review

- [ ] Orchestrator 接 viewer_sink=None,默认 NoopViewerSink
- [ ] _handle_priority 和 _process_batch 都 push_expression/push_motion
- [ ] _do_tts 改为 audio_sink 可选,viewer_sink 总 push
- [ ] FakeViewerSink 记录 expressions / motions / audios
- [ ] 3 个新测试 pass
- [ ] 全套 132 passed
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- 测试结果
- 任何 concerns

---

## Task 8: __main__ 启动 uvicorn 跟 chat 并行

**Files:**
- Modify: `src/g_chan/__main__.py`

### Step 8.1: 在 imports 区添加

```python
import uvicorn

from g_chan.server.app import create_app
from g_chan.server.connection_manager import ConnectionManager
from g_chan.viewer_sink import NoopViewerSink, ViewerSink, WSViewerSink
```

### Step 8.2: 在 `amain` 函数里,**chat 装配之前**(Orchestrator 之前)装配 viewer_sink + server

找到当前 `tts_engine` 装配的代码块之后,`orch = Orchestrator(...)` 之前,插入:

```python
    # Viewer sink + WebSocket server (Phase 3a)
    viewer_sink: ViewerSink
    server_task: asyncio.Task | None = None
    if cfg.server.enabled:
        conn_manager = ConnectionManager()
        viewer_sink = WSViewerSink(conn_manager)
        app = create_app(conn_manager, static_dir=cfg.server.static_dir)
        server_cfg = uvicorn.Config(
            app=app,
            host=cfg.server.host,
            port=cfg.server.port,
            log_level=cfg.logging.level,
            access_log=False,   # 减少日志噪音
        )
        server = uvicorn.Server(server_cfg)
        server_task = asyncio.create_task(server.serve())
        log.info("ws server enabled at ws://%s:%d/ws",
                 cfg.server.host, cfg.server.port)
    else:
        viewer_sink = NoopViewerSink()
        log.info("ws server disabled — viewer_sink is no-op")
```

### Step 8.3: Orchestrator 调用加 viewer_sink

把:
```python
    orch = Orchestrator(
        chat=chat, llm=llm, persona=persona, stream_ctx=sctx,
        vip_window_ms=cfg.interaction.vip_window_ms,
        ...
        tts=tts_engine,
        audio_sink=audio_sink,
    )
```

改成:
```python
    orch = Orchestrator(
        chat=chat, llm=llm, persona=persona, stream_ctx=sctx,
        vip_window_ms=cfg.interaction.vip_window_ms,
        ...
        tts=tts_engine,
        audio_sink=audio_sink,
        viewer_sink=viewer_sink,
    )
```

### Step 8.4: 在 `finally` 块加 server_task.cancel()

找到 `finally` 块:
```python
    finally:
        if polling is not None:
            polling.cancel()
        await chat.disconnect()
    return 0
```

改成:
```python
    finally:
        if polling is not None:
            polling.cancel()
        if server_task is not None:
            server_task.cancel()
        await chat.disconnect()
    return 0
```

### Step 8.5: smoke check — 启动失败应是 config 缺,不是 import

```bash
mv config.yaml config.yaml.bak 2>/dev/null
uv run python -m g_chan 2>&1 | tail -5
mv config.yaml.bak config.yaml 2>/dev/null
```
Expected: `FileNotFoundError: [Errno 2] No such file or directory: 'config.yaml'`.

### Step 8.6: 全套测试 + ruff

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```
Expected: 132 passed, ruff clean.

## Self-Review

- [ ] __main__.py 启动 uvicorn.Server.serve() 作为 asyncio task
- [ ] viewer_sink 注入 Orchestrator
- [ ] cfg.server.enabled=False 时 viewer_sink = NoopViewerSink
- [ ] finally 块 cancel server_task
- [ ] smoke check 报 FileNotFoundError
- [ ] 132 passed
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- smoke 错误信息
- 任何 concerns

---

## Task 9: 端到端手动验证(用户)

**Files:** 无。

### Step 9.1: 确认本地 config.yaml 含 server 块

参考 `config.example.yaml`,在 `config.yaml` 加:

```yaml
server:
  enabled: true
  host: "localhost"
  port: 8765
  static_dir: "viewer/dist"
```

### Step 9.2: 启动 bot

```bash
uv run python -m g_chan
```

启动日志应包含:
- `ws server enabled at ws://localhost:8765/ws`
- `static_dir 'viewer/dist' not found, /ws + /health only`(Phase 3b 还没写)
- 已有的其他启动日志

### Step 9.3: 验证 /health 端点

新开一个终端:
```bash
curl http://localhost:8765/health
```
Expected: `{"ok": true, "clients": 0}`

### Step 9.4: 连 WS 验证 push 事件

新开终端,用 wscat 或 websocat 连:

```bash
# 如果没装,先 brew install websocat
websocat ws://localhost:8765/ws
```

(连上后 /health 应显示 `clients=1`)

让朋友/小号在 Twitch 触发 `@G酱 嗨`(或主播自己 mod 身份触发)→ websocat 终端应实时打印 3 条 JSON:

```
{"type":"expression","name":"smile"}
{"type":"motion","name":"none"}
{"type":"speak","audio":"<base64>","format":"mp3","text":"哈喽"}
```

### Step 9.5: 验证多客户端 broadcast

第三个终端再连一次 websocat → /health 显示 `clients=2`,触发一次,两个 websocat 都收到相同 3 条消息。

### Step 9.6: 验证 client disconnect 不影响 server

Ctrl+C 关掉一个 websocat → /health 显示 `clients=1`,另一个 websocat 仍能收消息。

---

## Phase 3a 完成定义

- [ ] `uv run pytest` 全绿(132 tests)
- [ ] `uv run ruff check src tests` 干净
- [ ] `uv run python -m g_chan` 启动后 `curl http://localhost:8765/health` 返回 `{"ok":true,"clients":0}`
- [ ] websocat 连上,Twitch chat 触发后实时收到 expression/motion/speak 3 条 JSON
- [ ] 多 client 时全部广播到
- [ ] client 断开不影响 server

Phase 3b 在 viewer 端实际渲染 Live2D + 收这些事件 → 角色动起来。
