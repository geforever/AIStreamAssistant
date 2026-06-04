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
    return Live2DConfig(enabled=True, default_expression="normal", default_motion="idle")


def _model():
    return Live2DModel(
        path=Path("/fake/model.model3.json"),
        expressions=["smile", "angry", "normal"],
        motions=["idle", "tap"],
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


def test_creates_gemini_without_model_uses_empty_enums():
    """live2d_model=None → schema 的 expression/motion enum 只含 'None'。"""
    with patch("g_chan.llm.gemini.genai.Client"):
        cfg = LLMConfig(provider="gemini", model="gemini-2.5-flash", api_key="x")
        p = create_provider(cfg, live2d_cfg=_live2d_enabled(), live2d_model=None)
        assert isinstance(p, GeminiProvider)
        # provider 内部存了 schema,检查 expression enum
        assert p._schema["properties"]["expression"]["enum"] == ["none"]
        assert p._schema["properties"]["motion"]["enum"] == ["none"]


@pytest.mark.parametrize("provider", ["claude", "openai", "qwen"])
def test_other_providers_not_implemented_yet(provider):
    cfg = LLMConfig(provider=provider, model="x", api_key="x")
    with pytest.raises(NotImplementedError, match=provider):
        create_provider(cfg, live2d_cfg=_live2d_disabled())
