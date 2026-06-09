from pathlib import Path

import pytest
from pydantic import ValidationError

from g_chan.config import AppConfig, load_config


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
    assert isinstance(cfg, AppConfig)
    assert cfg.twitch.channel == "alice"
    assert cfg.twitch.oauth_token == "oauth:abc"
    assert cfg.llm.api_key == "gkey"
    assert cfg.interaction.vip_window_ms == 2000


def test_missing_env_var_fails(tmp_path, monkeypatch):
    # 阻止 load_dotenv() 从项目根目录的真 .env 回填环境变量
    monkeypatch.setattr("g_chan.config.load_dotenv", lambda: None)
    # 显式删掉这些 env,模拟"没设过"的场景
    for k in ("TWITCH_OAUTH", "TWITCH_CLIENT_ID", "TWITCH_CLIENT_SECRET", "GEMINI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
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
    with pytest.raises(RuntimeError, match="missing environment variable"):
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
llm:
  provider: "lolwut"
  model: "x"
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
    with pytest.raises(ValueError, match="unknown llm.provider"):
        load_config(cfg_path)


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
tts:
  enabled: true
  voices:
    zh: "zh-CN-XiaoyiNeural"
    en: "en-US-AvaNeural"
    ja: "ja-JP-NanamiNeural"
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
    assert cfg.tts.voices["zh"] == "zh-CN-XiaoyiNeural"
    assert cfg.tts.voices["en"] == "en-US-AvaNeural"
    assert cfg.tts.voices["ja"] == "ja-JP-NanamiNeural"
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
    assert cfg.tts.enabled is True
    assert cfg.tts.voices["zh"] == "zh-CN-XiaoyiNeural"
    assert cfg.tts.voices["en"] == "en-US-AvaNeural"
    assert cfg.tts.voices["ja"] == "ja-JP-NanamiNeural"
    assert cfg.tts.output_dir == "out"


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
    # 未在 YAML 设置 → 默认 1000ms 自动回到 default_expression
    assert cfg.live2d.expression_revert_ms == 1000


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
    with pytest.raises(ValidationError):
        load_config(cfg_path)


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
