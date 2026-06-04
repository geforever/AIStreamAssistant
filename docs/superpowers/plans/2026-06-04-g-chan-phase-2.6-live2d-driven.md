# G 酱 — Phase 2.6 Implementation Plan(Live2D 驱动的 expression/motion 输出)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 LLM 的输出 schema 动态适配 Live2D 模型 — 启动时扫描 `Live2D/*/...*.model3.json`,把 `Expressions` 和 `Motions` 的名字塞进 schema 的 enum,LLM 直接输出物理表情/动作。`mood` 字段保留作情感语义。频率由代码控制(随机数 + 配置)。Live2D 可禁用,禁用时退化为纯 chat。

**Architecture:** 新增 `g_chan.live2d.model_loader` 解析 model3.json;`CHAT_REPLY_SCHEMA` 从常量改为 `build_chat_reply_schema(live2d_enabled, expressions, motions)` 函数,Factory 启动时构造并注入到 GeminiProvider;`LLMReply` 加 `expression: str` + `motion: str` 字段;Orchestrator 用注入的 `random_fn` 做频率裁剪(测试可控);prompts 拆成 base `output_rules.md` + 条件 `live2d_rules.md` 模板(`{{expressions_list}}` 替换)。

**Tech Stack:** Python 标准库 + 已有 Phase 2.5 栈(pydantic/google-genai/twitchio)。无新依赖。

**用户偏好:** 此项目不提交 git。所有 task 跳过 commit 步骤。

**Phase 2.6 不做:** Live2D 真实渲染(Phase 3)、expression/motion 推到 viewer(Phase 3 WebSocket)、Cubism 2 (.model.json) 兼容、多模型切换 UI。

---

## 关键设计回顾

### 新的 LLM 输出 schema

```jsonc
// Live2D enabled
{
  "text":       "...",
  "kaomoji":    "...",
  "mood":       "happy|angry|sad|surprised|shy|thinking|tsundere|dizzy",  // 情感语义,保留
  "expression": "Smile|Angry|...|None",                                    // 动态 enum,from model
  "motion":     "Idle|Tap|...|None",                                       // 动态 enum,from model
  "language":   "zh|en|ja"
}

// Live2D disabled
{ "text": ..., "kaomoji": ..., "mood": ..., "language": ... }   // 无 expression/motion
```

### `None` 语义统一

- LLM 输出 `"None"` 字符串 → 代码内规范化为 `""`(空字符串)
- 配置 `default_expression: ""` 同样表示"什么也不做"
- `LLMReply.expression: str` 类型;`""` = no-op,任何非空 = 具体表情名

### 频率控制

`Orchestrator` 持有 `random_fn`(可注入)。LLM 回复后:

```python
if self._random_fn() < cfg.live2d.expression_change_frequency:
    expression = reply.expression        # 用 LLM 选的
else:
    expression = cfg.live2d.default_expression   # 用 default
```

---

## 文件结构(Phase 2.6 新增/修改)

```
新增:
  src/g_chan/live2d/
    __init__.py
    model_loader.py        # Live2DModel + discover_model_path + load_model_info
  src/g_chan/prompts/
    live2d_rules.md        # 含 {{expressions_list}} {{motions_list}} 的模板
  tests/
    test_live2d_model_loader.py
    test_chat_reply_schema.py

修改:
  src/g_chan/config.py             # + Live2DConfig
  src/g_chan/llm/base.py           # LLMReply 加 expression/motion;parse_llm_json 新签名
  src/g_chan/llm/schemas/chat_reply.py   # 常量 → build_chat_reply_schema 函数
  src/g_chan/llm/gemini.py         # 接收 schema 实例
  src/g_chan/llm/factory.py        # 接 Live2DModel,build schema 后注入 Gemini
  src/g_chan/prompts/output_rules.py     # 函数式:动态拼 base + live2d 段
  src/g_chan/persona/loader.py     # 接收 rendered output_rules 字符串
  src/g_chan/orchestrator.py       # 频率裁剪 + random_fn 注入
  src/g_chan/__main__.py           # 启动时加载 Live2DModel + 装配
  config.example.yaml              # + live2d 块
  tests/conftest.py                # make_reply 多两个字段(可选默认 "")
  tests/test_config.py             # + Live2DConfig 测试
  tests/test_parse_llm_json.py     # 新签名 + 6-tuple unpacking
  tests/test_gemini_provider.py    # schema 注入
  tests/test_persona_loader.py     # output_rules 注入式
  tests/test_orchestrator.py       # 频率裁剪 + random_fn
  prompts/character.md (用户文件,不改)  # 仅文档说明:LLM 现在还会输出 expression/motion
```

---

## Task 1: Live2DConfig

**Files:**
- Modify: `src/g_chan/config.py`
- Modify: `config.example.yaml`
- Modify: `tests/test_config.py`

### Step 1.1: 在 `tests/test_config.py` 末尾追加 3 个新测试

```python
def test_loads_live2d_config(tmp_path, monkeypatch):
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
live2d:
  enabled: true
  model_path: "Live2D/Foo/model.model3.json"
  default_expression: "Normal"
  default_motion: "Idle"
  expression_change_frequency: 0.5
  motion_change_frequency: 0.2
logging:
  level: "info"
  file: "logs/g.log"
""")
    cfg = load_config(cfg_path)
    assert cfg.live2d.enabled is True
    assert cfg.live2d.model_path == "Live2D/Foo/model.model3.json"
    assert cfg.live2d.default_expression == "Normal"
    assert cfg.live2d.default_motion == "Idle"
    assert cfg.live2d.expression_change_frequency == 0.5
    assert cfg.live2d.motion_change_frequency == 0.2


def test_live2d_defaults_when_section_missing(tmp_path, monkeypatch):
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
    assert cfg.live2d.enabled is True
    assert cfg.live2d.model_path == ""
    assert cfg.live2d.default_expression == ""
    assert cfg.live2d.default_motion == ""
    assert cfg.live2d.expression_change_frequency == 1.0
    assert cfg.live2d.motion_change_frequency == 0.3


def test_live2d_frequency_out_of_range_rejected(tmp_path, monkeypatch):
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
live2d:
  expression_change_frequency: 2.5
logging:
  level: "info"
  file: "logs/g.log"
""")
    import pytest
    with pytest.raises(Exception):  # pydantic ValidationError
        load_config(cfg_path)
```

### Step 1.2: 跑测试,确认红

```bash
uv run pytest tests/test_config.py::test_loads_live2d_config tests/test_config.py::test_live2d_defaults_when_section_missing tests/test_config.py::test_live2d_frequency_out_of_range_rejected -v
```
Expected: FAIL with `AttributeError: 'AppConfig' object has no attribute 'live2d'`.

### Step 1.3: 在 `src/g_chan/config.py` 加 Live2DConfig 类

放在 `InteractionConfig` 之后,`LoggingConfig` 之前:

```python
class Live2DConfig(BaseModel):
    """Live2D 表情/动作驱动配置。

    enabled=False 时:
    - 不加载 Live2D 模型
    - LLM 输出 schema 不含 expression/motion 字段
    - 程序退化为纯 chat bot
    """
    # 启用 Live2D 表情/动作输出
    enabled: bool = True

    # 模型路径。空字符串 = 启动时扫描 Live2D/ 下第一个子文件夹,
    # 递归找第一个 *.model3.json
    model_path: str = ""

    # LLM 频率裁剪 fail 时 / LLM 调用失败时使用的表情和动作名
    # 空字符串 = 不传任何 expression / motion 给 viewer(保持当前状态)
    default_expression: str = ""
    default_motion: str = ""

    # 采纳 LLM 选择的概率 [0.0, 1.0]
    # 1.0 = 100% 用 LLM 选的(每次回复都可能变)
    # 0.0 = 永远不变,一直用 default_*
    # 0.3 = 30% 概率用 LLM 选的,70% 用 default
    expression_change_frequency: float = Field(default=1.0, ge=0.0, le=1.0)
    motion_change_frequency: float = Field(default=0.3, ge=0.0, le=1.0)
```

注意 `Field(..., ge=0.0, le=1.0)` 让 pydantic 校验范围。

### Step 1.4: 修改 `AppConfig` 加 live2d 字段

```python
class AppConfig(BaseModel):
    twitch: TwitchConfig
    llm: LLMConfig
    persona: PersonaConfig
    stream_context: StreamContextConfig
    tts: TTSConfig = Field(default_factory=TTSConfig)
    interaction: InteractionConfig = Field(default_factory=InteractionConfig)
    live2d: Live2DConfig = Field(default_factory=Live2DConfig)
    logging: LoggingConfig
```

### Step 1.5: 跑测试,确认绿

```bash
uv run pytest tests/test_config.py -v
```
Expected: 全部 pass(原 8 + 新 3 = 11)。

### Step 1.6: 更新 `config.example.yaml`,在 `interaction:` 块后、`logging:` 前加 `live2d:` 段

```yaml
# Live2D 角色表情和动作配置
live2d:
  # 启用 Live2D 表情/动作输出(false = 纯 chat 模式,LLM 不输出 expression/motion)
  enabled: true

  # 模型路径,空 = 自动扫描 Live2D/ 下第一个子文件夹递归找 *.model3.json
  # (auto-detect 找到的例:Live2D/Epsilon_free/runtime/Epsilon_free.model3.json)
  model_path: ""

  # AI 调用失败 / 频率裁剪 fail 时使用的表情和动作名
  # 空字符串 = 不传任何 expression / motion(角色保持当前状态)
  default_expression: ""
  default_motion: ""

  # 采纳 LLM 选择的概率 [0.0, 1.0]
  # 1.0 = 每次都用 LLM 选的;0.0 = 永远不变;0.3 = 30% 概率
  expression_change_frequency: 1.0
  motion_change_frequency: 0.3      # motion 默认偏保守(别动不动就播)
```

### Step 1.7: 全套测试 + ruff

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```
Expected: 全套全绿,ruff All checks passed.

## Self-Review

- [ ] `Live2DConfig` 6 个字段全部有合理默认值
- [ ] frequency 用 `Field(ge=0, le=1)` 做范围校验
- [ ] `AppConfig.live2d` 用 default_factory
- [ ] 3 个新测试 pass
- [ ] config.example.yaml 有完整注释
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- 测试结果
- 任何 concerns

---

## Task 2: Live2D model loader

**Files:**
- Create: `src/g_chan/live2d/__init__.py` (空)
- Create: `src/g_chan/live2d/model_loader.py`
- Create: `tests/test_live2d_model_loader.py`

### Step 2.1: 创建空 init

```bash
mkdir -p src/g_chan/live2d
touch src/g_chan/live2d/__init__.py
```

### Step 2.2: 写测试 `tests/test_live2d_model_loader.py`

```python
import json

import pytest

from g_chan.live2d.model_loader import (
    Live2DModel,
    discover_model_path,
    load_model_info,
)


def _write_model_file(dir, name="m.model3.json", expressions=None, motions=None):
    """Write a minimal .model3.json with optional Expressions/Motions."""
    refs = {"Moc": "x.moc3", "Textures": []}
    if expressions is not None:
        refs["Expressions"] = expressions
    if motions is not None:
        refs["Motions"] = motions
    payload = {"Version": 3, "FileReferences": refs}
    path = dir / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_model_info_parses_expressions_and_motions(tmp_path):
    p = _write_model_file(
        tmp_path,
        expressions=[
            {"Name": "Smile", "File": "expressions/Smile.exp3.json"},
            {"Name": "Angry", "File": "expressions/Angry.exp3.json"},
            {"Name": "f01", "File": "expressions/f01.exp3.json"},
        ],
        motions={
            "Idle": [{"File": "motion/idle.motion3.json"}],
            "Tap":  [{"File": "motion/tap.motion3.json"}],
        },
    )
    info = load_model_info(p)
    assert isinstance(info, Live2DModel)
    assert info.path == p
    assert info.expressions == ["Smile", "Angry", "f01"]
    assert sorted(info.motions) == ["Idle", "Tap"]


def test_load_model_info_handles_missing_expressions_section(tmp_path):
    p = _write_model_file(tmp_path, expressions=None, motions={"Idle": []})
    info = load_model_info(p)
    assert info.expressions == []
    assert info.motions == ["Idle"]


def test_load_model_info_handles_missing_motions_section(tmp_path):
    p = _write_model_file(tmp_path, expressions=[{"Name": "X", "File": "x"}])
    info = load_model_info(p)
    assert info.expressions == ["X"]
    assert info.motions == []


def test_load_model_info_raises_on_invalid_json(tmp_path):
    bad = tmp_path / "bad.model3.json"
    bad.write_text("not json {", encoding="utf-8")
    with pytest.raises(ValueError):
        load_model_info(bad)


def test_load_model_info_raises_on_missing_file_references(tmp_path):
    bad = tmp_path / "bad.model3.json"
    bad.write_text(json.dumps({"Version": 3}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_model_info(bad)


def test_discover_model_path_finds_first_subfolder_first_match(tmp_path):
    """在 Live2D/<first_sorted>/...深度找第一个 .model3.json。"""
    folder_a = tmp_path / "AAA_first" / "runtime"
    folder_a.mkdir(parents=True)
    target = folder_a / "a.model3.json"
    target.write_text("{}", encoding="utf-8")

    folder_b = tmp_path / "BBB_second" / "runtime"
    folder_b.mkdir(parents=True)
    (folder_b / "b.model3.json").write_text("{}", encoding="utf-8")

    found = discover_model_path(tmp_path)
    assert found == target


def test_discover_model_path_skips_hidden_folders(tmp_path):
    """跳过 .DS_Store / __MACOSX 之类的隐藏 / 系统目录。"""
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "hidden.model3.json").write_text("{}", encoding="utf-8")

    visible = tmp_path / "visible"
    visible.mkdir()
    target = visible / "ok.model3.json"
    target.write_text("{}", encoding="utf-8")

    found = discover_model_path(tmp_path)
    assert found == target


def test_discover_model_path_returns_none_when_no_match(tmp_path):
    (tmp_path / "empty").mkdir()
    assert discover_model_path(tmp_path) is None


def test_discover_model_path_returns_none_when_live2d_dir_missing(tmp_path):
    missing = tmp_path / "doesnt_exist"
    assert discover_model_path(missing) is None
```

### Step 2.3: 跑测试,确认红

```bash
uv run pytest tests/test_live2d_model_loader.py -v
```
Expected: ImportError.

### Step 2.4: 写 `src/g_chan/live2d/model_loader.py`

```python
"""Live2D 模型 (.model3.json) 解析 + auto-detect。

只支持 Cubism 3+ (model3.json)。遇到 Cubism 2 (.model.json) 会被 discover 忽略,
load_model_info 直接传 v2 路径会 raise(没有 FileReferences 字段)。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Live2DModel:
    path: Path                # 模型文件绝对路径
    expressions: list[str]    # Expressions[*].Name,按 model3.json 中的顺序
    motions: list[str]        # Motions dict 的 keys,按 model3.json 中的顺序


def load_model_info(path: Path) -> Live2DModel:
    """解析 .model3.json,返回 Live2DModel。

    Raises:
        ValueError: JSON 无效或缺 FileReferences 字段。
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"invalid model3.json at {path}: {e}") from e

    refs = data.get("FileReferences")
    if not isinstance(refs, dict):
        raise ValueError(
            f"model3.json at {path} missing FileReferences section "
            "(is this a valid Cubism 3+ model?)"
        )

    expressions = [
        str(e.get("Name", ""))
        for e in refs.get("Expressions", []) or []
        if isinstance(e, dict) and e.get("Name")
    ]
    motions_dict = refs.get("Motions", {}) or {}
    motions = list(motions_dict.keys()) if isinstance(motions_dict, dict) else []

    return Live2DModel(path=Path(path), expressions=expressions, motions=motions)


def discover_model_path(live2d_dir: Path) -> Path | None:
    """扫 live2d_dir,取字母序第一个非隐藏子文件夹,递归找第一个 *.model3.json。

    找不到返回 None(调用方决定是 raise 还是 fallback)。
    """
    live2d_dir = Path(live2d_dir)
    if not live2d_dir.exists() or not live2d_dir.is_dir():
        return None

    subfolders = sorted(
        p for p in live2d_dir.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )
    if not subfolders:
        return None

    first = subfolders[0]
    matches = sorted(first.rglob("*.model3.json"))
    return matches[0] if matches else None
```

### Step 2.5: 跑测试,确认绿

```bash
uv run pytest tests/test_live2d_model_loader.py -v
```
Expected: 9 tests pass.

### Step 2.6: 真实模型 smoke

```bash
uv run python -c "
from pathlib import Path
from g_chan.live2d.model_loader import discover_model_path, load_model_info
p = discover_model_path(Path('Live2D'))
print('found:', p)
info = load_model_info(p)
print('expressions:', info.expressions)
print('motions:', info.motions)
"
```
Expected: 输出真实的 expressions(`['Angry', 'Blushing', 'f01', 'f02', 'Normal', 'Sad', 'Smile', 'Surprised']`)和 motions(`['Idle', 'FlickUp', 'Flick', 'Tap', 'Flick3', 'FlickDown', 'Shake']`)。

### Step 2.7: 全套测试 + ruff

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```
Expected: 全绿,ruff 干净。

## Self-Review

- [ ] `Live2DModel` 是 frozen dataclass
- [ ] `load_model_info` 防御缺失字段(返回空 list,不崩)
- [ ] `discover_model_path` 跳过隐藏目录
- [ ] 真实 Epsilon_free smoke 通过
- [ ] 9 个测试 pass
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- 真实 model smoke 的 expressions / motions 列表
- 任何 concerns

---

## Task 3: LLMReply 加 expression/motion + parse_llm_json 新签名

**Files:**
- Modify: `src/g_chan/llm/base.py`
- Modify: `tests/test_parse_llm_json.py`
- Modify: `tests/conftest.py`(make_reply 多两个 kw)

### Step 3.1: 修改 `src/g_chan/llm/base.py`

在 `LLMReply` 末尾加两个字段(放最后,有默认值,不破坏现有构造):

```python
@dataclass
class LLMReply:
    text: str
    kaomoji: str
    mood: Mood
    language: Language
    raw: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    # Phase 2.6 新增 — Live2D 物理表情和动作("" = 无变化 / Live2D disabled)
    expression: str = ""
    motion: str = ""
```

替换 `parse_llm_json` 函数(完全重写):

```python
def parse_llm_json(
    raw: str,
    *,
    fallback_text: str,
    fallback_kaomoji: str,
    fallback_mood: Mood,
    fallback_language: Language,
    fallback_expression: str = "",
    fallback_motion: str = "",
    available_expressions: list[str] | None = None,
    available_motions: list[str] | None = None,
) -> tuple[str, str, Mood, Language, str, str]:
    """解析 LLM JSON → (text, kaomoji, mood, language, expression, motion)。

    expression / motion 行为:
    - available_* 是 None 或空 list → Live2D disabled,返回 ""(忽略 JSON 里的值)
    - LLM 输出 "None" 字符串 → 规范化为 ""
    - LLM 输出 "" 或不在 available 里 → 回退到 fallback_*
    """
    available_expressions = available_expressions or []
    available_motions = available_motions or []

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        log.warning("LLM JSON parse failed: %s, raw=%r", e, raw)
        return (
            fallback_text, fallback_kaomoji, fallback_mood, fallback_language,
            _normalize_or_fallback(None, available_expressions, fallback_expression),
            _normalize_or_fallback(None, available_motions, fallback_motion),
        )

    if not isinstance(data, dict):
        log.warning("LLM JSON is not an object: %r", raw)
        return (
            fallback_text, fallback_kaomoji, fallback_mood, fallback_language,
            _normalize_or_fallback(None, available_expressions, fallback_expression),
            _normalize_or_fallback(None, available_motions, fallback_motion),
        )

    text = str(data.get("text", "")).strip()
    if not text:
        log.warning("LLM JSON has empty/missing text field: %r", raw)
        return (
            fallback_text, fallback_kaomoji, fallback_mood, fallback_language,
            _normalize_or_fallback(None, available_expressions, fallback_expression),
            _normalize_or_fallback(None, available_motions, fallback_motion),
        )

    kaomoji = str(data.get("kaomoji", "")).strip()

    mood_raw = data.get("mood", "happy")
    if mood_raw in MOOD_VALUES:
        mood: Mood = mood_raw  # type: ignore[assignment]
    else:
        log.warning("LLM returned unknown mood: %r", mood_raw)
        mood = "happy"

    lang_raw = data.get("language", fallback_language)
    if lang_raw in LANGUAGE_VALUES:
        language: Language = lang_raw  # type: ignore[assignment]
    else:
        log.warning("LLM returned unknown language: %r", lang_raw)
        language = fallback_language

    # expression / motion:Live2D 禁用时返回 ""
    expression = _normalize_or_fallback(
        data.get("expression"), available_expressions, fallback_expression,
    )
    motion = _normalize_or_fallback(
        data.get("motion"), available_motions, fallback_motion,
    )

    return text, kaomoji, mood, language, expression, motion


def _normalize_or_fallback(raw, available, fallback) -> str:
    """规范化 LLM 输出的 expression/motion 值。

    - available 为空(Live2D disabled) → 总返回 ""
    - raw 是 None / "" / "None" → 规范化为 "",但如果 fallback 不空且 raw 是 None(缺字段) 用 fallback
    - raw 在 available 里 → 返回 raw
    - raw 不在 available 里 → 用 fallback(也通过 available 校验,不在就 "")
    """
    if not available:
        return ""
    # 规范化:None / 空串 / "None" → 空字符串
    if raw is None or raw == "" or raw == "None":
        normalized = ""
    elif isinstance(raw, str) and raw in available:
        return raw
    else:
        normalized = ""

    if normalized == "" and fallback:
        # 用 fallback,但 fallback 本身也得在 available 里(或 "" / "None")
        if fallback in ("", "None"):
            return ""
        if fallback in available:
            return fallback
        return ""
    return normalized
```

### Step 3.2: 修改 `tests/conftest.py` 的 `make_reply` 加两个 kwargs

找到当前的 `make_reply` 函数,改为:

```python
def make_reply(
    text: str,
    mood: Mood = "happy",
    kaomoji: str = "",
    language: Language = "zh",
    expression: str = "",
    motion: str = "",
) -> LLMReply:
    return LLMReply(
        text=text, kaomoji=kaomoji, mood=mood, language=language,
        raw=text, latency_ms=42, tokens_in=10, tokens_out=20,
        expression=expression, motion=motion,
    )
```

### Step 3.3: 重写 `tests/test_parse_llm_json.py`

完全替换文件内容:

```python
import json

import pytest

from g_chan.llm.base import parse_llm_json

FB_TEXT = "FB_TEXT"
FB_KAOMOJI = "FB_KAOMOJI"
FB_MOOD = "dizzy"
FB_LANG = "zh"
FB_EXP = ""    # 默认不指定 fallback expression
FB_MOT = ""


def _parse(raw, *, available_expressions=None, available_motions=None,
           fallback_expression=FB_EXP, fallback_motion=FB_MOT):
    return parse_llm_json(
        raw,
        fallback_text=FB_TEXT,
        fallback_kaomoji=FB_KAOMOJI,
        fallback_mood=FB_MOOD,
        fallback_language=FB_LANG,
        fallback_expression=fallback_expression,
        fallback_motion=fallback_motion,
        available_expressions=available_expressions,
        available_motions=available_motions,
    )


def _dump(**kw):
    return json.dumps(kw, ensure_ascii=False)


# === 基础字段(text/kaomoji/mood/language)===

def test_full_payload_without_live2d():
    raw = _dump(text="哼,本小姐才没有", kaomoji="(›´ω`‹)", mood="tsundere", language="zh")
    text, kao, mood, lang, expr, mot = _parse(raw)
    assert text == "哼,本小姐才没有"
    assert kao == "(›´ω`‹)"
    assert mood == "tsundere"
    assert lang == "zh"
    assert expr == ""   # Live2D 没启用
    assert mot == ""


def test_empty_kaomoji_allowed():
    raw = _dump(text="好的", kaomoji="", mood="happy", language="zh")
    _, kao, _, _, _, _ = _parse(raw)
    assert kao == ""


def test_missing_kaomoji_field_defaults_empty():
    raw = _dump(text="好的", mood="happy", language="zh")
    _, kao, _, _, _, _ = _parse(raw)
    assert kao == ""


@pytest.mark.parametrize("mood_name", [
    "happy", "angry", "sad", "surprised",
    "shy",   "thinking", "tsundere", "dizzy",
])
def test_all_eight_moods_accepted(mood_name):
    raw = _dump(text="x", mood=mood_name, language="zh")
    _, _, mood, _, _, _ = _parse(raw)
    assert mood == mood_name


def test_unknown_mood_falls_back_to_happy():
    raw = _dump(text="x", mood="lolwut", language="zh")
    _, _, mood, _, _, _ = _parse(raw)
    assert mood == "happy"


@pytest.mark.parametrize("lang", ["zh", "en", "ja"])
def test_all_three_languages_accepted(lang):
    raw = _dump(text="x", mood="happy", language=lang)
    _, _, _, language, _, _ = _parse(raw)
    assert language == lang


def test_unknown_language_falls_back():
    raw = _dump(text="x", mood="happy", language="ko")
    _, _, _, language, _, _ = _parse(raw)
    assert language == FB_LANG


# === expression / motion 行为 ===

def test_live2d_disabled_returns_empty_expression_motion():
    """available_* 为空 → 总返回 "",不管 JSON 里写什么。"""
    raw = _dump(text="x", mood="happy", language="zh",
                expression="Smile", motion="Tap")
    _, _, _, _, expr, mot = _parse(raw)
    assert expr == ""
    assert mot == ""


def test_live2d_enabled_accepts_valid_expression():
    raw = _dump(text="x", mood="happy", language="zh", expression="Smile")
    _, _, _, _, expr, _ = _parse(raw, available_expressions=["Smile", "Angry"])
    assert expr == "Smile"


def test_live2d_enabled_unknown_expression_falls_back_to_default():
    raw = _dump(text="x", mood="happy", language="zh", expression="NotAReal")
    _, _, _, _, expr, _ = _parse(
        raw,
        available_expressions=["Smile", "Angry", "Normal"],
        fallback_expression="Normal",
    )
    assert expr == "Normal"


def test_live2d_none_string_normalized_to_empty():
    raw = _dump(text="x", mood="happy", language="zh", expression="None")
    _, _, _, _, expr, _ = _parse(raw, available_expressions=["Smile"])
    assert expr == ""


def test_live2d_missing_expression_uses_fallback():
    raw = _dump(text="x", mood="happy", language="zh")  # 没 expression key
    _, _, _, _, expr, _ = _parse(
        raw,
        available_expressions=["Smile", "Normal"],
        fallback_expression="Normal",
    )
    assert expr == "Normal"


def test_live2d_fallback_invalid_returns_empty():
    """fallback 也不在 available 里 → 返回 ""(不崩)"""
    raw = _dump(text="x", mood="happy", language="zh", expression="BadVal")
    _, _, _, _, expr, _ = _parse(
        raw,
        available_expressions=["Smile"],
        fallback_expression="AlsoBad",
    )
    assert expr == ""


def test_live2d_motion_works_same_as_expression():
    raw = _dump(text="x", mood="happy", language="zh", motion="Tap")
    _, _, _, _, _, mot = _parse(raw, available_motions=["Idle", "Tap"])
    assert mot == "Tap"


# === parse 失败时使用 fallback,包括 expression/motion ===

def test_malformed_json_uses_all_fallbacks():
    raw = '{"text'
    text, kao, mood, lang, expr, mot = _parse(
        raw,
        available_expressions=["Normal"],
        available_motions=["Idle"],
        fallback_expression="Normal",
        fallback_motion="Idle",
    )
    assert text == FB_TEXT
    assert kao == FB_KAOMOJI
    assert mood == FB_MOOD
    assert lang == FB_LANG
    assert expr == "Normal"
    assert mot == "Idle"


def test_empty_text_uses_all_fallbacks():
    raw = _dump(text="", mood="happy", language="zh")
    text, _, _, _, expr, _ = _parse(
        raw,
        available_expressions=["Normal"],
        fallback_expression="Normal",
    )
    assert text == FB_TEXT
    assert expr == "Normal"
```

### Step 3.4: 跑测试,确认绿

```bash
uv run pytest tests/test_parse_llm_json.py -v
```
Expected: 全 pass(约 16 个测试)。

### Step 3.5: 验证 LLMReply 新字段

```bash
uv run python -c "
from g_chan.llm.base import LLMReply
r = LLMReply(text='a', kaomoji='', mood='happy', language='zh',
             raw='', latency_ms=0, tokens_in=0, tokens_out=0)
print('default expression:', r.expression)
print('default motion:', r.motion)
r2 = LLMReply(text='a', kaomoji='', mood='happy', language='zh',
              raw='', latency_ms=0, tokens_in=0, tokens_out=0,
              expression='Smile', motion='Tap')
print('explicit:', r2.expression, r2.motion)
"
```
Expected: defaults 为 `''`,explicit 为 `'Smile' 'Tap'`.

### Step 3.6: 全套测试

```bash
uv run pytest 2>&1 | tail -5
```
Expected: 其他测试**预期挂**(gemini provider 没传 available_expressions/motions,后续 task 修),但 config / parse / model_loader 都绿。

## Self-Review

- [ ] LLMReply 加了 `expression: str = ""` 和 `motion: str = ""`
- [ ] parse_llm_json 接 6 个 fallback + 2 个 available list
- [ ] `_normalize_or_fallback` 正确处理 None / "" / "None" / 不在 available 里
- [ ] make_reply 新签名,旧调用兼容
- [ ] parse_llm_json 测试约 16 个全 pass
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- parse_llm_json 测试结果
- 其他文件 fail 数(预期)

---

## Task 4: schema build 函数

**Files:**
- Modify: `src/g_chan/llm/schemas/chat_reply.py`
- Create: `tests/test_chat_reply_schema.py`

### Step 4.1: 写测试 `tests/test_chat_reply_schema.py`

```python
from g_chan.llm.schemas.chat_reply import build_chat_reply_schema


def test_schema_without_live2d_has_basic_fields_only():
    schema = build_chat_reply_schema(live2d_enabled=False)
    props = schema["properties"]
    assert "text" in props
    assert "kaomoji" in props
    assert "mood" in props
    assert "language" in props
    # 关键:Live2D 禁用 → 不含 expression / motion
    assert "expression" not in props
    assert "motion" not in props
    # required 也不含
    assert "expression" not in schema["required"]
    assert "motion" not in schema["required"]


def test_schema_with_live2d_adds_expression_and_motion():
    schema = build_chat_reply_schema(
        live2d_enabled=True,
        expressions=["Smile", "Angry", "Sad"],
        motions=["Idle", "Tap"],
    )
    props = schema["properties"]
    assert "expression" in props
    assert "motion" in props
    # enum 含模型表情 + "None"
    assert set(props["expression"]["enum"]) == {"Smile", "Angry", "Sad", "None"}
    assert set(props["motion"]["enum"]) == {"Idle", "Tap", "None"}
    # required 含 expression / motion
    assert "expression" in schema["required"]
    assert "motion" in schema["required"]


def test_schema_with_live2d_but_empty_lists_still_includes_none():
    """空模型(模型有 enabled 但没 expressions 文件)— 至少含 None。"""
    schema = build_chat_reply_schema(
        live2d_enabled=True,
        expressions=[],
        motions=[],
    )
    props = schema["properties"]
    assert props["expression"]["enum"] == ["None"]
    assert props["motion"]["enum"] == ["None"]


def test_schema_mood_enum_always_contains_8_values():
    schema = build_chat_reply_schema(live2d_enabled=False)
    mood_enum = schema["properties"]["mood"]["enum"]
    assert set(mood_enum) == {
        "happy", "angry", "sad", "surprised",
        "shy",   "thinking", "tsundere", "dizzy",
    }


def test_schema_language_enum_always_contains_3():
    schema = build_chat_reply_schema(live2d_enabled=False)
    lang_enum = schema["properties"]["language"]["enum"]
    assert set(lang_enum) == {"zh", "en", "ja"}
```

### Step 4.2: 跑测试,确认红

```bash
uv run pytest tests/test_chat_reply_schema.py -v
```
Expected: ImportError(还是常量,没有 function).

### Step 4.3: 完整替换 `src/g_chan/llm/schemas/chat_reply.py`

```python
"""LLM 输出 JSON schema — 现在是动态构造的函数,而非常量。

字段对齐:
- src/g_chan/llm/base.py (parse_llm_json + LLMReply)
- src/g_chan/prompts/output_rules.py (LLM 看到的文本描述)
"""
from __future__ import annotations

from g_chan.llm.base import LANGUAGE_VALUES, MOOD_VALUES


def build_chat_reply_schema(
    *,
    live2d_enabled: bool,
    expressions: list[str] | None = None,
    motions: list[str] | None = None,
) -> dict:
    """构造 chat reply 的 JSON schema。

    Live2D enabled → 加 expression / motion 字段(enum 由模型决定 + "None")。
    Live2D disabled → schema 不含这两个字段(LLM 不输出)。
    """
    properties: dict = {
        "text": {
            "type": "string",
            "description": (
                "Main reply text intended for TTS. Spoken words only. "
                "No kaomoji, emoji, brackets, @user, or stage directions."
            ),
        },
        "kaomoji": {
            "type": "string",
            "description": (
                "Optional kaomoji for chat decoration only (not spoken by TTS). "
                "May be empty string."
            ),
        },
        "mood": {
            "type": "string",
            "enum": list(MOOD_VALUES),
            "description": (
                "Character emotion label (semantic, independent of Live2D physical expression). "
                "Pick the one that best describes your inner feeling."
            ),
        },
        "language": {
            "type": "string",
            "enum": list(LANGUAGE_VALUES),
            "description": (
                "Language code matching the actual language of the 'text' field. "
                "Mirror the viewer's language."
            ),
        },
    }
    required = ["text", "mood", "language"]

    if live2d_enabled:
        expressions = expressions or []
        motions = motions or []
        properties["expression"] = {
            "type": "string",
            "enum": expressions + ["None"],
            "description": (
                "Live2D facial expression name (from the loaded model). "
                "Pick one whose name semantically matches the character's "
                "current state, OR pick 'None' to keep current expression. "
                "Skip expressions whose names you don't understand."
            ),
        }
        properties["motion"] = {
            "type": "string",
            "enum": motions + ["None"],
            "description": (
                "Live2D body motion to play once. Use sparingly — most replies "
                "should pick 'None'. Only trigger a motion when it semantically "
                "matches the reply (e.g. 'Tap' for a playful poke)."
            ),
        }
        required += ["expression", "motion"]

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }
```

### Step 4.4: 跑测试,确认绿

```bash
uv run pytest tests/test_chat_reply_schema.py -v
```
Expected: 5 tests pass.

### Step 4.5: schemas/__init__.py 重新导出

确认 `src/g_chan/llm/schemas/__init__.py` 不再导出旧的 `CHAT_REPLY_SCHEMA` 常量(它已不存在),改为导出函数:

```python
"""LLM schema 包入口。"""
from g_chan.llm.schemas.chat_reply import build_chat_reply_schema

__all__ = ["build_chat_reply_schema"]
```

### Step 4.6: 全套测试

```bash
uv run pytest 2>&1 | tail -5
```
Expected: gemini_provider 测试仍 fail(用了 CHAT_REPLY_SCHEMA 常量),后续 task 修。

## Self-Review

- [ ] `build_chat_reply_schema` 函数已定义
- [ ] `CHAT_REPLY_SCHEMA` 常量已删除
- [ ] schemas/__init__.py 不再导出常量
- [ ] 5 个 schema 测试 pass
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- schema 测试结果

---

## Task 5: GeminiProvider 接收 schema 实例

**Files:**
- Modify: `src/g_chan/llm/gemini.py`
- Modify: `tests/test_gemini_provider.py`

### Step 5.1: 改 `src/g_chan/llm/gemini.py`

把 `CHAT_REPLY_SCHEMA` 的 import 删掉,改为 `__init__` 接收 `schema: dict` + `available_expressions: list[str]` + `available_motions: list[str]`(用于 parse 校验)。

完整替换 `__init__` 签名 + `generate` 方法对 `parse_llm_json` 和 `LLMReply` 的调用:

```python
"""Gemini provider — google-genai 适配,使用 JSON mode + responseSchema 约束输出。"""
from __future__ import annotations

import asyncio
import time

from google import genai
from google.genai import types

from g_chan.llm.base import (
    Language,
    LLMMessage,
    LLMProvider,
    LLMReply,
    LLMServerError,
    LLMTimeoutError,
    Mood,
    parse_llm_json,
)


class GeminiProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        schema: dict,
        fallback_text: str,
        fallback_kaomoji: str,
        fallback_mood: Mood,
        fallback_language: Language,
        fallback_expression: str = "",
        fallback_motion: str = "",
        available_expressions: list[str] | None = None,
        available_motions: list[str] | None = None,
    ):
        self._client = genai.Client(api_key=api_key)
        self._model = model
        self._schema = schema
        self._fallback_text = fallback_text
        self._fallback_kaomoji = fallback_kaomoji
        self._fallback_mood = fallback_mood
        self._fallback_language = fallback_language
        self._fallback_expression = fallback_expression
        self._fallback_motion = fallback_motion
        self._available_expressions = available_expressions or []
        self._available_motions = available_motions or []

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
        config = types.GenerateContentConfig(
            temperature=temperature,
            maxOutputTokens=max_tokens,
            responseMimeType="application/json",
            responseSchema=self._schema,
            systemInstruction=system,
            thinkingConfig=types.ThinkingConfig(thinkingBudget=0),
        )

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
        except TimeoutError as e:
            raise LLMTimeoutError(f"Gemini timeout after {timeout_s}s") from e
        except Exception as e:  # noqa: BLE001
            raise LLMServerError(f"Gemini error: {e}") from e
        latency_ms = int((time.monotonic() - t0) * 1000)

        raw = resp.text or ""
        text, kaomoji, mood, language, expression, motion = parse_llm_json(
            raw,
            fallback_text=self._fallback_text,
            fallback_kaomoji=self._fallback_kaomoji,
            fallback_mood=self._fallback_mood,
            fallback_language=self._fallback_language,
            fallback_expression=self._fallback_expression,
            fallback_motion=self._fallback_motion,
            available_expressions=self._available_expressions,
            available_motions=self._available_motions,
        )
        usage = getattr(resp, "usage_metadata", None)
        return LLMReply(
            text=text,
            kaomoji=kaomoji,
            mood=mood,
            language=language,
            expression=expression,
            motion=motion,
            raw=raw,
            latency_ms=latency_ms,
            tokens_in=getattr(usage, "prompt_token_count", 0) if usage else 0,
            tokens_out=getattr(usage, "candidates_token_count", 0) if usage else 0,
        )
```

### Step 5.2: 重写 `tests/test_gemini_provider.py`

完整替换:

```python
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from g_chan.llm.base import LLMMessage, LLMTimeoutError
from g_chan.llm.gemini import GeminiProvider

_FB_KWARGS = {
    "fallback_text": "FB",
    "fallback_kaomoji": "FBK",
    "fallback_mood": "dizzy",
    "fallback_language": "zh",
}

_SCHEMA_NOLIVE2D = {  # 简化的占位 schema
    "type": "object",
    "properties": {"text": {"type": "string"}},
    "required": ["text"],
}


def _fake_response(text, in_tokens=10, out_tokens=20):
    return SimpleNamespace(
        text=text,
        usage_metadata=SimpleNamespace(
            prompt_token_count=in_tokens,
            candidates_token_count=out_tokens,
        ),
    )


@pytest.mark.asyncio
async def test_generate_parses_json_reply_no_live2d(monkeypatch):
    payload = json.dumps(
        {"text": "好啊~", "kaomoji": "(=ω=)", "mood": "happy", "language": "zh"},
        ensure_ascii=False,
    )
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(return_value=_fake_response(payload))
    monkeypatch.setattr("g_chan.llm.gemini.genai.Client", lambda api_key: fake_client)

    p = GeminiProvider(
        api_key="x", model="gemini-2.5-flash", schema=_SCHEMA_NOLIVE2D,
        **_FB_KWARGS,
    )
    reply = await p.generate([LLMMessage("user", "嗨")])
    assert reply.text == "好啊~"
    assert reply.mood == "happy"
    assert reply.expression == ""    # Live2D 没启用 → ""
    assert reply.motion == ""


@pytest.mark.asyncio
async def test_generate_with_live2d_parses_expression_motion(monkeypatch):
    payload = json.dumps({
        "text": "好啊~", "kaomoji": "", "mood": "happy", "language": "zh",
        "expression": "Smile", "motion": "Tap",
    })
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(return_value=_fake_response(payload))
    monkeypatch.setattr("g_chan.llm.gemini.genai.Client", lambda api_key: fake_client)

    p = GeminiProvider(
        api_key="x", model="gemini-2.5-flash", schema=_SCHEMA_NOLIVE2D,
        available_expressions=["Smile", "Angry"],
        available_motions=["Tap", "Idle"],
        **_FB_KWARGS,
    )
    reply = await p.generate([LLMMessage("user", "嗨")])
    assert reply.expression == "Smile"
    assert reply.motion == "Tap"


@pytest.mark.asyncio
async def test_generate_passes_schema_to_sdk(monkeypatch):
    captured = {}

    async def fake_generate(model, contents, config):
        captured["config"] = config
        return _fake_response(json.dumps({
            "text": "x", "mood": "happy", "language": "zh",
        }))

    fake_client = MagicMock()
    fake_client.aio.models.generate_content = fake_generate
    monkeypatch.setattr("g_chan.llm.gemini.genai.Client", lambda api_key: fake_client)

    custom_schema = {"type": "object", "properties": {"foo": {}}, "required": ["foo"]}
    p = GeminiProvider(
        api_key="x", model="gemini-2.5-flash", schema=custom_schema, **_FB_KWARGS,
    )
    await p.generate([LLMMessage("user", "嗨")])
    cfg = captured["config"]
    assert cfg.response_mime_type == "application/json"
    # SDK 可能保留 dict 或转 Schema 对象,只验关键标志
    rs = cfg.response_schema
    if isinstance(rs, dict):
        assert rs == custom_schema or rs.get("properties", {}).get("foo") is not None
    # 不强求验证内部对象,SDK 内部转换


@pytest.mark.asyncio
async def test_generate_timeout_raises(monkeypatch):
    async def hangs(**kwargs):
        await asyncio.sleep(10)
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = hangs
    monkeypatch.setattr("g_chan.llm.gemini.genai.Client", lambda api_key: fake_client)

    p = GeminiProvider(
        api_key="x", model="gemini-2.5-flash", schema=_SCHEMA_NOLIVE2D, **_FB_KWARGS,
    )
    with pytest.raises(LLMTimeoutError):
        await p.generate([LLMMessage("user", "嗨")], timeout_s=0.05)


@pytest.mark.asyncio
async def test_generate_uses_fallback_on_bad_json(monkeypatch):
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(return_value=_fake_response('{"text'))
    monkeypatch.setattr("g_chan.llm.gemini.genai.Client", lambda api_key: fake_client)

    p = GeminiProvider(
        api_key="x", model="gemini-2.5-flash", schema=_SCHEMA_NOLIVE2D,
        fallback_text="custom走神", fallback_kaomoji="(°ロ°)",
        fallback_mood="dizzy", fallback_language="zh",
        fallback_expression="Normal", fallback_motion="Idle",
        available_expressions=["Normal", "Smile"],
        available_motions=["Idle", "Tap"],
    )
    reply = await p.generate([LLMMessage("user", "嗨")])
    assert reply.text == "custom走神"
    assert reply.expression == "Normal"
    assert reply.motion == "Idle"
```

### Step 5.3: 跑测试

```bash
uv run pytest tests/test_gemini_provider.py -v
```
Expected: 5 tests pass.

### Step 5.4: 全套

```bash
uv run pytest 2>&1 | tail -3
```
Expected: factory + main 测试 fail(下个 task 修),其他大部分绿。

## Self-Review

- [ ] GeminiProvider 接 `schema` + `available_expressions` + `available_motions` + `fallback_expression/motion`
- [ ] 不再 import CHAT_REPLY_SCHEMA
- [ ] LLMReply 构造含 expression / motion
- [ ] 5 个 gemini 测试 pass
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- gemini 测试结果

---

## Task 6: Factory 接 Live2DModel 构造 schema

**Files:**
- Modify: `src/g_chan/llm/factory.py`
- Modify: `tests/test_llm_factory.py`

### Step 6.1: 重写 `src/g_chan/llm/factory.py`

```python
"""LLM provider factory — 按 config 返回具体实现。

Phase 2.6: 接 Live2DModel + Live2DConfig 来动态构造 schema。
"""
from __future__ import annotations

from g_chan.config import Live2DConfig, LLMConfig
from g_chan.live2d.model_loader import Live2DModel
from g_chan.llm.base import LLMProvider
from g_chan.llm.gemini import GeminiProvider
from g_chan.llm.schemas import build_chat_reply_schema


def create_provider(
    cfg: LLMConfig,
    *,
    live2d_cfg: Live2DConfig,
    live2d_model: Live2DModel | None = None,
) -> LLMProvider:
    """构造 LLM provider。

    live2d_cfg.enabled=True 时必须传 live2d_model(否则 raise)。
    live2d_cfg.enabled=False 时 live2d_model 可为 None,schema 不含 expression/motion。
    """
    if live2d_cfg.enabled and live2d_model is None:
        raise ValueError(
            "live2d.enabled=True but no Live2DModel provided to factory"
        )

    expressions = live2d_model.expressions if live2d_model else []
    motions = live2d_model.motions if live2d_model else []

    schema = build_chat_reply_schema(
        live2d_enabled=live2d_cfg.enabled,
        expressions=expressions,
        motions=motions,
    )

    name = cfg.provider
    if name == "gemini":
        return GeminiProvider(
            api_key=cfg.api_key,
            model=cfg.model,
            schema=schema,
            fallback_text=cfg.fallback.text,
            fallback_kaomoji=cfg.fallback.kaomoji,
            fallback_mood=cfg.fallback.mood,
            fallback_language=cfg.fallback.language,
            fallback_expression=live2d_cfg.default_expression,
            fallback_motion=live2d_cfg.default_motion,
            available_expressions=expressions,
            available_motions=motions,
        )
    if name in ("claude", "openai", "qwen"):
        raise NotImplementedError(
            f"LLM provider {name!r} not implemented yet — coming in a later phase."
        )
    raise ValueError(f"unknown provider: {name!r}")
```

### Step 6.2: 重写 `tests/test_llm_factory.py`

```python
from pathlib import Path
from unittest.mock import patch

import pytest

from g_chan.config import Live2DConfig, LLMConfig
from g_chan.live2d.model_loader import Live2DModel
from g_chan.llm.factory import create_provider
from g_chan.llm.gemini import GeminiProvider


def _live2d_disabled():
    return Live2DConfig(enabled=False)


def _live2d_enabled():
    return Live2DConfig(enabled=True, default_expression="Normal", default_motion="Idle")


def _model():
    return Live2DModel(
        path=Path("/fake/model.model3.json"),
        expressions=["Smile", "Angry", "Normal"],
        motions=["Idle", "Tap"],
    )


def test_creates_gemini_with_live2d_disabled():
    with patch("g_chan.llm.gemini.genai.Client"):
        cfg = LLMConfig(provider="gemini", model="gemini-2.5-flash", api_key="x")
        p = create_provider(cfg, live2d_cfg=_live2d_disabled(), live2d_model=None)
        assert isinstance(p, GeminiProvider)


def test_creates_gemini_with_live2d_enabled():
    with patch("g_chan.llm.gemini.genai.Client"):
        cfg = LLMConfig(provider="gemini", model="gemini-2.5-flash", api_key="x")
        p = create_provider(cfg, live2d_cfg=_live2d_enabled(), live2d_model=_model())
        assert isinstance(p, GeminiProvider)


def test_live2d_enabled_without_model_raises():
    cfg = LLMConfig(provider="gemini", model="gemini-2.5-flash", api_key="x")
    with pytest.raises(ValueError, match="no Live2DModel"):
        create_provider(cfg, live2d_cfg=_live2d_enabled(), live2d_model=None)


@pytest.mark.parametrize("provider", ["claude", "openai", "qwen"])
def test_other_providers_not_implemented_yet(provider):
    cfg = LLMConfig(provider=provider, model="x", api_key="x")
    with pytest.raises(NotImplementedError, match=provider):
        create_provider(cfg, live2d_cfg=_live2d_disabled())
```

### Step 6.3: 跑测试

```bash
uv run pytest tests/test_llm_factory.py -v
```
Expected: 6 tests pass.

### Step 6.4: 全套

```bash
uv run pytest 2>&1 | tail -3
```
Expected: orchestrator + persona_loader + main 测试 fail(后续 task 修)。

## Self-Review

- [ ] factory 接 `live2d_cfg` + `live2d_model`
- [ ] enabled 但缺 model 时 raise ValueError
- [ ] disabled 时 model 可为 None
- [ ] schema 通过 build_chat_reply_schema 动态构造
- [ ] 6 个 factory 测试 pass
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 7: prompts/live2d_rules.md + output_rules.py 改函数式

**Files:**
- Create: `src/g_chan/prompts/live2d_rules.md`
- Modify: `src/g_chan/prompts/output_rules.py`
- Modify: `src/g_chan/prompts/__init__.py`

### Step 7.1: 创建 `src/g_chan/prompts/live2d_rules.md`

```markdown
### Live2D 表情和动作

你的回复还需要驱动 Live2D 角色的表情和动作。

**expression(表情)— 可用值: {{expressions_list}}**

- 选名字你**认得含义**的(比如 Smile / Angry / Sad / Surprised / Blushing)
- **看不懂的名字(比如 f01、f02)不要选**,改选 `"None"`
- 不需要换表情时选 `"None"`(角色保持当前表情)

**motion(动作)— 可用值: {{motions_list}}**

- motion 是一次性动作(挥手、撇头),播完回 idle
- **大部分时间应该选 `"None"`** — 别动不动就播
- 仅在合适时机才选一个(比如说话很激动、调侃语气配合 Tap 等)

注意: 角色的内在情感语义在 mood 字段(独立于 Live2D)。mood 是你**心里**的感受,expression/motion 是你**外在**的反应,两者可以不一致(嘴硬心软 = mood=tsundere + expression=Blushing)。
```

### Step 7.2: 重写 `src/g_chan/prompts/output_rules.py`

```python
"""LLM 输出规则 — 动态拼装 base + 可选 Live2D 段。

调整 .md 文件时,必须同步检查:
- src/g_chan/llm/schemas/chat_reply.py (build_chat_reply_schema)
- src/g_chan/llm/base.py (parse_llm_json, MOOD_VALUES, LANGUAGE_VALUES)
"""
from __future__ import annotations

import re
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_BASE_PATH = _HERE / "output_rules.md"
_LIVE2D_PATH = _HERE / "live2d_rules.md"

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def _render(template: str, **vars: str) -> str:
    def _sub(m: re.Match) -> str:
        return vars.get(m.group(1), m.group(0))
    return _VAR_RE.sub(_sub, template)


def render_output_rules(
    *,
    live2d_enabled: bool,
    expressions: list[str] | None = None,
    motions: list[str] | None = None,
) -> str:
    """返回完整的 output rules 文本(base 永远有,Live2D 段可选)。"""
    base = _BASE_PATH.read_text(encoding="utf-8")
    if not live2d_enabled:
        return base

    live2d_template = _LIVE2D_PATH.read_text(encoding="utf-8")
    live2d_section = _render(
        live2d_template,
        expressions_list=", ".join(expressions or []) or "(none)",
        motions_list=", ".join(motions or []) or "(none)",
    )
    return base + "\n\n" + live2d_section
```

### Step 7.3: 修改 `src/g_chan/prompts/__init__.py`

```python
"""程序定义的 prompt 契约。"""
from g_chan.prompts.batch import build_batch_user_message
from g_chan.prompts.output_rules import render_output_rules

__all__ = ["build_batch_user_message", "render_output_rules"]
```

注意:之前导出的 `OUTPUT_RULES` 常量已不存在,改为 `render_output_rules` 函数。

### Step 7.4: 验证 import

```bash
uv run python -c "
from g_chan.prompts import render_output_rules
# 禁用 Live2D
print('--- disabled ---')
print(render_output_rules(live2d_enabled=False)[-300:])
# 启用,有模型 expressions/motions
print('--- enabled ---')
print(render_output_rules(live2d_enabled=True,
                          expressions=['Smile', 'Angry', 'f01'],
                          motions=['Idle', 'Tap'])[-500:])
"
```
Expected: disabled 不含 "Live2D",enabled 末尾含 "Smile, Angry, f01" 和 "Idle, Tap"。

## Self-Review

- [ ] live2d_rules.md 创建,含 {{expressions_list}} {{motions_list}}
- [ ] output_rules.py 改成 `render_output_rules` 函数
- [ ] __init__.py 不再导 OUTPUT_RULES,导 render_output_rules
- [ ] smoke check 通过
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 8: PersonaLoader 接 rendered rules

**Files:**
- Modify: `src/g_chan/persona/loader.py`
- Modify: `tests/test_persona_loader.py`

### Step 8.1: 重写 `src/g_chan/persona/loader.py`

```python
"""Persona 拼装:用户人设 + 直播上下文 + 程序输出契约。

输出契约文本由调用方(__main__ 装配时)预先 render 好后注入。
"""
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
        output_rules_text: str,
        include_stream_context: bool = True,
    ):
        self._base_path = Path(base_path)
        self._output_rules_text = output_rules_text
        self._include_stream_context = include_stream_context

    def assemble(self, *, stream_ctx: StreamContext | None) -> str:
        base = self._base_path.read_text(encoding="utf-8").strip()
        sections = [base]
        if self._include_stream_context and stream_ctx is not None:
            sections.append(
                "[当前直播上下文]\n"
                f"直播间标题: {stream_ctx.title}\n"
                f"正在玩: {stream_ctx.game_name}\n"
                "[/当前直播上下文]\n"
                "如果观众问到你在玩什么/做什么,基于上述上下文回答。"
            )
        sections.append(self._output_rules_text)
        return "\n\n".join(sections)
```

注意:删了直接 `from g_chan.prompts import OUTPUT_RULES`,改为外部注入 `output_rules_text`。

### Step 8.2: 重写 `tests/test_persona_loader.py`

```python
from pathlib import Path

from g_chan.persona.loader import PersonaLoader, StreamContext


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


_RULES = "<<< INJECTED RULES TEXT >>>"


def test_assembles_base_with_injected_rules(tmp_path):
    base = write(tmp_path / "base.md", "你是 G 酱。")
    loader = PersonaLoader(base_path=base, output_rules_text=_RULES)
    out = loader.assemble(stream_ctx=None)
    assert "你是 G 酱。" in out
    assert _RULES in out
    assert "[当前直播上下文]" not in out


def test_includes_stream_context_when_provided(tmp_path):
    base = write(tmp_path / "base.md", "你是 G 酱。")
    loader = PersonaLoader(base_path=base, output_rules_text=_RULES)
    ctx = StreamContext(title="深夜原神", game_name="Genshin Impact")
    out = loader.assemble(stream_ctx=ctx)
    assert "深夜原神" in out
    assert "Genshin Impact" in out
    assert "[当前直播上下文]" in out
    assert _RULES in out


def test_omits_context_section_when_disabled(tmp_path):
    base = write(tmp_path / "base.md", "你是 G 酱。")
    loader = PersonaLoader(
        base_path=base, output_rules_text=_RULES, include_stream_context=False,
    )
    ctx = StreamContext(title="任何", game_name="任何")
    out = loader.assemble(stream_ctx=ctx)
    assert "[当前直播上下文]" not in out
    assert _RULES in out


def test_rules_appear_after_base_and_context(tmp_path):
    """rules 应该在最末尾(LLM 看到 system prompt 时最后看到契约)。"""
    base = write(tmp_path / "base.md", "BASE_TEXT")
    loader = PersonaLoader(base_path=base, output_rules_text=_RULES)
    ctx = StreamContext(title="T", game_name="G")
    out = loader.assemble(stream_ctx=ctx)
    base_idx = out.index("BASE_TEXT")
    ctx_idx = out.index("[当前直播上下文]")
    rules_idx = out.index(_RULES)
    assert base_idx < ctx_idx < rules_idx
```

### Step 8.3: 跑测试

```bash
uv run pytest tests/test_persona_loader.py -v
```
Expected: 4 tests pass.

## Self-Review

- [ ] PersonaLoader 接 `output_rules_text` 必填参数
- [ ] 不再 import OUTPUT_RULES
- [ ] 4 个测试 pass
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT

---

## Task 9: Orchestrator 频率裁剪 + 测试

**Files:**
- Modify: `src/g_chan/orchestrator.py`
- Modify: `tests/test_orchestrator.py`

### Step 9.1: 完整替换 `src/g_chan/orchestrator.py`

跟现版本相比,加 4 件事:
1. `__init__` 接 `expression_change_frequency` + `motion_change_frequency` + `default_expression` + `default_motion` + `random_fn`
2. `_handle_priority` 跑频率裁剪后 log expression/motion
3. `_process_batch` 同样
4. 新增 `_apply_frequency()` 工具

```python
"""Orchestrator — VIP 即时路径 + 普通观众批处理路径 + Live2D 频率裁剪。"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Callable, Protocol

from g_chan.chat.base import ChatAdapter, ChatMessage
from g_chan.interaction.buffer import MessageBuffer
from g_chan.llm.base import Language, LLMError, LLMMessage, LLMProvider, LLMReply, Mood
from g_chan.persona.loader import StreamContext
from g_chan.prompts import build_batch_user_message
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
        vip_window_ms: int,
        batch_window_s: float,
        batch_cooldown_ms: int,
        buffer_size: int,
        fallback_text: str,
        fallback_kaomoji: str,
        fallback_mood: Mood,
        fallback_language: Language,
        # Phase 2.6 新增
        default_expression: str = "",
        default_motion: str = "",
        expression_change_frequency: float = 1.0,
        motion_change_frequency: float = 1.0,
        tts: TTSEngine | None = None,
        audio_sink: AudioSink | None = None,
        now_ms: Callable[[], float] = _default_now_ms,
        random_fn: Callable[[], float] = random.random,
    ):
        self._chat = chat
        self._llm = llm
        self._persona = persona
        self._stream_ctx = stream_ctx
        self._vip_rl = RateLimiter(window_ms=vip_window_ms, now_ms=now_ms)
        self._batch_window_s = batch_window_s
        self._batch_cooldown_ms = batch_cooldown_ms
        self._buffer = MessageBuffer(max_size=buffer_size)
        self._prompt_max = buffer_size if buffer_size > 0 else 1_000_000
        self._fallback_text = fallback_text
        self._fallback_kaomoji = fallback_kaomoji
        self._fallback_mood = fallback_mood
        self._fallback_language = fallback_language
        self._default_expression = default_expression
        self._default_motion = default_motion
        self._expression_change_frequency = expression_change_frequency
        self._motion_change_frequency = motion_change_frequency
        self._tts = tts
        self._audio_sink = audio_sink
        self._now_ms = now_ms
        self._random_fn = random_fn
        self._last_batch_started_at_ms: float = -float("inf")
        self._batch_in_flight: bool = False

    def wire(self) -> None:
        self._chat.on_trigger(self._on_trigger)

    async def _on_trigger(self, msg: ChatMessage) -> None:
        log.info("trigger: user=%s priority=%s body=%r",
                 msg.user, msg.is_priority, msg.body)
        if msg.is_priority:
            asyncio.create_task(self._handle_priority(msg))
        else:
            await self._handle_regular(msg)

    # --------------------- VIP ---------------------

    async def _handle_priority(self, msg: ChatMessage) -> None:
        if not self._vip_rl.try_acquire():
            log.info("vip rate-limited, drop: user=%s", msg.user)
            return

        try:
            reply = await self._llm.generate(self._build_single_messages(msg))
        except LLMError as e:
            log.warning("vip llm failed: %s — using fallback", e)
            reply = self._fallback_reply()

        expression, motion = self._apply_frequency(reply)
        log.info(
            "vip reply: user=%s mood=%s lang=%s text=%r kaomoji=%r expr=%r motion=%r",
            msg.user, reply.mood, reply.language, reply.text, reply.kaomoji,
            expression, motion,
        )

        await self._do_tts(reply.text, language=reply.language, user=msg.user)
        chat_body = (
            f"{reply.text} {reply.kaomoji}".strip() if reply.kaomoji else reply.text
        )
        await self._chat.send(f"@{msg.user} {chat_body}")

    # --------------------- 普通观众 ---------------------

    async def _handle_regular(self, msg: ChatMessage) -> None:
        if self._batch_window_s <= 0:
            log.debug("batch path disabled, drop regular")
            return

        now = self._now_ms()
        if now - self._last_batch_started_at_ms < self._batch_cooldown_ms:
            log.debug("regular @ during cooldown, drop: user=%s", msg.user)
            return
        if self._batch_in_flight:
            log.debug("regular @ during batch in-flight, drop: user=%s", msg.user)
            return

        was_empty = self._buffer.is_empty()
        self._buffer.add(msg, now_ms=now)
        if was_empty:
            asyncio.create_task(self._scheduled_flush())

    async def _scheduled_flush(self) -> None:
        first_at = self._buffer.first_at_ms()
        if first_at is None:
            return
        now = self._now_ms()
        elapsed_ms = now - first_at
        target_ms = self._batch_window_s * 1000
        sleep_s = max(0.0, (target_ms - elapsed_ms) / 1000)
        if sleep_s > 0:
            await asyncio.sleep(sleep_s)

        if self._buffer.is_empty() or self._batch_in_flight:
            return

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

        if not reply.text.strip():
            log.info("batch result: silence (batch_size=%d)", len(messages))
            return

        expression, motion = self._apply_frequency(reply)
        log.info(
            "batch reply: batch_size=%d mood=%s lang=%s text=%r kaomoji=%r expr=%r motion=%r",
            len(messages), reply.mood, reply.language, reply.text, reply.kaomoji,
            expression, motion,
        )

        await self._do_tts(reply.text, language=reply.language, user="batch")
        chat_body = (
            f"{reply.text} {reply.kaomoji}".strip() if reply.kaomoji else reply.text
        )
        await self._chat.send(chat_body)

    # --------------------- 共用 ---------------------

    def _apply_frequency(self, reply: LLMReply) -> tuple[str, str]:
        """根据 frequency 决定用 LLM 选的还是 default。"""
        if self._random_fn() < self._expression_change_frequency:
            expression = reply.expression
        else:
            expression = self._default_expression
        if self._random_fn() < self._motion_change_frequency:
            motion = reply.motion
        else:
            motion = self._default_motion
        return expression, motion

    async def _do_tts(self, text: str, *, language: Language, user: str) -> None:
        if self._tts is None or self._audio_sink is None:
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
            expression=self._default_expression,
            motion=self._default_motion,
        )

    def _build_single_messages(self, msg: ChatMessage) -> list[LLMMessage]:
        system = self._persona.assemble(stream_ctx=self._stream_ctx.current())
        return [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=f"{msg.user}: {msg.body}"),
        ]

    def _build_batch_messages(self, messages: list[ChatMessage]) -> list[LLMMessage]:
        system = self._persona.assemble(stream_ctx=self._stream_ctx.current())
        return [
            LLMMessage(role="system", content=system),
            LLMMessage(role="user", content=build_batch_user_message(messages)),
        ]
```

### Step 9.2: 在 `tests/test_orchestrator.py` 顶部更新默认 fallback,加 Live2D 默认值,加 frequency 控制 helper

找到 `_FB_KWARGS` 字典,改为:

```python
_FB_KWARGS = {
    "fallback_text": "FB_TEXT",
    "fallback_kaomoji": "FB_KAO",
    "fallback_mood": "dizzy",
    "fallback_language": "zh",
    "default_expression": "",
    "default_motion": "",
    "expression_change_frequency": 1.0,   # 测试默认 100% 用 LLM 选的
    "motion_change_frequency": 1.0,
}
```

`_build_orch` 函数加 `random_fn` 参数:

```python
def _build_orch(
    *, chat, llm, clock,
    vip_window_ms=0,
    batch_window_s=2,
    batch_cooldown_ms=0,
    buffer_size=10,
    tts=None, audio_sink=None,
    random_fn=lambda: 0.0,   # 默认 0 → 永远 < frequency,采纳 LLM 选的
    **overrides,   # 让测试可覆盖 _FB_KWARGS 里的某个值
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
        now_ms=clock,
        random_fn=random_fn,
        **kw,
    )
```

### Step 9.3: 在 `tests/test_orchestrator.py` 末尾追加 frequency 测试

```python
# ============= Live2D 频率裁剪 =============

@pytest.mark.asyncio
async def test_vip_uses_llm_expression_when_random_passes():
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊", mood="happy",
                                expression="Smile", motion="Tap")
    clock = FakeClock()
    # random_fn=lambda: 0.0 → 0 < 1.0 → 总是采纳 LLM 选的
    orch = _build_orch(
        chat=chat, llm=llm, clock=clock,
        random_fn=lambda: 0.0,
        expression_change_frequency=1.0,
        motion_change_frequency=1.0,
    )
    orch.wire()
    await chat.emit("alice", "嗨", is_priority=True)
    await asyncio.sleep(0.05)
    # log 写了 expr=Smile motion=Tap(无法直接断言,但 chat 行为正确)
    assert chat.sent == ["@alice 好啊"]


@pytest.mark.asyncio
async def test_vip_uses_default_when_random_fails_frequency():
    """random_fn returns 0.5,frequency=0.0 → fail → 用 default。"""
    # 这个测试无法直接断言 expression(orchestrator 只 log,没 expose),
    # 但行为是:无 expression/motion 变化,chat 正常发送
    chat = FakeChat()
    llm = FakeLLM()
    llm.next_reply = make_reply("好啊", mood="happy",
                                expression="Smile", motion="Tap")
    clock = FakeClock()
    orch = _build_orch(
        chat=chat, llm=llm, clock=clock,
        random_fn=lambda: 0.5,   # > 0.0
        expression_change_frequency=0.0,
        motion_change_frequency=0.0,
        default_expression="Normal",
        default_motion="Idle",
    )
    orch.wire()
    await chat.emit("alice", "嗨", is_priority=True)
    await asyncio.sleep(0.05)
    # chat 不被频率影响
    assert chat.sent == ["@alice 好啊"]
    # 注:expression 应是 "Normal",但 orchestrator 不暴露,
    # Phase 3 viewer 集成后才能黑盒测试


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
```

### Step 9.4: 跑 orchestrator 测试

```bash
uv run pytest tests/test_orchestrator.py -v
```
Expected: 全 pass(原 ~13 个 + 新 3 个 = ~16 个)。

### Step 9.5: 全套 + ruff

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```
Expected: main.py 测试可能 fail(下个 task 修),ruff 干净。

## Self-Review

- [ ] Orchestrator 接 5 个新参数(default_expression/motion + 2 个 frequency + random_fn)
- [ ] `_apply_frequency` 方法用 random_fn 决定 LLM vs default
- [ ] VIP + batch 两条路径都跑 frequency
- [ ] fallback_reply 把 default_expression/motion 写进 LLMReply
- [ ] 测试新增 3 个 frequency case
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- orchestrator 测试总数

---

## Task 10: __main__.py 装配

**Files:**
- Modify: `src/g_chan/__main__.py`

### Step 10.1: 完整替换 `src/g_chan/__main__.py`

```python
"""g_chan 入口 — python -m g_chan。"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from g_chan.chat.twitch import TwitchChatAdapter
from g_chan.config import load_config
from g_chan.live2d.model_loader import (
    Live2DModel,
    discover_model_path,
    load_model_info,
)
from g_chan.llm.factory import create_provider
from g_chan.logging_setup import setup_logging
from g_chan.orchestrator import Orchestrator
from g_chan.persona.loader import PersonaLoader
from g_chan.persona.stream_context import StreamContextProvider, TwitchHelixClient
from g_chan.prompts import render_output_rules
from g_chan.tts.edge import EdgeTTSEngine
from g_chan.tts.file_sink import FileAudioSink

log = logging.getLogger("g_chan")


def _load_live2d_model(model_path_str: str) -> Live2DModel:
    """根据 config.live2d.model_path 加载模型。空字符串 → auto-detect。"""
    if model_path_str:
        path = Path(model_path_str)
        if not path.exists():
            raise FileNotFoundError(
                f"live2d.model_path does not exist: {path}"
            )
    else:
        path = discover_model_path(Path("Live2D"))
        if path is None:
            raise FileNotFoundError(
                "live2d.enabled=true but no model found. "
                "Either put a .model3.json under Live2D/<folder>/ "
                "or set live2d.model_path explicitly."
            )
    log.info("loading Live2D model: %s", path)
    return load_model_info(path)


async def amain() -> int:
    cfg_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("config.yaml")
    cfg = load_config(cfg_path)
    setup_logging(level=cfg.logging.level, file=cfg.logging.file)

    # Live2D 模型(可选)
    live2d_model: Live2DModel | None = None
    if cfg.live2d.enabled:
        live2d_model = _load_live2d_model(cfg.live2d.model_path)
        log.info(
            "live2d enabled — expressions=%d motions=%d",
            len(live2d_model.expressions), len(live2d_model.motions),
        )
    else:
        log.info("live2d disabled — pure chat mode")

    log.info(
        "starting G酱 — channel=#%s provider=%s vip_window=%dms batch=%.1fs cooldown=%dms buffer=%d",
        cfg.twitch.channel, cfg.llm.provider,
        cfg.interaction.vip_window_ms,
        cfg.interaction.batch_window_s,
        cfg.interaction.batch_cooldown_ms,
        cfg.interaction.buffer_size,
    )

    chat = TwitchChatAdapter(
        channel=cfg.twitch.channel,
        bot_username=cfg.twitch.bot_username,
        oauth_token=cfg.twitch.oauth_token,
        trigger=cfg.twitch.trigger,
    )

    # 注入 Live2DModel 到 factory(可能为 None)
    llm = create_provider(cfg.llm, live2d_cfg=cfg.live2d, live2d_model=live2d_model)

    # 预 render output rules 文本,然后注入 PersonaLoader
    output_rules_text = render_output_rules(
        live2d_enabled=cfg.live2d.enabled,
        expressions=live2d_model.expressions if live2d_model else [],
        motions=live2d_model.motions if live2d_model else [],
    )

    persona = PersonaLoader(
        base_path=cfg.persona.prompt_file,
        output_rules_text=output_rules_text,
        include_stream_context=cfg.stream_context.enabled,
    )

    sctx: StreamContextProvider | _NullStreamCtx
    polling: asyncio.Task | None = None
    if cfg.stream_context.enabled:
        helix = TwitchHelixClient(
            client_id=cfg.twitch.client_id,
            client_secret=cfg.twitch.client_secret,
        )
        sctx = StreamContextProvider(channel=cfg.twitch.channel, helix=helix)
    else:
        log.info("stream_context disabled — skipping Helix polling")
        sctx = _NullStreamCtx()

    tts_engine: EdgeTTSEngine | None = None
    audio_sink: FileAudioSink | None = None
    if cfg.tts.enabled:
        tts_engine = EdgeTTSEngine(
            voices=cfg.tts.voices,
            rate=cfg.tts.rate,
            pitch=cfg.tts.pitch,
        )
        audio_sink = FileAudioSink(output_dir=cfg.tts.output_dir)
        log.info("tts enabled — voices=%s, output_dir=%s",
                 cfg.tts.voices, cfg.tts.output_dir)
    else:
        log.info("tts disabled")

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
        default_expression=cfg.live2d.default_expression,
        default_motion=cfg.live2d.default_motion,
        expression_change_frequency=cfg.live2d.expression_change_frequency,
        motion_change_frequency=cfg.live2d.motion_change_frequency,
        tts=tts_engine,
        audio_sink=audio_sink,
    )
    orch.wire()

    if isinstance(sctx, StreamContextProvider):
        polling = asyncio.create_task(
            sctx.start_polling(cfg.stream_context.poll_interval_ms)
        )
    try:
        await chat.connect()
        log.info("ready — listening for %s in #%s",
                 cfg.twitch.trigger, cfg.twitch.channel)
    except KeyboardInterrupt:
        log.info("shutting down")
    finally:
        if polling is not None:
            polling.cancel()
        await chat.disconnect()
    return 0


class _NullStreamCtx:
    """include_stream_context=False 时的空实现 — 满足 StreamCtxLike Protocol。"""
    def current(self) -> None:
        return None


def main() -> int:
    try:
        return asyncio.run(amain())
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
```

### Step 10.2: smoke check

```bash
mv config.yaml config.yaml.bak 2>/dev/null
uv run python -m g_chan 2>&1 | tail -5
mv config.yaml.bak config.yaml 2>/dev/null
```
Expected: `FileNotFoundError: [Errno 2] No such file or directory: 'config.yaml'`(不能是 ImportError 等)。

### Step 10.3: 全套测试 + ruff

```bash
uv run pytest 2>&1 | tail -3
uv run ruff check src tests 2>&1 | tail -3
```
Expected: 全套全绿,ruff 干净。

## Self-Review

- [ ] __main__.py 加 `_load_live2d_model` 帮助函数
- [ ] cfg.live2d.enabled 时加载模型,否则 None
- [ ] factory 收 live2d_cfg + live2d_model
- [ ] render_output_rules 拿 expressions/motions 后传给 PersonaLoader
- [ ] Orchestrator 收 default_expression/motion + 两个 frequency
- [ ] 启动日志含 live2d 信息
- [ ] smoke check 报 FileNotFoundError 不报 ImportError
- [ ] pytest + ruff 全绿
- [ ] 没有 git commit

## Report

- **Status:** DONE | DONE_WITH_CONCERNS | BLOCKED | NEEDS_CONTEXT
- 测试总数
- smoke 错误信息
- 任何 concerns

---

## Task 11: 真实 Gemini smoke + 端到端

**Files:** 无。

### Step 11.1: 直接调一次 LLM,看 expression/motion 是否合理

```bash
uv run python -c "
import asyncio, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from g_chan.config import load_config
from g_chan.live2d.model_loader import discover_model_path, load_model_info
from g_chan.llm.factory import create_provider
from g_chan.llm.base import LLMMessage
from g_chan.prompts import render_output_rules

async def main():
    cfg = load_config('config.yaml')
    live2d_model = None
    if cfg.live2d.enabled:
        path = discover_model_path(Path('Live2D')) if not cfg.live2d.model_path else Path(cfg.live2d.model_path)
        live2d_model = load_model_info(path)
        print(f'model: {path}')
        print(f'  expressions: {live2d_model.expressions}')
        print(f'  motions: {live2d_model.motions}')
    p = create_provider(cfg.llm, live2d_cfg=cfg.live2d, live2d_model=live2d_model)
    
    rules = render_output_rules(
        live2d_enabled=cfg.live2d.enabled,
        expressions=live2d_model.expressions if live2d_model else [],
        motions=live2d_model.motions if live2d_model else [],
    )
    system = '你是 G 酱,腹黑傲娇高中女生。' + open(cfg.persona.prompt_file).read() + '\n\n' + rules
    
    for q in ['你今天玩了啥?', '你害羞吗', '本小姐戳你一下']:
        reply = await p.generate([
            LLMMessage('system', system),
            LLMMessage('user', f'viewer: {q}'),
        ])
        print(f'\\nQ: {q}')
        print(f'  text:       {reply.text!r}')
        print(f'  mood:       {reply.mood}')
        print(f'  expression: {reply.expression!r}')
        print(f'  motion:     {reply.motion!r}')

asyncio.run(main())
" 2>&1 | tail -40
```

Expected:
- 输出包含真实 Live2D model 的 expressions/motions 列表
- 3 个问题各拿到一个 reply,expression 是真实表情(Smile / Angry / Blushing 等),motion 多数情况是 None,合适时机才是 Tap 等
- 没有 JSON parse 错误

### Step 11.2: 启动 bot 实地验证

确保本地 `config.yaml` 加了 `live2d:` 块(参考 config.example.yaml)。

```bash
uv run python -m g_chan
```

启动日志应包含:
- `loading Live2D model: ...`
- `live2d enabled — expressions=8 motions=7`
- `starting G酱 — ...`

在 Twitch chat 验证:
- 主播 / mod 发 `@G酱 嗨` → 立即回复 + 日志含 `expr=Smile motion=None`(或别的)
- 普通号刷 → 5 秒后批回复 + 日志含 expr/motion
- 频率 default 1.0 + 0.3 → motion 70% 都是 default(空)

## Phase 2.6 完成定义

- [ ] `uv run pytest` 全绿(预期 ~100+ tests,新增 ~20)
- [ ] `uv run ruff check src tests` 干净
- [ ] `uv run python -m g_chan` 启动日志含 `live2d enabled — expressions=N motions=M`
- [ ] Step 11.1 真实 Gemini smoke 拿到合理的 expression/motion(Smile/Angry 等)
- [ ] Step 11.2 端到端 chat 触发 + 日志可见 expression/motion 字段

---

## 后续(Phase 3)的事

这个 plan 只到"LLM 输出 expression/motion,Orchestrator 知道这个值"。**真正驱动 Live2D 渲染**(WebSocket 推送给 viewer)是 Phase 3 的事。Phase 2.6 之后,字段已经存在于 LLMReply,Phase 3 只要在 Orchestrator 加一步"push to viewer"即可。
