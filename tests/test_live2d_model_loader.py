import json

import pytest

from g_chan.live2d.model_loader import (
    Live2DModel,
    discover_model_path,
    load_model_info,
)


def _write_model_file(dir, name="m.model3.json", expressions=None, motions=None):
    """Write a minimal .model3.json with optional Expressions/Motions."""
    refs = {"Moc": "x.moc3", "Textures": []}
    if expressions is not None:
        refs["Expressions"] = expressions
    if motions is not None:
        refs["Motions"] = motions
    payload = {"Version": 3, "FileReferences": refs}
    path = dir / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_model_info_parses_expressions_and_motions(tmp_path):
    p = _write_model_file(
        tmp_path,
        expressions=[
            {"Name": "Smile", "File": "expressions/Smile.exp3.json"},
            {"Name": "Angry", "File": "expressions/Angry.exp3.json"},
            {"Name": "f01", "File": "expressions/f01.exp3.json"},
        ],
        motions={
            "Idle": [{"File": "motion/idle.motion3.json"}],
            "Tap":  [{"File": "motion/tap.motion3.json"}],
        },
    )
    info = load_model_info(p)
    assert isinstance(info, Live2DModel)
    assert info.path == p
    assert info.expressions == ["Smile", "Angry", "f01"]
    assert sorted(info.motions) == ["Idle", "Tap"]


def test_load_model_info_handles_missing_expressions_section(tmp_path):
    p = _write_model_file(tmp_path, expressions=None, motions={"Idle": []})
    info = load_model_info(p)
    assert info.expressions == []
    assert info.motions == ["Idle"]


def test_load_model_info_handles_missing_motions_section(tmp_path):
    p = _write_model_file(tmp_path, expressions=[{"Name": "X", "File": "x"}])
    info = load_model_info(p)
    assert info.expressions == ["X"]
    assert info.motions == []


def test_load_model_info_raises_on_invalid_json(tmp_path):
    bad = tmp_path / "bad.model3.json"
    bad.write_text("not json {", encoding="utf-8")
    with pytest.raises(ValueError):
        load_model_info(bad)


def test_load_model_info_raises_on_missing_file_references(tmp_path):
    bad = tmp_path / "bad.model3.json"
    bad.write_text(json.dumps({"Version": 3}), encoding="utf-8")
    with pytest.raises(ValueError):
        load_model_info(bad)


def test_discover_model_path_finds_first_subfolder_first_match(tmp_path):
    """在 Live2D/<first_sorted>/...深度找第一个 .model3.json。"""
    folder_a = tmp_path / "AAA_first" / "runtime"
    folder_a.mkdir(parents=True)
    target = folder_a / "a.model3.json"
    target.write_text("{}", encoding="utf-8")

    folder_b = tmp_path / "BBB_second" / "runtime"
    folder_b.mkdir(parents=True)
    (folder_b / "b.model3.json").write_text("{}", encoding="utf-8")

    found = discover_model_path(tmp_path)
    assert found == target


def test_discover_model_path_skips_hidden_folders(tmp_path):
    """跳过 .DS_Store / __MACOSX 之类的隐藏 / 系统目录。"""
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "hidden.model3.json").write_text("{}", encoding="utf-8")

    visible = tmp_path / "visible"
    visible.mkdir()
    target = visible / "ok.model3.json"
    target.write_text("{}", encoding="utf-8")

    found = discover_model_path(tmp_path)
    assert found == target


def test_discover_model_path_returns_none_when_no_match(tmp_path):
    (tmp_path / "empty").mkdir()
    assert discover_model_path(tmp_path) is None


def test_discover_model_path_returns_none_when_live2d_dir_missing(tmp_path):
    missing = tmp_path / "doesnt_exist"
    assert discover_model_path(missing) is None
