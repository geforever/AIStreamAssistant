"""JSON schema for the LLM chat reply.

Used with provider-native structured-output features such as
Gemini ``responseSchema``, OpenAI Structured Outputs, etc.

Field descriptions are in English so that LLMs interpret them consistently
across locales — model behavior on schema descriptions is best in English.
"""
from __future__ import annotations

from g_chan.llm.base import MOOD_VALUES

CHAT_REPLY_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": (
                "Main reply text intended for text-to-speech (TTS) synthesis. "
                "Must contain only spoken words. Do NOT include kaomoji, "
                "emoticons, brackets, asterisks, or stage directions here; "
                "decorative emoticons belong in the 'kaomoji' field."
            ),
        },
        "kaomoji": {
            "type": "string",
            "description": (
                "Optional kaomoji (Japanese-style emoticon) for visual chat "
                "decoration only. Will NOT be spoken by TTS. May be an empty "
                "string when no decoration is appropriate."
            ),
        },
        "mood": {
            "type": "string",
            "enum": list(MOOD_VALUES),
            "description": (
                "Emotion label used to drive the Live2D character expression. "
                "Must be one of the listed enum values."
            ),
        },
    },
    "required": ["text", "mood"],
}
