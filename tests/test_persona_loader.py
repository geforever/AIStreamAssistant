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
