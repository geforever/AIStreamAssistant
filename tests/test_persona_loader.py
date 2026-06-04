from pathlib import Path

from g_chan.persona.loader import PersonaLoader, StreamContext
from g_chan.prompts import OUTPUT_RULES


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_assembles_base_with_output_rules(tmp_path):
    """assembled prompt 含用户人设 + 程序 OUTPUT_RULES。"""
    base = write(tmp_path / "base.md", "你是 G 酱。")
    loader = PersonaLoader(base_path=base)
    out = loader.assemble(stream_ctx=None)
    assert "你是 G 酱。" in out
    # OUTPUT_RULES 是程序注入的,应包含特征字符串
    assert "输出格式" in out
    assert "mood" in out
    assert "language" in out
    # 不含直播上下文
    assert "[当前直播上下文]" not in out


def test_includes_stream_context_when_provided(tmp_path):
    base = write(tmp_path / "base.md", "你是 G 酱。")
    loader = PersonaLoader(base_path=base)
    ctx = StreamContext(title="深夜原神", game_name="Genshin Impact")
    out = loader.assemble(stream_ctx=ctx)
    assert "深夜原神" in out
    assert "Genshin Impact" in out
    assert "[当前直播上下文]" in out
    # OUTPUT_RULES 仍在
    assert "输出格式" in out


def test_omits_context_section_when_disabled(tmp_path):
    base = write(tmp_path / "base.md", "你是 G 酱。")
    loader = PersonaLoader(base_path=base, include_stream_context=False)
    ctx = StreamContext(title="任何", game_name="任何")
    out = loader.assemble(stream_ctx=ctx)
    assert "[当前直播上下文]" not in out
    # OUTPUT_RULES 仍在
    assert "输出格式" in out


def test_output_rules_constant_is_non_empty():
    """sanity check: OUTPUT_RULES 不能是空字符串。"""
    assert len(OUTPUT_RULES) > 100
    assert "json" in OUTPUT_RULES.lower()
