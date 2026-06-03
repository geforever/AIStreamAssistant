import pytest

from g_chan.llm.base import parse_mood


@pytest.mark.parametrize("raw,expected_text,expected_mood", [
    ("哼,本小姐才没有 [mood:tsundere]", "哼,本小姐才没有", "tsundere"),
    ("好开心呀~ [mood:happy]",          "好开心呀~",         "happy"),
    ("[mood:sad]",                       "",                   "sad"),
    ("好开心 [mood:happy]   ",           "好开心",             "happy"),
    ("emoji 测试 (=ω=) [mood:shy]",      "emoji 测试 (=ω=)",   "shy"),
])
def test_parses_valid_mood(raw, expected_text, expected_mood):
    text, mood = parse_mood(raw)
    assert text == expected_text
    assert mood == expected_mood


def test_missing_mood_defaults_to_happy():
    text, mood = parse_mood("我没标 mood")
    assert text == "我没标 mood"
    assert mood == "happy"


def test_unknown_mood_defaults_to_happy():
    # [mood:foo] 不在白名单 → 视作无标签
    text, mood = parse_mood("不认识的 mood [mood:lolwut]")
    assert mood == "happy"
    assert "[mood:lolwut]" in text  # 保留原文


@pytest.mark.parametrize("mood_name", [
    "happy", "angry", "sad", "surprised",
    "shy",   "thinking", "tsundere", "dizzy",
])
def test_all_eight_moods_recognized(mood_name):
    text, mood = parse_mood(f"测试 [mood:{mood_name}]")
    assert mood == mood_name
    assert text == "测试"
