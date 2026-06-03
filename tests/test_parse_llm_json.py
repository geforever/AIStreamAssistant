import json

import pytest

from g_chan.llm.base import parse_llm_json


def _dump(**kw) -> str:
    return json.dumps(kw, ensure_ascii=False)


def test_full_payload():
    raw = _dump(text="哼,本小姐才没有", kaomoji="(›´ω`‹)", mood="tsundere")
    text, kao, mood = parse_llm_json(raw)
    assert text == "哼,本小姐才没有"
    assert kao == "(›´ω`‹)"
    assert mood == "tsundere"


def test_empty_kaomoji_allowed():
    raw = _dump(text="好的", kaomoji="", mood="happy")
    text, kao, mood = parse_llm_json(raw)
    assert text == "好的"
    assert kao == ""
    assert mood == "happy"


def test_missing_kaomoji_field_defaults_empty():
    raw = _dump(text="好的", mood="happy")
    text, kao, mood = parse_llm_json(raw)
    assert text == "好的"
    assert kao == ""
    assert mood == "happy"


@pytest.mark.parametrize("mood_name", [
    "happy", "angry", "sad", "surprised",
    "shy",   "thinking", "tsundere", "dizzy",
])
def test_all_eight_moods_accepted(mood_name):
    raw = _dump(text="x", mood=mood_name)
    _, _, mood = parse_llm_json(raw)
    assert mood == mood_name


def test_unknown_mood_falls_back_to_happy():
    raw = _dump(text="x", mood="lolwut")
    _, _, mood = parse_llm_json(raw)
    assert mood == "happy"


def test_malformed_json_falls_back_to_raw_as_text():
    raw = "这不是 JSON {但是有花括号"
    text, kao, mood = parse_llm_json(raw)
    assert text == raw.strip()
    assert kao == ""
    assert mood == "happy"


def test_empty_string_input():
    text, kao, mood = parse_llm_json("")
    assert text == ""
    assert kao == ""
    assert mood == "happy"


def test_json_array_rejected():
    """LLM 返回数组而不是对象 → fallback。"""
    raw = '["text", "mood"]'
    text, kao, mood = parse_llm_json(raw)
    assert text == raw.strip()
    assert kao == ""
    assert mood == "happy"


def test_whitespace_stripped_from_fields():
    raw = _dump(text="  好的  ", kaomoji="  (=ω=)  ", mood="happy")
    text, kao, _ = parse_llm_json(raw)
    assert text == "好的"
    assert kao == "(=ω=)"


def test_non_string_text_coerced():
    """LLM 万一不按 schema 返回了数字之类的 — 不该崩。"""
    raw = json.dumps({"text": 42, "mood": "happy"})
    text, _, _ = parse_llm_json(raw)
    assert text == "42"
