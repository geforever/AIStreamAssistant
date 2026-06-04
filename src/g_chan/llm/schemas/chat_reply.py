"""LLM 输出 JSON schema — 动态构造,expression/motion enum 由模型(或空+None)决定。

字段对齐:
- src/g_chan/llm/base.py (parse_llm_json + LLMReply)
- src/g_chan/prompts/output_rules.md (LLM 看到的文本描述)
"""
from __future__ import annotations

from g_chan.llm.base import LANGUAGE_VALUES, MOOD_VALUES


def build_chat_reply_schema(
    *,
    expressions: list[str] | None = None,
    motions: list[str] | None = None,
) -> dict:
    """构造 chat reply 的 JSON schema。

    expression / motion 永远是 required 字段;enum 来自传入的 expressions/motions + "None"。
    expressions/motions 名字按 model3.json 原样大小写,不归一化。
    expressions=[] / motions=[] → enum 只有 "None"(LLM 被迫输出 "None")。
    """
    expressions = expressions or []
    motions = motions or []

    properties: dict = {
        "text": {
            "type": "string",
            "description": (
                "Main reply text intended for TTS. Spoken words only. "
                "No kaomoji, emoji, brackets, @user, or stage directions."
            ),
        },
        "kaomoji": {
            "type": "string",
            "description": (
                "Optional kaomoji for chat decoration only (not spoken by TTS). "
                "May be empty string."
            ),
        },
        "mood": {
            "type": "string",
            "enum": list(MOOD_VALUES),
            "description": (
                "Character emotion label (semantic, independent of Live2D physical expression). "
                "Pick the one that best describes your inner feeling."
            ),
        },
        "language": {
            "type": "string",
            "enum": list(LANGUAGE_VALUES),
            "description": (
                "Language code matching the actual language of the 'text' field. "
                "Mirror the viewer's language."
            ),
        },
        "expression": {
            "type": "string",
            "enum": expressions + ["None"],
            "description": (
                "Live2D facial expression name, EXACT case from the loaded model. "
                "Pick one whose name semantically matches the character's "
                "current state, OR pick 'None' to keep current expression. "
                "Skip expressions whose names you don't understand."
            ),
        },
        "motion": {
            "type": "string",
            "enum": motions + ["None"],
            "description": (
                "Live2D body motion to play once, EXACT case from the loaded model. "
                "Pick one when it semantically fits the reply (e.g. 'Tap' for a "
                "playful poke), otherwise 'None'."
            ),
        },
    }
    return {
        "type": "object",
        "properties": properties,
        "required": ["text", "mood", "language", "expression", "motion"],
    }
