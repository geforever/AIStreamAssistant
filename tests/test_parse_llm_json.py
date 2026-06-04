import json

import pytest

from g_chan.llm.base import parse_llm_json

FB_TEXT = "FB_TEXT"
FB_KAOMOJI = "FB_KAOMOJI"
FB_MOOD = "dizzy"
FB_LANG = "zh"
FB_EXP = ""    # 默认不指定 fallback expression
FB_MOT = ""


def _parse(raw, *, available_expressions=None, available_motions=None,
           fallback_expression=FB_EXP, fallback_motion=FB_MOT):
    return parse_llm_json(
        raw,
        fallback_text=FB_TEXT,
        fallback_kaomoji=FB_KAOMOJI,
        fallback_mood=FB_MOOD,
        fallback_language=FB_LANG,
        fallback_expression=fallback_expression,
        fallback_motion=fallback_motion,
        available_expressions=available_expressions,
        available_motions=available_motions,
    )


def _dump(**kw):
    return json.dumps(kw, ensure_ascii=False)


# === 基础字段(text/kaomoji/mood/language)===

def test_full_payload_without_live2d():
    raw = _dump(text="哼,本小姐才没有", kaomoji="(›´ω`‹)", mood="tsundere", language="zh")
    text, kao, mood, lang, expr, mot = _parse(raw)
    assert text == "哼,本小姐才没有"
    assert kao == "(›´ω`‹)"
    assert mood == "tsundere"
    assert lang == "zh"
    assert expr == ""   # Live2D 没启用
    assert mot == ""


def test_empty_kaomoji_allowed():
    raw = _dump(text="好的", kaomoji="", mood="happy", language="zh")
    _, kao, _, _, _, _ = _parse(raw)
    assert kao == ""


def test_missing_kaomoji_field_defaults_empty():
    raw = _dump(text="好的", mood="happy", language="zh")
    _, kao, _, _, _, _ = _parse(raw)
    assert kao == ""


@pytest.mark.parametrize("mood_name", [
    "happy", "angry", "sad", "surprised",
    "shy",   "thinking", "tsundere", "dizzy",
])
def test_all_eight_moods_accepted(mood_name):
    raw = _dump(text="x", mood=mood_name, language="zh")
    _, _, mood, _, _, _ = _parse(raw)
    assert mood == mood_name


def test_unknown_mood_falls_back_to_happy():
    raw = _dump(text="x", mood="lolwut", language="zh")
    _, _, mood, _, _, _ = _parse(raw)
    assert mood == "happy"


@pytest.mark.parametrize("lang", ["zh", "en", "ja"])
def test_all_three_languages_accepted(lang):
    raw = _dump(text="x", mood="happy", language=lang)
    _, _, _, language, _, _ = _parse(raw)
    assert language == lang


def test_unknown_language_falls_back():
    raw = _dump(text="x", mood="happy", language="ko")
    _, _, _, language, _, _ = _parse(raw)
    assert language == FB_LANG


# === expression / motion 行为 ===

def test_live2d_disabled_returns_empty_expression_motion():
    """available_* 为空 → 总返回 "",不管 JSON 里写什么。"""
    raw = _dump(text="x", mood="happy", language="zh",
                expression="smile", motion="tap")
    _, _, _, _, expr, mot = _parse(raw)
    assert expr == ""
    assert mot == ""


def test_live2d_enabled_accepts_valid_expression():
    raw = _dump(text="x", mood="happy", language="zh", expression="smile")
    _, _, _, _, expr, _ = _parse(raw, available_expressions=["smile", "angry"])
    assert expr == "smile"


def test_live2d_enabled_unknown_expression_falls_back_to_default():
    raw = _dump(text="x", mood="happy", language="zh", expression="NotAReal")
    _, _, _, _, expr, _ = _parse(
        raw,
        available_expressions=["smile", "angry", "normal"],
        fallback_expression="normal",
    )
    assert expr == "normal"


def test_live2d_none_string_normalized_to_empty():
    raw = _dump(text="x", mood="happy", language="zh", expression="none")
    _, _, _, _, expr, _ = _parse(raw, available_expressions=["smile"])
    assert expr == ""


def test_live2d_missing_expression_uses_fallback():
    raw = _dump(text="x", mood="happy", language="zh")  # 没 expression key
    _, _, _, _, expr, _ = _parse(
        raw,
        available_expressions=["smile", "normal"],
        fallback_expression="normal",
    )
    assert expr == "normal"


def test_live2d_fallback_invalid_returns_empty():
    """fallback 也不在 available 里 → 返回 ""(不崩)"""
    raw = _dump(text="x", mood="happy", language="zh", expression="BadVal")
    _, _, _, _, expr, _ = _parse(
        raw,
        available_expressions=["smile"],
        fallback_expression="AlsoBad",
    )
    assert expr == ""


def test_live2d_motion_works_same_as_expression():
    raw = _dump(text="x", mood="happy", language="zh", motion="tap")
    _, _, _, _, _, mot = _parse(raw, available_motions=["idle", "tap"])
    assert mot == "tap"


# === parse 失败时使用 fallback,包括 expression/motion ===

def test_malformed_json_uses_all_fallbacks():
    raw = '{"text'
    text, kao, mood, lang, expr, mot = _parse(
        raw,
        available_expressions=["normal"],
        available_motions=["idle"],
        fallback_expression="normal",
        fallback_motion="idle",
    )
    assert text == FB_TEXT
    assert kao == FB_KAOMOJI
    assert mood == FB_MOOD
    assert lang == FB_LANG
    assert expr == "normal"
    assert mot == "idle"


def test_empty_text_uses_all_fallbacks():
    raw = _dump(text="", mood="happy", language="zh")
    text, _, _, _, expr, _ = _parse(
        raw,
        available_expressions=["normal"],
        fallback_expression="normal",
    )
    assert text == FB_TEXT
    assert expr == "normal"
