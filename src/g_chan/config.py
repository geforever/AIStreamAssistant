"""配置加载:YAML + .env,pydantic 校验。"""
from __future__ import annotations

import os
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


class TTSConfig(BaseModel):
    enabled: bool = True
    voice: str = "zh-CN-XiaoyiNeural"
    rate: str = "+0%"
    pitch: str = "+0Hz"
    output_dir: str = "out"
    timeout_s: float = 10.0


class LoggingConfig(BaseModel):
    level: Literal["debug", "info", "warning", "error"] = "info"
    file: str = "logs/g-chan.log"


class AppConfig(BaseModel):
    twitch: TwitchConfig
    rate_limit: RateLimitConfig
    llm: LLMConfig
    persona: PersonaConfig
    stream_context: StreamContextConfig
    tts: TTSConfig = Field(default_factory=TTSConfig)
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
