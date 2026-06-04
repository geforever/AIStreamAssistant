from g_chan.llm.schemas.chat_reply import build_chat_reply_schema


def test_schema_always_includes_all_six_fields():
    """无论 expressions/motions 是否传入,schema 都含 6 个 properties + 全部 required。"""
    schema = build_chat_reply_schema()
    props = schema["properties"]
    assert set(props.keys()) == {
        "text", "kaomoji", "mood", "language", "expression", "motion",
    }
    assert set(schema["required"]) == {
        "text", "mood", "language", "expression", "motion",
    }


def test_schema_with_expressions_and_motions_populates_enums():
    schema = build_chat_reply_schema(
        expressions=["smile", "angry", "sad"],
        motions=["idle", "tap"],
    )
    props = schema["properties"]
    assert set(props["expression"]["enum"]) == {"smile", "angry", "sad", "None"}
    assert set(props["motion"]["enum"]) == {"idle", "tap", "None"}


def test_schema_empty_lists_still_have_none_in_enum():
    """没传 expressions/motions → enum 只有 ["None"](LLM 被迫输出 "None")。"""
    schema = build_chat_reply_schema(expressions=[], motions=[])
    props = schema["properties"]
    assert props["expression"]["enum"] == ["None"]
    assert props["motion"]["enum"] == ["None"]


def test_schema_none_args_treated_as_empty():
    """显式传 None → 当空 list 处理。"""
    schema = build_chat_reply_schema(expressions=None, motions=None)
    props = schema["properties"]
    assert props["expression"]["enum"] == ["None"]
    assert props["motion"]["enum"] == ["None"]


def test_schema_mood_enum_always_contains_8_values():
    schema = build_chat_reply_schema()
    mood_enum = schema["properties"]["mood"]["enum"]
    assert set(mood_enum) == {
        "happy", "angry", "sad", "surprised",
        "shy",   "thinking", "tsundere", "dizzy",
    }


def test_schema_language_enum_always_contains_3():
    schema = build_chat_reply_schema()
    lang_enum = schema["properties"]["language"]["enum"]
    assert set(lang_enum) == {"zh", "en", "ja"}
