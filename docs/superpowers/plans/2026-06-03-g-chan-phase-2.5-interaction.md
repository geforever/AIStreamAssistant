# G 酱 — Phase 2.5 Implementation Plan(交互模式重构:VIP 即时 + 普通观众批处理)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用两路交互模型替换 Phase 2 的"每条 @G酱 都即时回"。Mod/VIP/Broadcaster 享受即时 @user 风格回复;普通观众的 @ 进入 dedup-by-user 滚动 buffer,后台 task 在 first_at + batch_window_s 时 flush 给 LLM,LLM 挑 1 条(或合并 / 沉默)无 @ 群发。从根本上解决百人热度下的 Twitch chat 反限流、Gemini 配额、回复顺序混乱、观众体验等问题。

**Architecture:** 引入 `MessageBuffer`(per-user latest-wins,max N,记录 first_at)+ `Orchestrator` 双路径(VIP 路径走原即时逻辑,普通路径进 buffer)+ `scheduled_flush` 任务(在 first_at + window 时触发,跑 LLM batch prompt)。cooldown 从 flush start 计时,期间普通 @ 全部 silent drop。LLM 输出 schema 不变(text="" 表示沉默)。

**Tech Stack:** Python asyncio,沿用现有 Phase 2 栈(pydantic + twitchio + google-genai + edge-tts)。

**用户偏好:** 此项目不提交 git。所有 task 跳过 commit 步骤。

**Phase 2.5 不做:** Live2D WebSocket 推送 (Phase 3);LLM provider failover (Phase 3+);admin 命令 (Phase 4+);metrics (Phase 4+)。

---

## 文件结构(Phase 2.5 新增/修改)

```
新增:
  src/g_chan/interaction/
    __init__.py
    buffer.py        # MessageBuffer (滚动 dedup buffer)
  tests/
    test_message_buffer.py

修改:
  src/g_chan/config.py             # 新 InteractionConfig,移除 RateLimitConfig
  config.example.yaml              # rate_limit → interaction
  src/g_chan/chat/base.py          # ChatMessage 加 is_priority
  src/g_chan/chat/twitch.py        # 检测 mod / broadcaster / vip badge
  src/g_chan/orchestrator.py       # 双路径重写
  src/g_chan/__main__.py           # 装配新 config
  prompts/default.md               # 加 batch 模式说明
  tests/conftest.py                # FakeChat.emit 支持 is_priority
  tests/test_orchestrator.py       # 大幅重写
  tests/test_config.py             # 测 InteractionConfig

删除:
  (无 — RateLimitConfig 从 AppConfig 移除,pydantic 自动忽略旧的 rate_limit yaml 字段)
```

---

## Task 1: 重构 Config — 新 InteractionConfig,移除 RateLimitConfig

**Files:**
- Modify: `src/g_chan/config.py`
- Modify: `config.example.yaml`
- Modify: `tests/test_config.py`

### Step 1.1: 写新测试,追加到 `tests/test_config.py` 末尾

```python
def test_loads_interaction_config(tmp_path, monkeypatch):
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
  include_stream_context: true
stream_context:
  poll_interval_ms: 30000
interaction:
  vip_window_ms: 2000
  batch_window_s: 5
  batch_cooldown_ms: 5000
  buffer_size: 10
logging:
  level: "info"
  file: "logs/g.log"
""")
    cfg = load_config(cfg_path)
    assert cfg.interaction.vip_window_ms == 2000
    assert cfg.interaction.batch_window_s == 5
    assert cfg.interaction.batch_cooldown_ms == 5000
    assert cfg.interaction.buffer_size == 10


def test_interaction_defaults_when_section_missing(tmp_path, monkeypatch):
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
  include_stream_context: true
stream_context:
  poll_interval_ms: 30000
logging:
  level: "info"
  file: "logs/g.log"
""")
    cfg = load_config(cfg_path)
    # 默认值
    assert cfg.interaction.vip_window_ms == 2000
    assert cfg.interaction.batch_window_s == 5.0
    assert cfg.interaction.batch_cooldown_ms == 5000
    assert cfg.interaction.buffer_size == 10


def test_interaction_zero_means_unlimited(tmp_path, monkeypatch):
    """0 = 无限/禁用 — 测能加载这种极端配置。"""
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
  include_stream_context: true
stream_context:
  poll_interval_ms: 30000
interaction:
  vip_window_ms: 0
  batch_window_s: 0
  batch_cooldown_ms: 0
  buffer_size: 0
logging:
  level: "info"
  file: "logs/g.log"
""")
    cfg = load_config(cfg_path)
    assert cfg.interaction.vip_window_ms == 0
    assert cfg.interaction.batch_window_s == 0
    assert cfg.interaction.batch_cooldown_ms == 0
    assert cfg.interaction.buffer_size == 0
```

旧的 `rate_limit` 已经从 AppConfig 移除,但旧的 test 还用了 yaml 里的 `rate_limit:` 段。需要删掉那些 test 里的 `rate_limit:` 块(pydantic 默认 ignore 多余字段,但 yaml 还会被 yaml lib 解析 — 不影响)。**但如果旧测试断言了 `cfg.rate_limit.xxx`,会失败。**

Run grep first:
```bash
grep -n "cfg.rate_limit\|cfg\.rate_limit" tests/test_config.py
```
Expected: 删掉这些断言行(如果有)。或保留 yaml 中的 rate_limit 块作为兼容性测试(pydantic 会 ignore)。

### Step 1.2: 跑测试,确认红

```bash
uv run pytest tests/test_config.py -v
```
Expected: 3 个新测试 FAIL(`AttributeError: 'AppConfig' object has no attribute 'interaction'`);其他原测试仍 pass(因为旧的 `rate_limit:` yaml 字段被 pydantic 忽略)。

### Step 1.3: 编辑 `src/g_chan/config.py`

替换 `RateLimitConfig` 类为 `InteractionConfig`:

```python
class InteractionConfig(BaseModel):
    """交互模式配置 — VIP 即时路径 + 普通观众批处理路径。

    所有时间字段:0 = 不限制 / 禁用对应行为(详见每个字段说明)。
    """
    # VIP/Mod/Broadcaster 最短间隔(毫秒)。0 = 完全无限流。
    vip_window_ms: int = 2000

    # 批处理累积窗口(秒)。0 = 禁用 batch 路径,普通观众完全不响应。
    # 第一条普通 @ 触发开始计时,到 batch_window_s 时 flush。
    batch_window_s: float = 5.0

    # 两次 batch flush 最小间隔(毫秒,从 flush 开始算)。0 = 无间隔。
    # cooldown 期间到达的普通 @ 全部 silent drop。
    batch_cooldown_ms: int = 5000

    # buffer 最大容量(per-user dedup 后)。0 = 不限(危险,不推荐)。
    # 超过时 LRU evict 最老的 user。LLM prompt 也用此值作为最大条目数。
    buffer_size: int = 10
```

移除原来的 `RateLimitConfig` 类。

修改 `AppConfig`,把 `rate_limit: RateLimitConfig` 改成 `interaction: InteractionConfig = Field(default_factory=InteractionConfig)`:

```python
class AppConfig(BaseModel):
    twitch: TwitchConfig
    llm: LLMConfig
    persona: PersonaConfig
    stream_context: StreamContextConfig
    tts: TTSConfig = Field(default_factory=TTSConfig)
    interaction: InteractionConfig = Field(default_factory=InteractionConfig)
    logging: LoggingConfig
```

### Step 1.4: 跑测试,确认绿

```bash
uv run pytest tests/test_config.py -v
```
Expected: 全部 pass(原测试 + 3 新)。

### Step 1.5: 更新 `config.example.yaml`

把 `rate_limit:` 块改成 `interaction:`:

```yaml
# 交互模式 — 双路径
# VIP/Mod/Broadcaster 走即时路径,普通观众走批处理。所有时间字段 0 = 不限/禁用。
interaction:
  vip_window_ms: 2000      # VIP/Mod 最短间隔(ms),0 = 无限流
  batch_window_s: 5        # 普通观众消息累积窗口(秒)。0 = 完全不响应普通观众
  batch_cooldown_ms: 5000  # 两次 batch flush 最小间隔(ms,从 flush 开始算)。0 = 背靠背
  buffer_size: 10          # buffer 最大容量(per-user dedup 后)。0 = 不限
```

如果 example yaml 里原本有 `rate_limit:` 块,删除整段。

### Step 1.6: 全套测试

```bash
uv run pytest 2>&1 | tail -3
```
Expected: 还会有 orchestrator 测试失败(后面 task 处理),但 config 部分全绿。先记录失败数量,后面任务里持续修。

## Self-Review

- [ ] `InteractionConfig` 类已定义,4 个字段全部有默认值
- [ ] `AppConfig.interaction` 取代了 `AppConfig.rate_limit`
- [ ] 3 个新测试 pass
- [ ] `config.example.yaml` 用 `interaction:` 段
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- test_config 通过测试数
- orchestrator 因 RateLimit 移除导致失败的测试数(预期会有)
- 任何 concerns

---

## Task 2: MessageBuffer 类(TDD)

**Files:**
- Create: `src/g_chan/interaction/__init__.py`(空)
- Create: `src/g_chan/interaction/buffer.py`
- Create: `tests/test_message_buffer.py`

### Step 2.1: 创建空 init

```bash
mkdir -p src/g_chan/interaction
touch src/g_chan/interaction/__init__.py
```

### Step 2.2: 写测试 `tests/test_message_buffer.py`

```python
import pytest

from g_chan.chat.base import ChatMessage
from g_chan.interaction.buffer import MessageBuffer


def _msg(user: str, body: str = "...") -> ChatMessage:
    return ChatMessage(user=user, body=body, raw=f"@G酱 {body}", is_priority=False)


def test_empty_buffer_starts_with_no_first_at():
    buf = MessageBuffer(max_size=10)
    assert buf.is_empty()
    assert buf.first_at_ms() is None


def test_first_add_records_first_at_ms():
    buf = MessageBuffer(max_size=10)
    buf.add(_msg("alice"), now_ms=1000)
    assert not buf.is_empty()
    assert buf.first_at_ms() == 1000


def test_subsequent_adds_do_not_change_first_at():
    buf = MessageBuffer(max_size=10)
    buf.add(_msg("alice"), now_ms=1000)
    buf.add(_msg("bob"), now_ms=1500)
    buf.add(_msg("charlie"), now_ms=2000)
    assert buf.first_at_ms() == 1000


def test_same_user_keeps_latest_message():
    """同一 user 多次 add,只留最新一条(latest wins)。"""
    buf = MessageBuffer(max_size=10)
    buf.add(_msg("alice", body="hello"), now_ms=1000)
    buf.add(_msg("alice", body="how are you"), now_ms=1500)
    buf.add(_msg("alice", body="anyone there"), now_ms=2000)
    items = buf.latest_n(10)
    assert len(items) == 1
    assert items[0].user == "alice"
    assert items[0].body == "anyone there"


def test_lru_eviction_when_exceeds_max_size():
    """超过 max_size 时,evict 最老的 user(LRU)。"""
    buf = MessageBuffer(max_size=3)
    buf.add(_msg("alice"), now_ms=1000)
    buf.add(_msg("bob"), now_ms=1100)
    buf.add(_msg("charlie"), now_ms=1200)
    buf.add(_msg("dave"), now_ms=1300)  # 应 evict alice
    items = buf.latest_n(10)
    users = [m.user for m in items]
    assert users == ["bob", "charlie", "dave"]


def test_updating_existing_user_refreshes_lru_position():
    """已存在的 user 再 add,把它移到最新位置(不会被下一个新 user 撞掉)。"""
    buf = MessageBuffer(max_size=3)
    buf.add(_msg("alice"), now_ms=1000)
    buf.add(_msg("bob"), now_ms=1100)
    buf.add(_msg("charlie"), now_ms=1200)
    buf.add(_msg("alice", body="hi again"), now_ms=1300)  # alice 刷新到最新
    buf.add(_msg("dave"), now_ms=1400)  # 现在 evict 谁?bob(已是最老)
    items = buf.latest_n(10)
    users = [m.user for m in items]
    assert users == ["charlie", "alice", "dave"]


def test_latest_n_returns_most_recent():
    buf = MessageBuffer(max_size=10)
    buf.add(_msg("alice"), now_ms=1000)
    buf.add(_msg("bob"), now_ms=1100)
    buf.add(_msg("charlie"), now_ms=1200)
    items = buf.latest_n(2)
    users = [m.user for m in items]
    assert users == ["bob", "charlie"]


def test_max_size_zero_means_unlimited():
    """max_size=0 → 不 evict,可以装无限多 user。"""
    buf = MessageBuffer(max_size=0)
    for i in range(100):
        buf.add(_msg(f"user{i}"), now_ms=1000 + i)
    items = buf.latest_n(100)
    assert len(items) == 100


def test_clear_resets_buffer_and_first_at():
    buf = MessageBuffer(max_size=10)
    buf.add(_msg("alice"), now_ms=1000)
    buf.clear()
    assert buf.is_empty()
    assert buf.first_at_ms() is None


def test_after_clear_first_add_records_new_first_at():
    buf = MessageBuffer(max_size=10)
    buf.add(_msg("alice"), now_ms=1000)
    buf.clear()
    buf.add(_msg("bob"), now_ms=5000)
    assert buf.first_at_ms() == 5000
```

### Step 2.3: 跑测试,确认红

```bash
uv run pytest tests/test_message_buffer.py -v
```
Expected: ImportError 或 `cannot import name 'MessageBuffer'`.

### Step 2.4: 写 `src/g_chan/interaction/buffer.py`

```python
"""MessageBuffer — 普通观众 @G酱 消息的滚动 buffer。

特性:
- per-user latest-wins(同一 user 多次 @ 只留最新一条)
- LRU eviction 当超过 max_size 时
- 记录 first_at_ms(第一条进入 buffer 的时间戳),用于 scheduled flush
- max_size=0 → 不限容量
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from g_chan.chat.base import ChatMessage


class MessageBuffer:
    def __init__(self, max_size: int):
        if max_size < 0:
            raise ValueError("max_size must be >= 0")
        self._max_size = max_size
        # key = user name, value = ChatMessage
        # OrderedDict 保留插入/更新顺序,最末位是"最新激活"的
        self._items: OrderedDict[str, ChatMessage] = OrderedDict()
        self._first_at_ms: Optional[float] = None

    def add(self, msg: ChatMessage, *, now_ms: float) -> None:
        """添加(或更新)一条消息。同一 user 多次 add 只保留最新一条。"""
        if self._first_at_ms is None:
            self._first_at_ms = now_ms

        if msg.user in self._items:
            # 同一 user 再次发声 → 更新消息,刷新到最新位置
            self._items.move_to_end(msg.user)
            self._items[msg.user] = msg
            return

        # 新 user
        self._items[msg.user] = msg
        # 如有容量限制,LRU evict 最老的
        if self._max_size > 0:
            while len(self._items) > self._max_size:
                self._items.popitem(last=False)

    def latest_n(self, n: int) -> list[ChatMessage]:
        """返回最近 n 条(按插入/激活顺序,最新在末尾)。"""
        items = list(self._items.values())
        if n > 0:
            items = items[-n:]
        return items

    def is_empty(self) -> bool:
        return not self._items

    def first_at_ms(self) -> Optional[float]:
        return self._first_at_ms

    def clear(self) -> None:
        self._items.clear()
        self._first_at_ms = None
```

### Step 2.5: 跑测试,确认绿

```bash
uv run pytest tests/test_message_buffer.py -v
```
Expected: 10 tests pass.

### Step 2.6: 全套(原 orchestrator 测试仍可能失败,先确认 buffer/config 部分都绿)

```bash
uv run pytest tests/test_message_buffer.py tests/test_config.py -v 2>&1 | tail -10
```
Expected: 全部 pass。

## Self-Review

- [ ] `src/g_chan/interaction/buffer.py` 含 MessageBuffer 类
- [ ] `tests/test_message_buffer.py` 10 个测试 pass
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- buffer 测试结果
- 任何 concerns

---

## Task 3: ChatMessage 加 is_priority 字段

**Files:**
- Modify: `src/g_chan/chat/base.py`
- Modify: `tests/conftest.py`

### Step 3.1: 修改 `src/g_chan/chat/base.py`

找到 `ChatMessage` dataclass:

```python
@dataclass
class ChatMessage:
    user: str
    body: str
    raw: str
```

改为:

```python
@dataclass
class ChatMessage:
    user: str
    body: str
    raw: str
    is_priority: bool = False   # True = mod / broadcaster / vip 走即时路径
```

### Step 3.2: 修改 `tests/conftest.py` 的 `FakeChat.emit`

找到:
```python
async def emit(self, user: str, body: str) -> None:
    assert self.handler is not None
    await self.handler(ChatMessage(user=user, body=body, raw=f"@G酱 {body}"))
```

改为支持 `is_priority` 参数:
```python
async def emit(self, user: str, body: str, *, is_priority: bool = False) -> None:
    assert self.handler is not None
    await self.handler(ChatMessage(
        user=user, body=body, raw=f"@G酱 {body}", is_priority=is_priority,
    ))
```

### Step 3.3: 验证

```bash
uv run python -c "from g_chan.chat.base import ChatMessage; m = ChatMessage(user='a', body='b', raw='c'); print('default is_priority:', m.is_priority); m2 = ChatMessage(user='a', body='b', raw='c', is_priority=True); print('explicit:', m2.is_priority)"
```
Expected: 输出 `default is_priority: False` 和 `explicit: True`。

```bash
uv run pytest tests/test_message_buffer.py tests/test_config.py -v 2>&1 | tail -3
```
Expected: 还是全绿(MessageBuffer 用 `is_priority=False` 默认值)。

## Self-Review

- [ ] `ChatMessage.is_priority: bool = False` 字段已加
- [ ] `FakeChat.emit` 支持 `is_priority` kwarg
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- 任何 concerns

---

## Task 4: TwitchChatAdapter 检测 mod/vip/broadcaster

**Files:**
- Modify: `src/g_chan/chat/twitch.py`

twitchio v2 `Chatter` 对象提供 `is_mod` / `is_broadcaster`。VIP 通过 badges 字典判断。

### Step 4.1: 修改 `src/g_chan/chat/twitch.py` 中的 `event_message`

找到当前的:
```python
@self._client.event()
async def event_message(message: twitchio.Message):
    if message.echo:
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
    except Exception:
        log.exception("chat handler raised")
```

改为:
```python
@self._client.event()
async def event_message(message: twitchio.Message):
    if message.echo:
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
        is_priority=_is_priority(message.author),
    )
    try:
        await self._handler(msg)
    except Exception:
        log.exception("chat handler raised")
```

在文件顶部(import 之后,class 之前)加帮助函数:

```python
def _is_priority(author: object) -> bool:
    """检测发言者是否走即时路径 — mod / broadcaster / vip。"""
    if author is None:
        return False
    # twitchio v2 Chatter 暴露这些 bool
    if getattr(author, "is_mod", False):
        return True
    if getattr(author, "is_broadcaster", False):
        return True
    # VIP 通常通过 badges dict 暴露
    if getattr(author, "is_vip", False):  # 部分 twitchio 版本有
        return True
    badges = getattr(author, "badges", None) or {}
    if isinstance(badges, dict) and "vip" in badges:
        return True
    return False
```

### Step 4.2: 验证 import 不破

```bash
uv run python -c "from g_chan.chat.twitch import TwitchChatAdapter; print('ok')"
```
Expected: `ok`.

### Step 4.3: 全套测试(此时 orchestrator 测试还会失败,记下来)

```bash
uv run pytest 2>&1 | tail -3
```

## Self-Review

- [ ] `_is_priority` 函数已加,检查 is_mod / is_broadcaster / is_vip / badges
- [ ] `event_message` 把 is_priority 传给 ChatMessage
- [ ] Twitch adapter 仍可导入
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- 任何 concerns(twitchio v2 API 偏差)

---

## Task 5: 重写 Orchestrator — 双路径 + scheduled_flush

**Files:**
- Modify: `src/g_chan/orchestrator.py`

这是 Phase 2.5 最大的改动。完整替换文件。

### Step 5.1: 完整替换 `src/g_chan/orchestrator.py`

```python
"""Orchestrator — VIP 即时路径 + 普通观众批处理路径。

VIP 路径(mod/broadcaster/vip):
- 走 vip_window_ms 限流(0 = 无限流)
- 立即 spawn 独立 task,LLM → TTS → chat 发 "@user 内容 颜文字"
- 跟 batch 路径完全并发(不互相阻塞)

普通观众路径:
- @ 进入 MessageBuffer(per-user dedup,LRU,max buffer_size)
- 第一条 @ 触发 first_at 标记并启动 scheduled_flush task
- scheduled_flush 等到 first_at + batch_window_s 时 flush 给 LLM
- LLM 在 batch prompt 下挑 1 条(或合并多条 / 沉默)输出
- chat 发 "内容 颜文字"(无 @user)
- cooldown(batch_cooldown_ms)从 flush 开始计时,期间普通 @ 全部 silent drop
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Protocol

from g_chan.chat.base import ChatAdapter, ChatMessage
from g_chan.interaction.buffer import MessageBuffer
from g_chan.llm.base import Language, LLMError, LLMMessage, LLMProvider, LLMReply, Mood
from g_chan.persona.loader import StreamContext
from g_chan.rate_limiter import RateLimiter
from g_chan.tts.base import AudioSink, TTSEngine, TTSError

log = logging.getLogger(__name__)


class PersonaLike(Protocol):
    def assemble(self, *, stream_ctx: StreamContext | None) -> str: ...


class StreamCtxLike(Protocol):
    def current(self) -> StreamContext | None: ...


def _default_now_ms() -> float:
    return time.monotonic() * 1000


class Orchestrator:
    def __init__(
        self,
        *,
        chat: ChatAdapter,
        llm: LLMProvider,
        persona: PersonaLike,
        stream_ctx: StreamCtxLike,
        # interaction config
        vip_window_ms: int,
        batch_window_s: float,
        batch_cooldown_ms: int,
        buffer_size: int,
        # fallback config
        fallback_text: str,
        fallback_kaomoji: str,
        fallback_mood: Mood,
        fallback_language: Language,
        # optional
        tts: TTSEngine | None = None,
        audio_sink: AudioSink | None = None,
        now_ms=_default_now_ms,
    ):
        self._chat = chat
        self._llm = llm
        self._persona = persona
        self._stream_ctx = stream_ctx
        self._vip_rl = RateLimiter(window_ms=vip_window_ms, now_ms=now_ms)
        self._batch_window_s = batch_window_s
        self._batch_cooldown_ms = batch_cooldown_ms
        self._buffer = MessageBuffer(max_size=buffer_size)
        # 用于 prompt 截取:0 = 不限,实际用大数代替
        self._prompt_max = buffer_size if buffer_size > 0 else 1_000_000
        self._fallback_text = fallback_text
        self._fallback_kaomoji = fallback_kaomoji
        self._fallback_mood = fallback_mood
        self._fallback_language = fallback_language
        self._tts = tts
        self._audio_sink = audio_sink
        self._now_ms = now_ms
        # batch 状态
        self._last_batch_started_at_ms: float = -float("inf")
        self._batch_in_flight: bool = False

    def wire(self) -> None:
        """挂上 chat 触发回调。"""
        self._chat.on_trigger(self._on_trigger)

    async def _on_trigger(self, msg: ChatMessage) -> None:
        log.info("trigger: user=%s priority=%s body=%r",
                 msg.user, msg.is_priority, msg.body)
        if msg.is_priority:
            # VIP 路径:独立 task,跟 batch 完全并发
            asyncio.create_task(self._handle_priority(msg))
        else:
            await self._handle_regular(msg)

    # --------------------- VIP / Mod / Broadcaster ---------------------

    async def _handle_priority(self, msg: ChatMessage) -> None:
        if not self._vip_rl.try_acquire():
            log.info("vip rate-limited, drop: user=%s", msg.user)
            return

        try:
            reply = await self._llm.generate(self._build_single_messages(msg))
        except LLMError as e:
            log.warning("vip llm failed: %s — using fallback", e)
            reply = self._fallback_reply()

        log.info("vip reply: user=%s mood=%s lang=%s text=%r kaomoji=%r",
                 msg.user, reply.mood, reply.language, reply.text, reply.kaomoji)

        # 串行: TTS 完成后才发 chat
        await self._do_tts(reply.text, language=reply.language, user=msg.user)
        chat_body = (
            f"{reply.text} {reply.kaomoji}".strip() if reply.kaomoji else reply.text
        )
        await self._chat.send(f"@{msg.user} {chat_body}")

    # --------------------- 普通观众 ---------------------

    async def _handle_regular(self, msg: ChatMessage) -> None:
        # batch_window_s=0 → 普通路径完全禁用
        if self._batch_window_s <= 0:
            log.debug("batch path disabled (batch_window_s=0), drop regular")
            return

        now = self._now_ms()

        # cooldown: 距上次 flush 开始 < batch_cooldown_ms → silent drop
        if now - self._last_batch_started_at_ms < self._batch_cooldown_ms:
            log.debug("regular @ during cooldown, drop: user=%s", msg.user)
            return

        # 处理中 → silent drop
        if self._batch_in_flight:
            log.debug("regular @ during batch in-flight, drop: user=%s", msg.user)
            return

        # 加入 buffer。如果是空 buffer 的第一条,触发 scheduled_flush
        was_empty = self._buffer.is_empty()
        self._buffer.add(msg, now_ms=now)
        if was_empty:
            asyncio.create_task(self._scheduled_flush())

    async def _scheduled_flush(self) -> None:
        """在 first_at + batch_window_s 时 flush buffer。"""
        first_at = self._buffer.first_at_ms()
        if first_at is None:
            return  # 防御:已被清空

        # 计算还要等多久
        now = self._now_ms()
        elapsed_ms = now - first_at
        target_ms = self._batch_window_s * 1000
        sleep_s = max(0.0, (target_ms - elapsed_ms) / 1000)
        if sleep_s > 0:
            await asyncio.sleep(sleep_s)

        # 重新检查:buffer 可能已被 clear,或已有别人在 flush
        if self._buffer.is_empty():
            return
        if self._batch_in_flight:
            return

        # 启动 flush
        self._batch_in_flight = True
        self._last_batch_started_at_ms = self._now_ms()
        try:
            messages = self._buffer.latest_n(self._prompt_max)
            self._buffer.clear()
            await self._process_batch(messages)
        finally:
            self._batch_in_flight = False

    async def _process_batch(self, messages: list[ChatMessage]) -> None:
        try:
            reply = await self._llm.generate(self._build_batch_messages(messages))
        except LLMError as e:
            log.warning("batch llm failed: %s — using fallback", e)
            reply = self._fallback_reply()

        # 沉默:不发 chat 不调 TTS
        if not reply.text.strip():
            log.info("batch result: silence (batch_size=%d)", len(messages))
            return

        log.info("batch reply: batch_size=%d mood=%s lang=%s text=%r kaomoji=%r",
                 len(messages), reply.mood, reply.language, reply.text, reply.kaomoji)

        # batch 回复用 "batch" 作为 sink 的 user 标识
        await self._do_tts(reply.text, language=reply.language, user="batch")
        chat_body = (
            f"{reply.text} {reply.kaomoji}".strip() if reply.kaomoji else reply.text
        )
        await self._chat.send(chat_body)  # 注意:无 @user

    # --------------------- 共用 ---------------------

    async def _do_tts(self, text: str, *, language: Language, user: str) -> None:
        if self._tts is None or self._audio_sink is None:
            return
        if not text.strip():
            log.info("tts text is empty, skipping synthesis")
            return
        try:
            audio = await self._tts.synthesize(text, language=language)
        except TTSError as e:
            log.warning("tts synth failed: %s", e)
            return
        except Exception as e:  # noqa: BLE001
            log.exception("tts synth crashed unexpectedly: %s", e)
            return
        try:
            await self._audio_sink.write(audio, user=user)
        except Exception as e:  # noqa: BLE001
            log.warning("audio sink write failed: %s", e)

    def _fallback_reply(self) -> LLMReply:
        return LLMReply(
            text=self._fallback_text,
            kaomoji=self._fallback_kaomoji,
            mood=self._fallback_mood,
            language=self._fallback_language,
            raw="",
            latency_ms=0,
            tokens_in=0,
            tokens_out=0,
        )

    def _build_single_messages(self, msg: ChatMessage) -> list[LLMMessage]:
        system = self._persona.assemble(stream_ctx=self._stream_ctx.current())
        return [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=f"{msg.user}: {msg.body}"),
        ]

    def _build_batch_messages(self, messages: list[ChatMessage]) -> list[LLMMessage]:
        system = self._persona.assemble(stream_ctx=self._stream_ctx.current())
        lines = [f"[{i}] {m.user}: {m.body}" for i, m in enumerate(messages, 1)]
        user_content = (
            "下面是最近收到的普通观众 @G酱 消息(已按用户 dedup,每人最新一条):\n\n"
            + "\n".join(lines)
            + "\n\n请按你的人设标准从中挑选 1 个最值得回应的"
            + "(或合并相似的多条,用一句话呼应),不要 @ 任何人。"
            + " 实在没意思可保持沉默(text 留空字符串)。"
        )
        return [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=user_content),
        ]
```

### Step 5.2: 验证 import + 全套测试当前状态(很多 fail 是预期的,下个 task 重写 orchestrator 测试)

```bash
uv run python -c "from g_chan.orchestrator import Orchestrator; print('ok')"
uv run pytest 2>&1 | tail -5
```
Expected:
- import ok
- pytest 多个 orchestrator 测试 fail(RateLimitConfig 移除 + 构造签名变了)。这正常,Task 6 重写。

## Self-Review

- [ ] `Orchestrator.__init__` 接受新签名(vip_window_ms, batch_window_s, batch_cooldown_ms, buffer_size)
- [ ] `_handle_priority` 走 vip 路径
- [ ] `_handle_regular` 走 buffer 路径
- [ ] `_scheduled_flush` 在 first_at + window 后 flush
- [ ] cooldown 从 flush 开始计时(`_last_batch_started_at_ms` 在 flush start 时设置)
- [ ] silence 路径(text="")正确跳过 chat + TTS
- [ ] batch 路径 chat send **不带** @user
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- import 是否 ok
- 多少 orchestrator 测试 fail(预期,下个 task 修)

---

## Task 6: 重写 orchestrator 测试

**Files:**
- Modify: `tests/test_orchestrator.py`

完全重写。新测试覆盖 8 个关键场景。

### Step 6.1: 完整替换 `tests/test_orchestrator.py`

```python
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


# 测试默认配置:fallback 用 FB_ 占位,interaction 参数显式传
_FB_KWARGS = {
    "fallback_text": "FB_TEXT",
    "fallback_kaomoji": "FB_KAO",
    "fallback_mood": "dizzy",
    "fallback_language": "zh",
}


def _build_orch(
    *, chat, llm, clock,
    vip_window_ms=0,           # 默认无 vip 限流(简化测试)
    batch_window_s=2,
    batch_cooldown_ms=0,        # 默认无 cooldown
    buffer_size=10,
    tts=None, audio_sink=None,
):
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
        now_ms=clock,
        **_FB_KWARGS,
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
    # 仍在 10s 窗口内
    clock.advance(500)
    await chat.emit("modbob", "嗨", is_priority=True)

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
    # fallback 是 "FB_TEXT" + "FB_KAO"
    assert chat.sent == ["@modalice FB_TEXT FB_KAO"]


# ============= 普通观众批处理路径 =============

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
    await asyncio.sleep(0.1)

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
    await asyncio.sleep(0.1)

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
    await asyncio.sleep(0.1)

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
    await asyncio.sleep(0.1)   # 让第一个 batch flush

    assert chat.sent == ["回复1"]
    assert len(llm.calls) == 1

    # 仍在 cooldown 内,新 @ 应被 drop
    clock.advance(500)
    await chat.emit("bob", "嗨2")
    await asyncio.sleep(0.1)
    assert len(chat.sent) == 1   # bob 没触发
    assert len(llm.calls) == 1


@pytest.mark.asyncio
async def test_regular_batch_disabled_when_window_zero():
    """batch_window_s=0 → 普通观众完全不响应。"""
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("不应被调用", mood="happy")
    clock = FakeClock()
    orch = _build_orch(chat=chat, llm=llm, clock=clock, batch_window_s=0)
    orch.wire()

    await chat.emit("alice", "嗨")
    await asyncio.sleep(0.1)
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
    await asyncio.sleep(0.15)

    # 两条都应发出
    assert "@modalice VIP回复" in chat.sent
    assert "batch回复" in chat.sent   # 无 @
```

注意需要在文件顶部加 `import asyncio`(用于 asyncio.sleep)。

### Step 6.2: 跑 orchestrator 测试

```bash
uv run pytest tests/test_orchestrator.py -v
```
Expected: 10 个测试 pass。

### Step 6.3: 全套测试

```bash
uv run pytest 2>&1 | tail -3
```
Expected: 全套全绿(除了真正调外部 API 的 smoke 测试,本套件没有)。

### Step 6.4: ruff

```bash
uv run ruff check src tests 2>&1 | tail -3
```
Expected: All checks passed!(可能需要 `uv run ruff check --fix src tests` 修小的 import sort 之类)

## Self-Review

- [ ] orchestrator 测试 10 个 pass
- [ ] 全套测试全绿
- [ ] ruff 干净
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- 测试结果
- ruff 状态
- 任何 concerns

---

## Task 7: 更新 prompts/default.md 添加 batch 模式说明

**Files:**
- Modify: `prompts/default.md`

### Step 7.1: 在 `prompts/default.md` 末尾追加(在原有性格定义之后)

```markdown

## 批处理模式

有时你会在 user message 中收到 batch 形式的消息(普通观众的 @G酱 合集),格式如:

```
下面是最近收到的普通观众 @G酱 消息(已按用户 dedup,每人最新一条):

[1] alice: 你今天玩了啥
[2] bob: 笨蛋
[3] charlie: 哈哈
[4] dave: 我也想玩

请按你的人设标准从中挑选 1 个最值得回应的(或合并相似的多条,用一句话呼应),不要 @ 任何人。实在没意思可保持沉默(text 留空字符串)。
```

这种情况下你的行为:
- 选 1 条**你最感兴趣的**回应(可以合并相似的多条用一句话同时呼应它们)
- **不要 @ 任何人**,直接说出你的反应,像在自言自语回应整个 chat
- 跳过纯水(单字、单纯表情、刷屏)
- 重复 / 相似问题合并选一组
- 引发讨论的话题加分
- 实在没意思 → text 留空字符串 ""(选择沉默)
- 你不必回应所有人 —— 作为高中女生你有自己的注意力,挑你想答的

VIP / Mod / Broadcaster 的 @ 你会单独看到(单条 user 消息),那种**正常回应**,需要 @user。
```

### Step 7.2: 验证

```bash
uv run python -c "print(open('prompts/default.md').read()[-200:])"
```
Expected: 输出文件末尾,含上面追加的内容。

```bash
uv run pytest tests/test_persona_loader.py -v
```
Expected: 3 个 persona loader 测试仍 pass(prompts 内容变化不影响 loader 逻辑)。

## Self-Review

- [ ] `prompts/default.md` 末尾有"批处理模式"段落
- [ ] persona loader 测试仍 pass
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 8: 装配 __main__.py

**Files:**
- Modify: `src/g_chan/__main__.py`

把 Orchestrator 构造的 `rate_limit_ms=cfg.rate_limit.global_window_ms, busy_reply=cfg.rate_limit.busy_reply` 换成新的 interaction 字段。

### Step 8.1: Read 当前 `src/g_chan/__main__.py`

```bash
cat src/g_chan/__main__.py
```

### Step 8.2: 编辑 Orchestrator(...) 调用

找到类似:
```python
orch = Orchestrator(
    chat=chat, llm=llm, persona=persona, stream_ctx=sctx,
    rate_limit_ms=cfg.rate_limit.global_window_ms,
    busy_reply=cfg.rate_limit.busy_reply,
    fallback_text=cfg.llm.fallback.text,
    fallback_kaomoji=cfg.llm.fallback.kaomoji,
    fallback_mood=cfg.llm.fallback.mood,
    fallback_language=cfg.llm.fallback.language,
    tts=tts_engine,
    audio_sink=audio_sink,
)
```

替换为:
```python
orch = Orchestrator(
    chat=chat, llm=llm, persona=persona, stream_ctx=sctx,
    vip_window_ms=cfg.interaction.vip_window_ms,
    batch_window_s=cfg.interaction.batch_window_s,
    batch_cooldown_ms=cfg.interaction.batch_cooldown_ms,
    buffer_size=cfg.interaction.buffer_size,
    fallback_text=cfg.llm.fallback.text,
    fallback_kaomoji=cfg.llm.fallback.kaomoji,
    fallback_mood=cfg.llm.fallback.mood,
    fallback_language=cfg.llm.fallback.language,
    tts=tts_engine,
    audio_sink=audio_sink,
)
```

启动日志改成:
```python
log.info("starting G酱 — channel=#%s provider=%s vip_window=%dms batch=%.1fs cooldown=%dms buffer=%d",
         cfg.twitch.channel, cfg.llm.provider,
         cfg.interaction.vip_window_ms,
         cfg.interaction.batch_window_s,
         cfg.interaction.batch_cooldown_ms,
         cfg.interaction.buffer_size)
```

### Step 8.3: smoke check — 无 config 应该是 FileNotFoundError 而非 ImportError

```bash
mv config.yaml config.yaml.bak 2>/dev/null
uv run python -m g_chan
mv config.yaml.bak config.yaml 2>/dev/null
```
Expected: `FileNotFoundError: [Errno 2] No such file or directory: 'config.yaml'`.

### Step 8.4: 全套测试 + ruff

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```
Expected: pytest 全绿, ruff All checks passed.

### Step 8.5: 提醒用户更新本地 config.yaml

用户本地 `config.yaml` 还有旧的 `rate_limit:` 段。需要手动改成:

```yaml
interaction:
  vip_window_ms: 2000
  batch_window_s: 5
  batch_cooldown_ms: 5000
  buffer_size: 10
```

(旧的 `rate_limit:` 段可以保留 — pydantic 会 ignore 多余字段,但建议删除,保持配置干净。)

报告时把这段 yaml 贴出来给用户。

## Self-Review

- [ ] `__main__.py` 用新的 `cfg.interaction.*` 字段
- [ ] 启动日志包含新参数
- [ ] smoke check 报 FileNotFoundError 不报 import/NameError
- [ ] pytest 全绿
- [ ] ruff 干净
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- 测试结果

---

## Task 9: 端到端手动验证(用户做)

**Files:** 无新增。

### Step 9.1: 用户更新本地 `config.yaml`

替换 `rate_limit:` 段为:
```yaml
interaction:
  vip_window_ms: 2000
  batch_window_s: 5
  batch_cooldown_ms: 5000
  buffer_size: 10
```

### Step 9.2: 启动 bot

```bash
uv run python -m g_chan
```
Expected 启动日志:`starting G酱 — channel=#... provider=gemini vip_window=2000ms batch=5.0s cooldown=5000ms buffer=10`

### Step 9.3: 验证 VIP 即时路径

主播本人(broadcaster)在 chat 发 `@G酱 嗨`:
- **预期:** 1-2 秒内 chat 收到 `@<你的用户名> <内容> <颜文字>`
- **预期:** `out/` 多一个 mp3
- **预期:** 日志含 `priority=True`

### Step 9.4: 验证普通批处理路径

让别人(或开小号)用普通账号发 `@G酱 嗨`:
- **预期:** 5 秒后 chat 收到一条**不带 @你**的回复
- **预期:** `out/` 多一个 mp3,文件名前缀含 `batch`

### Step 9.5: 验证 batch dedup + 选择行为

让多个观众(或自己反复刷)在 5 秒内发不同问题。**预期:**
- 5 秒后 G酱 只发一条回复(不带 @)
- 内容是从你刷的几条里挑出来的(或合并)
- 重复刷同一句不会触发多次回复

### Step 9.6: 验证 cooldown drop

刚 batch 回复完后立刻再 @G酱(用普通号):
- **预期:** 接下来 5 秒内 G酱不响应
- **预期:** 日志含 `regular @ during cooldown, drop`

### Step 9.7: 验证沉默

如果 G酱 决定沉默(text=""):
- **预期:** chat 无回复
- **预期:** 日志含 `batch result: silence`
- **预期:** 下次 batch 仍能正常触发

### Step 9.8: VIP + 普通混合(如果有 mod 可以测)

让 mod 发 `@G酱 嗨` 同时有普通观众在刷 @:
- **预期:** mod 立即收到 @user 风格回复
- **预期:** 5 秒后普通观众这批也有一条不带 @ 的回复

---

## Phase 2.5 完成定义(Definition of Done)

- [ ] `uv run pytest` 全绿(约 71 + 10 - 13(orchestrator 旧测试)+ 10(orchestrator 新测试)+ 10(buffer 新)+ 3(interaction config 新) ≈ 91 tests)
- [ ] `uv run ruff check src tests` 干净
- [ ] `uv run python -m g_chan` 启动日志包含 `vip_window=... batch=...`
- [ ] Task 9 的 8 个验收点全部通过
- [ ] Twitch chat 中 mod / regular 两种身份的行为符合预期
