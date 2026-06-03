from unittest.mock import patch

import pytest

from g_chan.config import LLMConfig
from g_chan.llm.factory import create_provider
from g_chan.llm.gemini import GeminiProvider


def test_creates_gemini():
    with patch("g_chan.llm.gemini.genai.Client"):
        cfg = LLMConfig(provider="gemini", model="gemini-2.5-flash", api_key="x")
        p = create_provider(cfg)
        assert isinstance(p, GeminiProvider)


@pytest.mark.parametrize("provider", ["claude", "openai", "qwen"])
def test_other_providers_not_implemented_yet(provider):
    cfg = LLMConfig(provider=provider, model="x", api_key="x")
    with pytest.raises(NotImplementedError, match=provider):
        create_provider(cfg)
