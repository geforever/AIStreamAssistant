"""配置加载:YAML + .env,pydantic 校验。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from g_chan.llm.base import Language, Mood

LLMProviderName = Literal["gemini", "claude", "openai", "qwen"]


class TwitchConfig(BaseModel):
    channel: str
    bot_username: str
    trigger: str = "@G酱"
    oauth_token: str = Field(default="", description="from $TWITCH_OAUTH")
    client_id: str = Field(default="", description="from $TWITCH_CLIENT_ID")
    client_secret: str = Field(default="", description="from $TWITCH_CLIENT_SECRET")


class LLMFallbackConfig(BaseModel):
    """LLM 返回不合法 JSON / 空 text / 缺字段时使用的回退四元组。"""
    text: str = "诶?本小姐刚才走神了,你再说一遍嘛"
    kaomoji: str = "(=ω=)"
    mood: Mood = "dizzy"
    language: Language = "zh"


class LLMConfig(BaseModel):
    provider: LLMProviderName
    model: str
    temperature: float = 0.9
    max_tokens: int = 300
    timeout_s: float = 10.0
    api_key: str = Field(default="", description="from $<PROVIDER>_API_KEY")
    fallback: LLMFallbackConfig = Field(default_factory=LLMFallbackConfig)


class PersonaConfig(BaseModel):
    prompt_file: str = "prompts/default.md"
    include_stream_context: bool = True


class StreamContextConfig(BaseModel):
    poll_interval_ms: int = 30000


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


def _default_voices() -> dict[Language, str]:
    return {
        "zh": "zh-CN-XiaoyiNeural",
        "en": "en-US-AvaNeural",
        "ja": "ja-JP-NanamiNeural",
    }


class TTSConfig(BaseModel):
    enabled: bool = True
    voices: dict[Language, str] = Field(default_factory=_default_voices)
    rate: str = "+0%"
    pitch: str = "+0Hz"
    output_dir: str = "out"
    timeout_s: float = 10.0


class LoggingConfig(BaseModel):
    level: Literal["debug", "info", "warning", "error"] = "info"
    file: str = "logs/g-chan.log"


class AppConfig(BaseModel):
    twitch: TwitchConfig
    llm: LLMConfig
    persona: PersonaConfig
    stream_context: StreamContextConfig
    tts: TTSConfig = Field(default_factory=TTSConfig)
    interaction: InteractionConfig = Field(default_factory=InteractionConfig)
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
