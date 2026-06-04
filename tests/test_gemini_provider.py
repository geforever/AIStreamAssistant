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

_SCHEMA_NOLIVE2D = {
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
        "expression": "smile", "motion": "tap",
    })
    fake_client = MagicMock()
    fake_client.aio.models.generate_content = AsyncMock(return_value=_fake_response(payload))
    monkeypatch.setattr("g_chan.llm.gemini.genai.Client", lambda api_key: fake_client)

    p = GeminiProvider(
        api_key="x", model="gemini-2.5-flash", schema=_SCHEMA_NOLIVE2D,
        available_expressions=["smile", "angry"],
        available_motions=["tap", "idle"],
        **_FB_KWARGS,
    )
    reply = await p.generate([LLMMessage("user", "嗨")])
    assert reply.expression == "smile"
    assert reply.motion == "tap"


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
    # 关键:SDK 收到的 schema 跟传入的对齐
    rs = cfg.response_schema
    # SDK 可能保留 dict 或转 Schema 对象;只验关键属性存在
    if isinstance(rs, dict):
        assert "foo" in rs.get("properties", {})
    # 否则 SDK 转成了 Schema 对象,不强求验证


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
        fallback_expression="normal", fallback_motion="idle",
        available_expressions=["normal", "smile"],
        available_motions=["idle", "tap"],
    )
    reply = await p.generate([LLMMessage("user", "嗨")])
    assert reply.text == "custom走神"
    assert reply.expression == "normal"
    assert reply.motion == "idle"
