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
