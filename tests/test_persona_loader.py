from pathlib import Path

from g_chan.persona.loader import PersonaLoader, StreamContext


def write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def test_assembles_base_only(tmp_path):
    base = write(tmp_path / "base.md", "你是 G 酱。")
    fmt  = write(tmp_path / "fmt.md", "输出规则:xxx")
    loader = PersonaLoader(base_path=base, output_format_path=fmt)
    out = loader.assemble(stream_ctx=None)
    assert "你是 G 酱。" in out
    assert "输出规则:xxx" in out
    assert "[当前直播上下文]" not in out


def test_includes_stream_context_when_provided(tmp_path):
    base = write(tmp_path / "base.md", "你是 G 酱。")
    fmt  = write(tmp_path / "fmt.md", "输出规则:xxx")
    loader = PersonaLoader(base_path=base, output_format_path=fmt)
    ctx = StreamContext(title="深夜原神", game_name="Genshin Impact")
    out = loader.assemble(stream_ctx=ctx)
    assert "深夜原神" in out
    assert "Genshin Impact" in out
    assert "[当前直播上下文]" in out


def test_omits_context_section_when_disabled(tmp_path):
    base = write(tmp_path / "base.md", "你是 G 酱。")
    fmt  = write(tmp_path / "fmt.md", "输出规则:xxx")
    loader = PersonaLoader(
        base_path=base, output_format_path=fmt, include_stream_context=False
    )
    ctx = StreamContext(title="任何", game_name="任何")
    out = loader.assemble(stream_ctx=ctx)
    assert "[当前直播上下文]" not in out
