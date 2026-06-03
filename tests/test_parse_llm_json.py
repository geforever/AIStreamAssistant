import json

import pytest

from g_chan.llm.base import parse_llm_json

FB_TEXT = "FB_TEXT"
FB_KAOMOJI = "FB_KAOMOJI"
FB_MOOD = "dizzy"
FB_LANG = "zh"


def _parse(raw: str):
    return parse_llm_json(
        raw,
        fallback_text=FB_TEXT,
        fallback_kaomoji=FB_KAOMOJI,
        fallback_mood=FB_MOOD,
        fallback_language=FB_LANG,
    )


def _dump(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False)


def test_full_payload():
    raw = _dump(text="哼,本小姐才没有", kaomoji="(›´ω`‹)", mood="tsundere")
    text, kao, mood, _ = _parse(raw)
    assert text == "哼,本小姐才没有"
    assert kao == "(›´ω`‹)"
    assert mood == "tsundere"


def test_empty_kaomoji_allowed():
    raw = _dump(text="好的", kaomoji="", mood="happy")
    text, kao, mood, _ = _parse(raw)
    assert text == "好的"
    assert kao == ""
    assert mood == "happy"


def test_missing_kaomoji_field_defaults_empty():
    raw = _dump(text="好的", mood="happy")
    text, kao, mood, _ = _parse(raw)
    assert text == "好的"
    assert kao == ""
    assert mood == "happy"


@pytest.mark.parametrize("mood_name", [
    "happy", "angry", "sad", "surprised",
    "shy",   "thinking", "tsundere", "dizzy",
])
def test_all_eight_moods_accepted(mood_name):
    raw = _dump(text="x", mood=mood_name)
    _, _, mood, _ = _parse(raw)
    assert mood == mood_name


def test_unknown_mood_falls_back_to_happy():
    """未知 mood 不触发整体 fallback,只把 mood 替换成 happy。"""
    raw = _dump(text="x", mood="lolwut")
    text, _, mood, _ = _parse(raw)
    assert text == "x"
    assert mood == "happy"


def test_malformed_json_uses_fallback():
    """残破 JSON(被截断、不合法) → 返回 fallback 三元组,绝不把垃圾送 chat/TTS。"""
    raw = '{"text'  # 模拟被 token 限制截断
    text, kao, mood, _ = _parse(raw)
    assert text == FB_TEXT
    assert kao == FB_KAOMOJI
    assert mood == FB_MOOD


def test_empty_string_input_uses_fallback():
    text, kao, mood, _ = _parse("")
    assert text == FB_TEXT
    assert kao == FB_KAOMOJI
    assert mood == FB_MOOD


def test_json_array_uses_fallback():
    raw = '["text", "mood"]'
    text, _, mood, _ = _parse(raw)
    assert text == FB_TEXT
    assert mood == FB_MOOD


def test_empty_text_field_uses_fallback():
    raw = _dump(text="", mood="happy")
    text, _, mood, _ = _parse(raw)
    assert text == FB_TEXT
    assert mood == FB_MOOD


def test_whitespace_stripped_from_fields():
    raw = _dump(text="  好的  ", kaomoji="  (=ω=)  ", mood="happy")
    text, kao, _, _ = _parse(raw)
    assert text == "好的"
    assert kao == "(=ω=)"


def test_non_string_text_coerced():
    """LLM 万一不按 schema 返回了数字之类的 — 不该崩。"""
    raw = json.dumps({"text": 42, "mood": "happy"})
    text, _, _, _ = _parse(raw)
    assert text == "42"


@pytest.mark.parametrize("lang", ["zh", "en", "ja"])
def test_all_three_languages_accepted(lang):
    raw = _dump(text="x", mood="happy", language=lang)
    _, _, _, language = _parse(raw)
    assert language == lang


def test_unknown_language_falls_back():
    """未知 language 不触发整体 fallback,只把 language 替换成 fallback。"""
    raw = _dump(text="x", mood="happy", language="ko")
    text, _, _, language = _parse(raw)
    assert text == "x"
    assert language == FB_LANG


def test_missing_language_field_uses_fallback():
    raw = _dump(text="x", mood="happy")
    _, _, _, language = _parse(raw)
    assert language == FB_LANG
