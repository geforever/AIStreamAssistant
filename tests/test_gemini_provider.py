import asyncio
import json
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
async def test_generate_parses_json_reply(monkeypatch):
    payload = json.dumps(
        {"text": "好啊~", "kaomoji": "(=ω=)", "mood": "happy"},
        ensure_ascii=False,
    )
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(
        return_value=_fake_response(payload)
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
    assert reply.kaomoji == "(=ω=)"
    assert reply.mood == "happy"
    assert reply.tokens_in == 10
    assert reply.tokens_out == 20
    assert reply.latency_ms >= 0


@pytest.mark.asyncio
async def test_generate_uses_json_mode_and_schema(monkeypatch):
    """验证调用 SDK 时传了 responseMimeType=application/json + responseSchema。"""
    captured = {}

    async def fake_generate(model, contents, config):
        captured["config"] = config
        return _fake_response(json.dumps({"text": "x", "mood": "happy"}))

    fake_client = MagicMock()
    fake_client.aio.models.generate_content = fake_generate
    monkeypatch.setattr(
        "g_chan.llm.gemini.genai.Client",
        lambda api_key: fake_client,
    )

    p = GeminiProvider(api_key="x", model="gemini-2.5-flash")
    await p.generate([LLMMessage("user", "嗨")])

    cfg = captured["config"]
    assert cfg.response_mime_type == "application/json"
    schema = cfg.response_schema
    # schema 在 SDK 内部可能是 dict 或 Schema 对象 — 兼容两种
    if isinstance(schema, dict):
        assert schema["type"] == "object"
        props = schema["properties"]
        assert "text" in props and "kaomoji" in props and "mood" in props
        assert set(props["mood"]["enum"]) == {
            "happy", "angry", "sad", "surprised",
            "shy", "thinking", "tsundere", "dizzy",
        }
    else:
        # SDK 转成了 types.Schema
        props = schema.properties
        assert "text" in props and "kaomoji" in props and "mood" in props
        assert set(props["mood"].enum) == {
            "happy", "angry", "sad", "surprised",
            "shy", "thinking", "tsundere", "dizzy",
        }


@pytest.mark.asyncio
async def test_generate_handles_kaomoji_omission(monkeypatch):
    """JSON 里没 kaomoji 字段 — 应该解析为空字符串,不崩。"""
    payload = json.dumps({"text": "好啊", "mood": "happy"}, ensure_ascii=False)
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(
        return_value=_fake_response(payload)
    )
    monkeypatch.setattr(
        "g_chan.llm.gemini.genai.Client",
        lambda api_key: fake_client,
    )

    p = GeminiProvider(api_key="x", model="gemini-2.5-flash")
    reply = await p.generate([LLMMessage("user", "嗨")])
    assert reply.text == "好啊"
    assert reply.kaomoji == ""
    assert reply.mood == "happy"


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
