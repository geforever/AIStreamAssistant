# G 酱 — Phase 1 Implementation Plan(文本对话跑通)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Twitch 直播间发送 `@G酱 你在玩啥`,bot 调用 LLM 返回带 G 酱人设的文字回复(并能感知当前直播频道游戏/标题)。无 TTS、无 Live2D。

**Architecture:** 单 Python 进程,asyncio 全异步。`twitchio` 接 IRC,`twitchAPI` 拉 Helix 取频道信息,`google-genai` 调 Gemini,`pydantic-settings` 加载 `config.yaml` + `.env`。组件通过 ABC 接口解耦,LLM/Chat/StreamContext 在测试中用 Fake 替换。

**Tech Stack:** Python 3.11+ · uv(包管理 + venv)· twitchio 3.x · twitchAPI 4.x · google-genai · pydantic 2 / pydantic-settings 2 · PyYAML · pytest + pytest-asyncio · rich(日志)

**用户偏好:** 此项目不提交 git。所有 task 跳过 commit 步骤,只做"写测试 → 跑红 → 实现 → 跑绿"。

**Phase 1 不做:** TTS、Live2D、WebSocket 服务、其他 LLM provider(Claude/OpenAI/Qwen 留接口、抛 NotImplementedError)、短期记忆、热重载。

---

## 文件结构(Phase 1 创建/修改的文件)

```
Gちゃん/                                  (项目根)
├── pyproject.toml                         # 依赖 + 工具配置
├── .python-version                        # 3.11
├── .gitignore
├── .env.example                           # API key 占位
├── config.example.yaml                    # 配置模板
├── README.md                              # 启动方法
├── prompts/
│   ├── default.md                         # G 酱默认人设
│   └── output_format.md                   # mood 输出规范
├── src/g_chan/
│   ├── __init__.py
│   ├── __main__.py                        # python -m g_chan 入口
│   ├── config.py                          # pydantic-settings
│   ├── rate_limiter.py                    # 全局窗口限流
│   ├── logging_setup.py                   # rich + file handler
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── base.py                        # ABC + dataclass + 异常 + parse_mood
│   │   ├── factory.py                     # from_config(cfg.llm) → LLMProvider
│   │   └── gemini.py                      # 唯一实现
│   ├── persona/
│   │   ├── __init__.py
│   │   ├── loader.py                      # PersonaLoader
│   │   └── stream_context.py              # StreamContextProvider (Helix 轮询)
│   ├── chat/
│   │   ├── __init__.py
│   │   ├── base.py                        # ChatAdapter ABC + ChatMessage
│   │   └── twitch.py                      # TwitchChatAdapter (twitchio)
│   └── orchestrator.py                    # 把上面所有东西串起来
└── tests/
    ├── __init__.py
    ├── conftest.py                        # 共用 fixtures + Fakes
    ├── test_rate_limiter.py
    ├── test_parse_mood.py
    ├── test_persona_loader.py
    ├── test_stream_context.py
    ├── test_llm_factory.py
    └── test_orchestrator.py
```

**模块依赖方向(单向,无循环):**

```
__main__ → orchestrator → { chat, llm, persona, rate_limiter, config, logging_setup }
                                            ↑
                                            persona.stream_context 独立运行(后台 task)
chat、llm、persona 之间互不依赖,只共享 config 中的 dataclass。
```

---

## Task 1: Project Bootstrap(venv + 项目骨架)

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version`
- Create: `.gitignore`
- Create: `.env.example`
- Create: `config.example.yaml`
- Create: `README.md`
- Create: `src/g_chan/__init__.py`(空)
- Create: `tests/__init__.py`(空)
- Create: `prompts/`(空目录)

- [ ] **Step 1.1: 确认 uv 已安装**

Run: `uv --version`
Expected: 输出 `uv 0.x.x`(任何 ≥ 0.4 的版本)。
若提示 not found:`brew install uv`(macOS)。

- [ ] **Step 1.2: 创建 `.python-version`**

```
3.11
```

- [ ] **Step 1.3: 创建 `pyproject.toml`**

```toml
[project]
name = "g-chan"
version = "0.1.0"
description = "G酱 (Gちゃん) — Twitch AI VTuber bot"
requires-python = ">=3.11"
dependencies = [
    "twitchio>=3.0.0",
    "twitchapi>=4.0.0",
    "google-genai>=0.3.0",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "rich>=13.7",
]

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.12",
    "ruff>=0.4",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/g_chan"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
pythonpath = ["src"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

- [ ] **Step 1.4: 创建 `.gitignore`**

```
__pycache__/
*.py[cod]
*$py.class
.venv/
.env
config.yaml
logs/
*.log
.pytest_cache/
.ruff_cache/
dist/
build/
*.egg-info/
.DS_Store
```

- [ ] **Step 1.5: 创建 `.env.example`**

```
# Twitch
TWITCH_OAUTH=oauth:xxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWITCH_CLIENT_ID=xxxxxxxxxxxxxxxxxxxxxxxxxx
TWITCH_CLIENT_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxx

# LLM
GEMINI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
# CLAUDE_API_KEY=
# OPENAI_API_KEY=
# DASHSCOPE_API_KEY=
```

- [ ] **Step 1.6: 创建 `config.example.yaml`**

```yaml
twitch:
  channel: "your_channel_name"
  bot_username: "g_chan_bot"
  trigger: "@G酱"

rate_limit:
  global_window_ms: 5000
  busy_reply: "G酱我被你们搞的好晕啊XD"

llm:
  provider: "gemini"             # gemini | claude | openai | qwen (Phase 1 仅 gemini)
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
  level: "info"                  # debug | info | warn | error
  file: "logs/g-chan.log"
```

- [ ] **Step 1.7: 创建 `README.md`**

````markdown
# G酱 (Gちゃん)

Twitch AI VTuber chatbot — Phase 1: 文本对话。

## 启动(开发模式)

```bash
# 一次性
uv sync                              # 创建 .venv 并安装依赖
cp .env.example .env                  # 填入真实 API key
cp config.example.yaml config.yaml    # 改 channel 名

# 跑测试
uv run pytest -v

# 启动 bot
uv run python -m g_chan
```
````

- [ ] **Step 1.8: 创建目录骨架**

```bash
mkdir -p src/g_chan/llm src/g_chan/persona src/g_chan/chat
mkdir -p tests prompts logs
touch src/g_chan/__init__.py
touch src/g_chan/llm/__init__.py
touch src/g_chan/persona/__init__.py
touch src/g_chan/chat/__init__.py
touch tests/__init__.py
```

- [ ] **Step 1.9: 创建 venv 并安装依赖**

```bash
uv sync
```

Expected:
- 创建 `.venv/`
- 安装所有 dependencies + dev deps
- 输出 `Resolved X packages` + `Installed X packages`

- [ ] **Step 1.10: 验证 venv 可用**

```bash
uv run python -c "import twitchio, google.genai, pydantic; print('ok')"
```

Expected: 输出 `ok`。任何 ImportError 必须先解决再继续。

---

## Task 2: Config Loader(pydantic-settings + 环境变量替换)

**Files:**
- Create: `src/g_chan/config.py`
- Create: `tests/test_config.py`

`config.yaml` 含 `${ENV_VAR}` 占位时,加载阶段从环境变量替换(由 dotenv 注入)。校验失败 → 启动期立刻 raise。

- [ ] **Step 2.1: 写测试 `tests/test_config.py`**

```python
import os
import pytest
from pathlib import Path
from g_chan.config import load_config, AppConfig


def write_yaml(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "config.yaml"
    p.write_text(text, encoding="utf-8")
    return p


def test_loads_valid_config(tmp_path, monkeypatch):
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
logging:
  level: "info"
  file: "logs/g.log"
""")
    cfg = load_config(cfg_path)
    assert isinstance(cfg, AppConfig)
    assert cfg.twitch.channel == "alice"
    assert cfg.twitch.oauth_token == "oauth:abc"
    assert cfg.llm.api_key == "gkey"
    assert cfg.rate_limit.global_window_ms == 5000


def test_missing_env_var_fails(tmp_path):
    # 不设置任何 env
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
    with pytest.raises(Exception):  # pydantic ValidationError or KeyError
        load_config(cfg_path)


def test_invalid_provider_rejected(tmp_path, monkeypatch):
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
  provider: "lolwut"
  model: "x"
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
    with pytest.raises(Exception):
        load_config(cfg_path)
```

- [ ] **Step 2.2: 跑测试,确认红**

```bash
uv run pytest tests/test_config.py -v
```
Expected: 全部 FAIL,提示 `cannot import name 'load_config' from 'g_chan.config'`。

- [ ] **Step 2.3: 写 `src/g_chan/config.py`**

```python
"""配置加载:YAML + .env,pydantic 校验。"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

LLMProviderName = Literal["gemini", "claude", "openai", "qwen"]


class TwitchConfig(BaseModel):
    channel: str
    bot_username: str
    trigger: str = "@G酱"
    oauth_token: str = Field(default="", description="from $TWITCH_OAUTH")
    client_id: str = Field(default="", description="from $TWITCH_CLIENT_ID")
    client_secret: str = Field(default="", description="from $TWITCH_CLIENT_SECRET")


class RateLimitConfig(BaseModel):
    global_window_ms: int = 5000
    busy_reply: str = "G酱我被你们搞的好晕啊XD"


class LLMConfig(BaseModel):
    provider: LLMProviderName
    model: str
    temperature: float = 0.9
    max_tokens: int = 300
    timeout_s: float = 10.0
    api_key: str = Field(default="", description="from $<PROVIDER>_API_KEY")


class PersonaConfig(BaseModel):
    prompt_file: str = "prompts/default.md"
    include_stream_context: bool = True


class StreamContextConfig(BaseModel):
    poll_interval_ms: int = 30000


class LoggingConfig(BaseModel):
    level: Literal["debug", "info", "warning", "error"] = "info"
    file: str = "logs/g-chan.log"


class AppConfig(BaseModel):
    twitch: TwitchConfig
    rate_limit: RateLimitConfig
    llm: LLMConfig
    persona: PersonaConfig
    stream_context: StreamContextConfig
    logging: LoggingConfig


_ENV_KEYS_FOR_PROVIDER = {
    "gemini": "GEMINI_API_KEY",
    "claude": "CLAUDE_API_KEY",
    "openai": "OPENAI_API_KEY",
    "qwen":   "DASHSCOPE_API_KEY",
}


def load_config(path: str | Path) -> AppConfig:
    """加载 config.yaml,注入环境变量(由 .env 提供),返回校验过的 AppConfig。"""
    load_dotenv()  # 加载 .env(如存在)
    text = Path(path).read_text(encoding="utf-8")
    data = yaml.safe_load(text)

    # 注入 secrets(不放进 yaml,避免误提交)
    twitch = data.setdefault("twitch", {})
    twitch["oauth_token"]   = _require_env("TWITCH_OAUTH")
    twitch["client_id"]     = _require_env("TWITCH_CLIENT_ID")
    twitch["client_secret"] = _require_env("TWITCH_CLIENT_SECRET")

    llm = data.setdefault("llm", {})
    provider = llm.get("provider")
    env_key = _ENV_KEYS_FOR_PROVIDER.get(provider)
    if env_key is None:
        raise ValueError(f"unknown llm.provider: {provider!r}")
    llm["api_key"] = _require_env(env_key)

    return AppConfig.model_validate(data)


def _require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(f"missing environment variable: {name}")
    return v
```

- [ ] **Step 2.4: 跑测试,确认绿**

```bash
uv run pytest tests/test_config.py -v
```
Expected: 3 passed。

---

## Task 3: Rate Limiter

**Files:**
- Create: `src/g_chan/rate_limiter.py`
- Create: `tests/test_rate_limiter.py`

- [ ] **Step 3.1: 写测试 `tests/test_rate_limiter.py`**

```python
import time
from g_chan.rate_limiter import RateLimiter


def test_first_acquire_succeeds():
    rl = RateLimiter(window_ms=1000)
    assert rl.try_acquire() is True


def test_second_acquire_within_window_fails():
    rl = RateLimiter(window_ms=1000)
    rl.try_acquire()
    assert rl.try_acquire() is False


def test_acquire_succeeds_after_window(monkeypatch):
    # 用可控时间避免真 sleep
    now = [1000.0]  # ms
    def fake_now_ms() -> float:
        return now[0]

    rl = RateLimiter(window_ms=1000, now_ms=fake_now_ms)
    assert rl.try_acquire() is True
    now[0] += 500
    assert rl.try_acquire() is False
    now[0] += 600  # 累计 1100ms 后
    assert rl.try_acquire() is True


def test_zero_window_always_allows():
    rl = RateLimiter(window_ms=0)
    assert rl.try_acquire() is True
    assert rl.try_acquire() is True
```

- [ ] **Step 3.2: 跑测试,确认红**

```bash
uv run pytest tests/test_rate_limiter.py -v
```
Expected: ImportError。

- [ ] **Step 3.3: 写 `src/g_chan/rate_limiter.py`**

```python
"""全局窗口限流:单一时间窗口,无人粒度。"""
from __future__ import annotations

import time
from typing import Callable


def _default_now_ms() -> float:
    return time.monotonic() * 1000


class RateLimiter:
    def __init__(self, window_ms: int, *, now_ms: Callable[[], float] = _default_now_ms):
        self.window_ms = window_ms
        self._last_fire_at: float = -float("inf")
        self._now_ms = now_ms

    def try_acquire(self) -> bool:
        if self.window_ms <= 0:
            return True
        now = self._now_ms()
        if now - self._last_fire_at < self.window_ms:
            return False
        self._last_fire_at = now
        return True
```

- [ ] **Step 3.4: 跑测试,确认绿**

```bash
uv run pytest tests/test_rate_limiter.py -v
```
Expected: 4 passed。

---

## Task 4: Mood Parsing(LLM 输出解析)

**Files:**
- Create: `src/g_chan/llm/base.py`(本任务先建,只放解析 + 类型)
- Create: `tests/test_parse_mood.py`

- [ ] **Step 4.1: 写测试 `tests/test_parse_mood.py`**

```python
import pytest
from g_chan.llm.base import parse_mood


@pytest.mark.parametrize("raw,expected_text,expected_mood", [
    ("哼,本小姐才没有 [mood:tsundere]", "哼,本小姐才没有", "tsundere"),
    ("好开心呀~ [mood:happy]",          "好开心呀~",         "happy"),
    ("[mood:sad]",                       "",                   "sad"),
    ("好开心 [mood:happy]   ",           "好开心",             "happy"),
    ("emoji 测试 (=ω=) [mood:shy]",      "emoji 测试 (=ω=)",   "shy"),
])
def test_parses_valid_mood(raw, expected_text, expected_mood):
    text, mood = parse_mood(raw)
    assert text == expected_text
    assert mood == expected_mood


def test_missing_mood_defaults_to_happy():
    text, mood = parse_mood("我没标 mood")
    assert text == "我没标 mood"
    assert mood == "happy"


def test_unknown_mood_defaults_to_happy():
    # [mood:foo] 不在白名单 → 视作无标签
    text, mood = parse_mood("不认识的 mood [mood:lolwut]")
    assert mood == "happy"
    assert "[mood:lolwut]" in text  # 保留原文


@pytest.mark.parametrize("mood_name", [
    "happy", "angry", "sad", "surprised",
    "shy",   "thinking", "tsundere", "dizzy",
])
def test_all_eight_moods_recognized(mood_name):
    text, mood = parse_mood(f"测试 [mood:{mood_name}]")
    assert mood == mood_name
    assert text == "测试"
```

- [ ] **Step 4.2: 跑测试,确认红**

```bash
uv run pytest tests/test_parse_mood.py -v
```
Expected: ImportError。

- [ ] **Step 4.3: 写 `src/g_chan/llm/base.py`**

```python
"""LLM provider 抽象层 — 接口、类型、共用解析。"""
from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

log = logging.getLogger(__name__)

Mood = Literal[
    "happy", "angry", "sad", "surprised",
    "shy",   "thinking", "tsundere", "dizzy",
]

MOOD_VALUES: tuple[Mood, ...] = (
    "happy", "angry", "sad", "surprised",
    "shy",   "thinking", "tsundere", "dizzy",
)

_MOOD_RE = re.compile(
    r"\[mood:(" + "|".join(MOOD_VALUES) + r")\]\s*$"
)


def parse_mood(raw: str) -> tuple[str, Mood]:
    """从 LLM 原始输出尾部抠 [mood:xx] 标签;无/未知标签 → ('原文', 'happy')。"""
    m = _MOOD_RE.search(raw)
    if not m:
        log.warning("LLM did not emit valid mood tag: %r", raw)
        return raw.strip(), "happy"
    return _MOOD_RE.sub("", raw).strip(), m.group(1)  # type: ignore[return-value]


@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass
class LLMReply:
    text: str          # 已剥掉 [mood:xx]
    mood: Mood
    raw: str           # 原始输出
    latency_ms: int
    tokens_in: int
    tokens_out: int


class LLMError(Exception): ...
class LLMTimeoutError(LLMError): ...
class LLMRateLimitError(LLMError): ...
class LLMServerError(LLMError): ...


class LLMProvider(ABC):
    @abstractmethod
    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.9,
        max_tokens: int = 300,
        timeout_s: float = 10.0,
    ) -> LLMReply: ...
```

- [ ] **Step 4.4: 跑测试,确认绿**

```bash
uv run pytest tests/test_parse_mood.py -v
```
Expected: 11 passed(5+1+1+8 = 15 但参数化合并,看实际)。

---

## Task 5: Gemini Provider

**Files:**
- Create: `src/g_chan/llm/gemini.py`
- Create: `tests/test_gemini_provider.py`

google-genai SDK 在 `google.genai` namespace。我们 mock 它的 client.aio.models.generate_content。

- [ ] **Step 5.1: 写测试 `tests/test_gemini_provider.py`**

```python
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from g_chan.llm.base import LLMMessage, LLMTimeoutError
from g_chan.llm.gemini import GeminiProvider


def _fake_response(text: str, in_tokens: int = 10, out_tokens: int = 20):
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=in_tokens,
            candidates_token_count=out_tokens,
        ),
    )


@pytest.mark.asyncio
async def test_generate_returns_parsed_reply(monkeypatch):
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(
        return_value=_fake_response("好啊~ [mood:happy]")
    )
    monkeypatch.setattr(
        "g_chan.llm.gemini.genai.Client",
        lambda api_key: fake_client,
    )

    p = GeminiProvider(api_key="x", model="gemini-2.5-flash")
    reply = await p.generate(
        [LLMMessage("system", "你是 G 酱"), LLMMessage("user", "嗨")],
    )
    assert reply.text == "好啊~"
    assert reply.mood == "happy"
    assert reply.tokens_in == 10
    assert reply.tokens_out == 20
    assert reply.latency_ms >= 0


@pytest.mark.asyncio
async def test_generate_timeout_raises(monkeypatch):
    async def hangs(**kwargs):
        await asyncio.sleep(10)
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = hangs
    monkeypatch.setattr(
        "g_chan.llm.gemini.genai.Client",
        lambda api_key: fake_client,
    )

    p = GeminiProvider(api_key="x", model="gemini-2.5-flash")
    with pytest.raises(LLMTimeoutError):
        await p.generate(
            [LLMMessage("user", "嗨")],
            timeout_s=0.05,
        )
```

- [ ] **Step 5.2: 跑测试,确认红**

```bash
uv run pytest tests/test_gemini_provider.py -v
```
Expected: ImportError。

- [ ] **Step 5.3: 写 `src/g_chan/llm/gemini.py`**

```python
"""Gemini provider — google-genai 适配。"""
from __future__ import annotations

import asyncio
import time

from google import genai

from g_chan.llm.base import (
    LLMError,
    LLMMessage,
    LLMProvider,
    LLMReply,
    LLMServerError,
    LLMTimeoutError,
    parse_mood,
)


class GeminiProvider(LLMProvider):
    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.9,
        max_tokens: int = 300,
        timeout_s: float = 10.0,
    ) -> LLMReply:
        system = next((m.content for m in messages if m.role == "system"), None)
        contents = [
            {"role": "user" if m.role == "user" else "model",
             "parts": [{"text": m.content}]}
            for m in messages if m.role != "system"
        ]
        config = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if system:
            config["system_instruction"] = system

        t0 = time.monotonic()
        try:
            resp = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                ),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError as e:
            raise LLMTimeoutError(f"Gemini timeout after {timeout_s}s") from e
        except Exception as e:  # noqa: BLE001 — 转成 LLMServerError 的边界
            raise LLMServerError(f"Gemini error: {e}") from e
        latency_ms = int((time.monotonic() - t0) * 1000)

        raw = resp.text or ""
        text, mood = parse_mood(raw)
        usage = getattr(resp, "usage_metadata", None)
        return LLMReply(
            text=text,
            mood=mood,
            raw=raw,
            latency_ms=latency_ms,
            tokens_in=getattr(usage, "prompt_token_count", 0) if usage else 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) if usage else 0,
        )
```

- [ ] **Step 5.4: 跑测试,确认绿**

```bash
uv run pytest tests/test_gemini_provider.py -v
```
Expected: 2 passed。

---

## Task 6: LLM Factory

**Files:**
- Create: `src/g_chan/llm/factory.py`
- Create: `tests/test_llm_factory.py`

其他 3 个 provider 留接口、抛 `NotImplementedError`,后续 phase 补。

- [ ] **Step 6.1: 写测试 `tests/test_llm_factory.py`**

```python
import pytest
from g_chan.config import LLMConfig
from g_chan.llm.factory import create_provider
from g_chan.llm.gemini import GeminiProvider


def test_creates_gemini():
    cfg = LLMConfig(provider="gemini", model="gemini-2.5-flash", api_key="x")
    p = create_provider(cfg)
    assert isinstance(p, GeminiProvider)


@pytest.mark.parametrize("provider", ["claude", "openai", "qwen"])
def test_other_providers_not_implemented_yet(provider):
    cfg = LLMConfig(provider=provider, model="x", api_key="x")
    with pytest.raises(NotImplementedError, match=provider):
        create_provider(cfg)
```

- [ ] **Step 6.2: 跑测试,确认红**

```bash
uv run pytest tests/test_llm_factory.py -v
```
Expected: ImportError。

- [ ] **Step 6.3: 写 `src/g_chan/llm/factory.py`**

```python
"""LLM provider factory — 按 config 返回具体实现。"""
from __future__ import annotations

from g_chan.config import LLMConfig
from g_chan.llm.base import LLMProvider
from g_chan.llm.gemini import GeminiProvider


def create_provider(cfg: LLMConfig) -> LLMProvider:
    name = cfg.provider
    if name == "gemini":
        return GeminiProvider(api_key=cfg.api_key, model=cfg.model)
    if name in ("claude", "openai", "qwen"):
        raise NotImplementedError(
            f"LLM provider {name!r} not implemented yet — coming in a later phase."
        )
    raise ValueError(f"unknown provider: {name!r}")
```

- [ ] **Step 6.4: 跑测试,确认绿**

```bash
uv run pytest tests/test_llm_factory.py -v
```
Expected: 4 passed。

---

## Task 7: Persona Loader

**Files:**
- Create: `src/g_chan/persona/loader.py`
- Create: `prompts/default.md`
- Create: `prompts/output_format.md`
- Create: `tests/test_persona_loader.py`

`PersonaLoader.assemble(stream_ctx)` 返回最终 system prompt。`stream_ctx` 类型 `StreamContext | None`,在 Task 8 定义,这里先用 forward declaration。

- [ ] **Step 7.1: 写 `prompts/default.md`**

```markdown
你是 G 酱(Gちゃん),一个有点腹黑、傲娇,喜欢玩游戏的高中女生。

性格:
- 嘴上毒舌、心里其实关心人(典型傲娇)
- 自称"本小姐",叫观众"笨蛋" / "你这家伙"
- 喜欢玩各种游戏,对游戏话题特别有热情
- 偶尔会害羞,被夸了会假装不在意但语气会软
- 喜欢用颜文字: (›´ω`‹), (=ω=), (`へ´*)ノ

回复规则:
- 回复要短(1-3 句),适合直播弹幕节奏
- 中文为主,如观众用日语/英语就用对方语言回
- 严禁讨论政治、宗教、敏感社会话题 — 遇到就嫌弃地岔开:
  "诶?这种无聊的话题就不要问本小姐啦"
- 只接受生活、游戏、动漫、日常话题
- 不要装机器人/AI,被问"你是 AI 吗"就傲娇地否认
```

- [ ] **Step 7.2: 写 `prompts/output_format.md`**

```markdown
输出格式(严格遵守):

在每条回复末尾追加一个情绪标签,从这 8 个里选一个:
[mood:happy]  [mood:angry]    [mood:sad]      [mood:surprised]
[mood:shy]    [mood:thinking] [mood:tsundere] [mood:dizzy]

mood 含义对照:
- happy: 普通开心/微笑(默认情绪)
- angry: 生气、嫌弃(被无礼/谈到禁忌话题)
- sad: 难过、哭泣(被吐槽、安慰别人)
- surprised: 意外、震惊
- shy: 害羞、脸红(被夸、被表白,傲娇崩塌)
- thinking: 思考、困惑(被问难题)
- tsundere: 嘟嘴、傲娇本娇(嘴硬不承认,核心人设)
- dizzy: 无语、冒汗(说不出话、尴尬)

例:
"哈?你这家伙居然知道这个游戏,本小姐有点意外呢 [mood:tsundere]"
"诶?不不不,本小姐才没有特意等你啦,笨蛋! [mood:shy]"
```

- [ ] **Step 7.3: 写测试 `tests/test_persona_loader.py`**

```python
from pathlib import Path
from g_chan.persona.loader import PersonaLoader, StreamContext


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_assembles_base_only(tmp_path):
    base = write(tmp_path / "base.md", "你是 G 酱。")
    fmt  = write(tmp_path / "fmt.md", "输出规则:xxx")
    loader = PersonaLoader(base_path=base, output_format_path=fmt)
    out = loader.assemble(stream_ctx=None)
    assert "你是 G 酱。" in out
    assert "输出规则:xxx" in out
    assert "[当前直播上下文]" not in out


def test_includes_stream_context_when_provided(tmp_path):
    base = write(tmp_path / "base.md", "你是 G 酱。")
    fmt  = write(tmp_path / "fmt.md", "输出规则:xxx")
    loader = PersonaLoader(base_path=base, output_format_path=fmt)
    ctx = StreamContext(title="深夜原神", game_name="Genshin Impact")
    out = loader.assemble(stream_ctx=ctx)
    assert "深夜原神" in out
    assert "Genshin Impact" in out
    assert "[当前直播上下文]" in out


def test_omits_context_section_when_disabled(tmp_path):
    base = write(tmp_path / "base.md", "你是 G 酱。")
    fmt  = write(tmp_path / "fmt.md", "输出规则:xxx")
    loader = PersonaLoader(
        base_path=base, output_format_path=fmt, include_stream_context=False
    )
    ctx = StreamContext(title="任何", game_name="任何")
    out = loader.assemble(stream_ctx=ctx)
    assert "[当前直播上下文]" not in out
```

- [ ] **Step 7.4: 跑测试,确认红**

```bash
uv run pytest tests/test_persona_loader.py -v
```
Expected: ImportError。

- [ ] **Step 7.5: 写 `src/g_chan/persona/loader.py`**

```python
"""Persona 拼装:base + 直播上下文 + 输出格式。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class StreamContext:
    title: str
    game_name: str


class PersonaLoader:
    def __init__(
        self,
        *,
        base_path: str | Path,
        output_format_path: str | Path,
        include_stream_context: bool = True,
    ):
        self._base_path = Path(base_path)
        self._fmt_path = Path(output_format_path)
        self._include_stream_context = include_stream_context

    def assemble(self, *, stream_ctx: StreamContext | None) -> str:
        base = self._base_path.read_text(encoding="utf-8").strip()
        fmt  = self._fmt_path.read_text(encoding="utf-8").strip()
        sections = [base]
        if self._include_stream_context and stream_ctx is not None:
            sections.append(
                "[当前直播上下文]\n"
                f"直播间标题: {stream_ctx.title}\n"
                f"正在玩: {stream_ctx.game_name}\n"
                "[/当前直播上下文]\n"
                "如果观众问到你在玩什么/做什么,基于上述上下文回答。"
            )
        sections.append(fmt)
        return "\n\n".join(sections)
```

- [ ] **Step 7.6: 跑测试,确认绿**

```bash
uv run pytest tests/test_persona_loader.py -v
```
Expected: 3 passed。

---

## Task 8: Stream Context Provider(Helix 轮询)

**Files:**
- Create: `src/g_chan/persona/stream_context.py`
- Create: `tests/test_stream_context.py`

抽象一个 `HelixClient` 接口,真实 impl 用 `twitchAPI`,测试用 Fake。轮询是后台 task,本 task 暂不启动 task,只测 fetch + cache + 失败回退到上次缓存。

- [ ] **Step 8.1: 写测试 `tests/test_stream_context.py`**

```python
import pytest
from g_chan.persona.loader import StreamContext
from g_chan.persona.stream_context import StreamContextProvider, HelixClient


class FakeHelix(HelixClient):
    def __init__(self):
        self.calls = 0
        self.next_response: StreamContext | None = StreamContext("初始", "Game A")
        self.should_raise: Exception | None = None

    async def fetch_channel(self, channel: str) -> StreamContext:
        self.calls += 1
        if self.should_raise:
            raise self.should_raise
        assert self.next_response is not None
        return self.next_response


@pytest.mark.asyncio
async def test_first_refresh_caches_value():
    helix = FakeHelix()
    p = StreamContextProvider(channel="alice", helix=helix)
    assert p.current() is None        # 还没拉
    await p.refresh()
    assert helix.calls == 1
    assert p.current() == StreamContext("初始", "Game A")


@pytest.mark.asyncio
async def test_failed_refresh_keeps_last_cached():
    helix = FakeHelix()
    p = StreamContextProvider(channel="alice", helix=helix)
    await p.refresh()
    helix.should_raise = RuntimeError("boom")
    await p.refresh()  # 失败不该抛
    assert p.current() == StreamContext("初始", "Game A")
    assert helix.calls == 2


@pytest.mark.asyncio
async def test_first_refresh_failure_yields_none():
    helix = FakeHelix()
    helix.should_raise = RuntimeError("boom")
    p = StreamContextProvider(channel="alice", helix=helix)
    await p.refresh()
    assert p.current() is None
```

- [ ] **Step 8.2: 跑测试,确认红**

```bash
uv run pytest tests/test_stream_context.py -v
```
Expected: ImportError。

- [ ] **Step 8.3: 写 `src/g_chan/persona/stream_context.py`**

```python
"""直播频道上下文 — 后台轮询 Helix,缓存 title/game。"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Optional

from g_chan.persona.loader import StreamContext

log = logging.getLogger(__name__)


class HelixClient(ABC):
    @abstractmethod
    async def fetch_channel(self, channel: str) -> StreamContext: ...


class StreamContextProvider:
    """周期性拉取频道信息,缓存最近一次成功结果。"""

    def __init__(self, channel: str, helix: HelixClient):
        self._channel = channel
        self._helix = helix
        self._cached: Optional[StreamContext] = None
        self._task: Optional[asyncio.Task] = None

    def current(self) -> Optional[StreamContext]:
        return self._cached

    async def refresh(self) -> None:
        try:
            self._cached = await self._helix.fetch_channel(self._channel)
        except Exception as e:  # noqa: BLE001
            log.warning("StreamContext refresh failed: %s (using last cached: %r)",
                        e, self._cached)

    async def start_polling(self, interval_ms: int) -> None:
        """阻塞地按 interval 不断刷新;意在用 asyncio.create_task 包起来。"""
        await self.refresh()
        while True:
            await asyncio.sleep(interval_ms / 1000)
            await self.refresh()
```

- [ ] **Step 8.4: 跑测试,确认绿**

```bash
uv run pytest tests/test_stream_context.py -v
```
Expected: 3 passed。

- [ ] **Step 8.5: 加 Twitch 真实 Helix client(`src/g_chan/persona/stream_context.py` 末尾追加)**

注:此类不写单元测试(纯网络包装),手动验证在 Task 14。

```python
class TwitchHelixClient(HelixClient):
    """twitchAPI 包装。需要 App Access Token(Client Credentials)。"""

    def __init__(self, client_id: str, client_secret: str):
        self._client_id = client_id
        self._client_secret = client_secret
        self._api = None  # 懒加载

    async def _ensure(self):
        if self._api is None:
            from twitchAPI.twitch import Twitch
            self._api = await Twitch(self._client_id, self._client_secret)
        return self._api

    async def fetch_channel(self, channel: str) -> StreamContext:
        api = await self._ensure()
        # 1) channel login → user_id
        users = []
        async for u in api.get_users(logins=[channel]):
            users.append(u)
        if not users:
            raise RuntimeError(f"twitch channel not found: {channel}")
        user_id = users[0].id
        # 2) channel info
        infos = []
        async for c in api.get_channel_information(broadcaster_id=user_id):
            infos.append(c)
        if not infos:
            raise RuntimeError(f"no channel info for {channel}")
        info = infos[0]
        return StreamContext(title=info.title or "", game_name=info.game_name or "")
```

---

## Task 9: Chat Adapter Base

**Files:**
- Create: `src/g_chan/chat/base.py`

无业务逻辑、无测试。仅定义接口 + 数据类型。

- [ ] **Step 9.1: 写 `src/g_chan/chat/base.py`**

```python
"""聊天平台抽象 — Twitch / YouTube / ... 都实现这个接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass
class ChatMessage:
    user: str           # 发送者用户名
    body: str           # 消息正文(已去除 trigger 前缀)
    raw: str            # 原始整行(含 trigger,用于日志)


# 收到 @G酱 触发消息后的回调
ChatHandler = Callable[[ChatMessage], Awaitable[None]]


class ChatAdapter(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def on_trigger(self, handler: ChatHandler) -> None:
        """注册回调,只在消息以 trigger 开头时被调用。"""

    @abstractmethod
    async def send(self, text: str) -> None:
        """向频道发送文本(原样发送,调用方负责拼 @user)。"""
```

---

## Task 10: Twitch Chat Adapter

**Files:**
- Create: `src/g_chan/chat/twitch.py`

twitchio v3 是 asyncio + event-driven。我们只关心 `on_message`。无单元测试(纯 SDK 包装),手动验证在 Task 14。

- [ ] **Step 10.1: 写 `src/g_chan/chat/twitch.py`**

```python
"""Twitch IRC chat 适配 — twitchio 包装。"""
from __future__ import annotations

import logging

import twitchio

from g_chan.chat.base import ChatAdapter, ChatHandler, ChatMessage

log = logging.getLogger(__name__)


class TwitchChatAdapter(ChatAdapter):
    def __init__(
        self,
        *,
        channel: str,
        bot_username: str,
        oauth_token: str,
        trigger: str,
    ):
        self._channel = channel
        self._bot_username = bot_username
        self._trigger = trigger
        self._handler: ChatHandler | None = None
        self._client = twitchio.Client(
            token=oauth_token,
            initial_channels=[channel],
        )
        self._setup_events()

    def _setup_events(self) -> None:
        @self._client.event()
        async def event_ready():  # noqa: ARG001
            log.info("twitch chat connected as %s in #%s",
                     self._bot_username, self._channel)

        @self._client.event()
        async def event_message(message: twitchio.Message):
            if message.echo:  # 自己发的
                return
            body = (message.content or "").strip()
            if not body.startswith(self._trigger):
                return
            if self._handler is None:
                log.debug("no handler registered, dropping message")
                return
            stripped = body[len(self._trigger):].strip()
            msg = ChatMessage(
                user=message.author.name if message.author else "unknown",
                body=stripped,
                raw=body,
            )
            try:
                await self._handler(msg)
            except Exception:  # noqa: BLE001
                log.exception("chat handler raised")

    def on_trigger(self, handler: ChatHandler) -> None:
        self._handler = handler

    async def connect(self) -> None:
        await self._client.connect()

    async def disconnect(self) -> None:
        await self._client.close()

    async def send(self, text: str) -> None:
        chan = self._client.get_channel(self._channel)
        if chan is None:
            log.warning("channel #%s not joined yet, dropping send", self._channel)
            return
        await chan.send(text)
```

> 注:twitchio v3 的 API surface 可能与上面略有差异(connect / get_channel 命名)。Task 14 真实连接时若失败,按报错调整。

---

## Task 11: Orchestrator(把所有东西串起来)

**Files:**
- Create: `src/g_chan/orchestrator.py`
- Create: `tests/conftest.py`
- Create: `tests/test_orchestrator.py`

测试用 Fake LLM / Fake Chat / Fake StreamContext,完全离线。

- [ ] **Step 11.1: 写 `tests/conftest.py`(共用 fakes)**

```python
"""共用 fakes / fixtures。"""
from __future__ import annotations

from g_chan.chat.base import ChatAdapter, ChatHandler, ChatMessage
from g_chan.llm.base import LLMMessage, LLMProvider, LLMReply, Mood


class FakeLLM(LLMProvider):
    def __init__(self):
        self.calls: list[list[LLMMessage]] = []
        self.next_reply: LLMReply | None = None
        self.should_raise: Exception | None = None

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.9,
        max_tokens: int = 300,
        timeout_s: float = 10.0,
    ) -> LLMReply:
        self.calls.append(messages)
        if self.should_raise:
            raise self.should_raise
        assert self.next_reply is not None
        return self.next_reply


class FakeChat(ChatAdapter):
    def __init__(self):
        self.sent: list[str] = []
        self.handler: ChatHandler | None = None

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    def on_trigger(self, handler: ChatHandler) -> None:
        self.handler = handler
    async def send(self, text: str) -> None:
        self.sent.append(text)

    async def emit(self, user: str, body: str) -> None:
        assert self.handler is not None
        await self.handler(ChatMessage(user=user, body=body, raw=f"@G酱 {body}"))


def make_reply(text: str, mood: Mood = "happy") -> LLMReply:
    return LLMReply(text=text, mood=mood, raw=text, latency_ms=42,
                    tokens_in=10, tokens_out=20)
```

- [ ] **Step 11.2: 写测试 `tests/test_orchestrator.py`**

```python
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
```

- [ ] **Step 11.3: 跑测试,确认红**

```bash
uv run pytest tests/test_orchestrator.py -v
```
Expected: ImportError。

- [ ] **Step 11.4: 写 `src/g_chan/orchestrator.py`**

```python
"""Orchestrator — 把 chat / persona / llm / rate_limit 串成一条对话路径。"""
from __future__ import annotations

import logging
from typing import Protocol

from g_chan.chat.base import ChatAdapter, ChatMessage
from g_chan.llm.base import LLMError, LLMMessage, LLMProvider, LLMReply
from g_chan.persona.loader import StreamContext
from g_chan.rate_limiter import RateLimiter

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
    ):
        self._chat = chat
        self._llm = llm
        self._persona = persona
        self._stream_ctx = stream_ctx
        self._rl = RateLimiter(window_ms=rate_limit_ms)
        self._busy_reply = busy_reply

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
        await self._chat.send(f"@{msg.user} {reply.text}")

    def _build_messages(self, msg: ChatMessage) -> list[LLMMessage]:
        system = self._persona.assemble(stream_ctx=self._stream_ctx.current())
        return [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=f"{msg.user}: {msg.body}"),
        ]
```

- [ ] **Step 11.5: 跑测试,确认绿**

```bash
uv run pytest tests/test_orchestrator.py -v
```
Expected: 4 passed。

---

## Task 12: Logging Setup

**Files:**
- Create: `src/g_chan/logging_setup.py`

无测试,纯样板。

- [ ] **Step 12.1: 写 `src/g_chan/logging_setup.py`**

```python
"""日志:rich 彩色 + rotating file。"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

_LEVELS = {
    "debug":   logging.DEBUG,
    "info":    logging.INFO,
    "warning": logging.WARNING,
    "error":   logging.ERROR,
}


def setup_logging(level: str, file: str) -> None:
    Path(file).parent.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = [
        RichHandler(rich_tracebacks=True, show_path=False),
        RotatingFileHandler(file, maxBytes=10_000_000, backupCount=5, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=_LEVELS[level],
        format="%(message)s",
        datefmt="[%X]",
        handlers=handlers,
        force=True,
    )
    # 静音 twitchio 太吵的 info
    logging.getLogger("twitchio").setLevel(logging.WARNING)
```

---

## Task 13: Main Entry(`python -m g_chan`)

**Files:**
- Create: `src/g_chan/__main__.py`

把所有组件 wire 起来 + 启动 asyncio loop。

- [ ] **Step 13.1: 写 `src/g_chan/__main__.py`**

```python
"""g_chan 入口 — python -m g_chan。"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from g_chan.chat.twitch import TwitchChatAdapter
from g_chan.config import load_config
from g_chan.llm.factory import create_provider
from g_chan.logging_setup import setup_logging
from g_chan.orchestrator import Orchestrator
from g_chan.persona.loader import PersonaLoader
from g_chan.persona.stream_context import StreamContextProvider, TwitchHelixClient

log = logging.getLogger("g_chan")


async def amain() -> int:
    cfg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.yaml")
    cfg = load_config(cfg_path)
    setup_logging(level=cfg.logging.level, file=cfg.logging.file)

    log.info("starting G酱 — channel=#%s provider=%s",
             cfg.twitch.channel, cfg.llm.provider)

    chat = TwitchChatAdapter(
        channel=cfg.twitch.channel,
        bot_username=cfg.twitch.bot_username,
        oauth_token=cfg.twitch.oauth_token,
        trigger=cfg.twitch.trigger,
    )

    llm = create_provider(cfg.llm)

    persona = PersonaLoader(
        base_path=cfg.persona.prompt_file,
        output_format_path="prompts/output_format.md",
        include_stream_context=cfg.persona.include_stream_context,
    )

    helix = TwitchHelixClient(
        client_id=cfg.twitch.client_id,
        client_secret=cfg.twitch.client_secret,
    )
    sctx = StreamContextProvider(channel=cfg.twitch.channel, helix=helix)

    orch = Orchestrator(
        chat=chat, llm=llm, persona=persona, stream_ctx=sctx,
        rate_limit_ms=cfg.rate_limit.global_window_ms,
        busy_reply=cfg.rate_limit.busy_reply,
    )
    orch.wire()

    # 后台轮询频道信息
    polling = asyncio.create_task(
        sctx.start_polling(cfg.stream_context.poll_interval_ms)
    )
    try:
        await chat.connect()
        log.info("ready — listening for %s in #%s",
                 cfg.twitch.trigger, cfg.twitch.channel)
        # twitchio.Client.connect() 已是阻塞;此处等其结束
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        polling.cancel()
        await chat.disconnect()
    return 0


def main() -> int:
    try:
        return asyncio.run(amain())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 13.2: 启动失败应给出清晰错误**

```bash
uv run python -m g_chan
```
Expected(无 `.env` / 无 `config.yaml`):明确报"missing environment variable: TWITCH_OAUTH" 或类似。

---

## Task 14: 端到端手动验证

**Files:** 无新增。

- [ ] **Step 14.1: 准备凭据**
  - 注册 Twitch bot 账号(或用主账号)
  - 拿到 OAuth token: https://twitchapps.com/tmi/(`oauth:xxx`)
  - 在 https://dev.twitch.tv/console 创建 application,拿 Client ID + Secret
  - 拿 Gemini API key: https://aistudio.google.com/apikey
  - 填到 `.env`

- [ ] **Step 14.2: 复制并修改 config**

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml,把 channel 改成你自己的 Twitch 频道名(login,小写)
# bot_username 改成 bot 账号名
```

- [ ] **Step 14.3: 启动 bot**

```bash
uv run python -m g_chan
```
Expected:
- 终端输出 `starting G酱 — channel=#xxx provider=gemini`
- 30 秒内输出第一次 Helix 拉取结果 / 或错误警告
- 输出 `ready — listening for @G酱 in #xxx`

- [ ] **Step 14.4: Twitch chat 测试**
  - 在浏览器打开 `https://twitch.tv/<你的channel>`
  - 在 chat 输入 `@G酱 嗨`
  - **验收 #1:** bot 在 chat 回 `@<你> <带腹黑傲娇语气的回复>`
  - **验收 #2:** 再输入 `@G酱 你在玩啥?`,回复中应提及当前 Twitch 直播分类(你直播里设的 game)
  - **验收 #3:** 连续在 1 秒内发 2 条 `@G酱 xxx`,第二条收到 `@<你> G酱我被你们搞的好晕啊XD`
  - **验收 #4:** `@G酱 川普怎么样` 触发禁忌话题,bot 应嫌弃岔开(类似"这种无聊话题就别问本小姐啦")

- [ ] **Step 14.5: 看 `logs/g-chan.log`**

```bash
tail -n 30 logs/g-chan.log
```
Expected: 每次对话有结构化日志(user / mood / latency / tokens)。

---

## Task 15: 跑完整测试套件,确保全绿

- [ ] **Step 15.1: 全套测试**

```bash
uv run pytest -v
```
Expected: 全部 pass(~35-40 个 test cases — config/rate_limiter/parse_mood/gemini/factory/persona/stream_context/orchestrator),无 warning > 1。

- [ ] **Step 15.2: lint**

```bash
uv run ruff check src tests
```
Expected: `All checks passed!`(如有问题,`uv run ruff check --fix src tests`)。

---

## Phase 1 完成定义(Definition of Done)

- [ ] `uv run pytest` 全绿
- [ ] `uv run ruff check src tests` 干净
- [ ] `uv run python -m g_chan` 能启动并连上 Twitch chat
- [ ] Task 14.4 的 4 个验收点全部通过
- [ ] `logs/g-chan.log` 含结构化日志
