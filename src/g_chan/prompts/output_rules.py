"""LLM 输出格式契约 — 跟 g_chan.llm.base.parse_llm_json + CHAT_REPLY_SCHEMA 严格对齐。

实际内容在同目录的 output_rules.md (方便手改)。

调整该 md 时,必须同步检查:
- src/g_chan/llm/schemas/chat_reply.py (responseSchema)
- src/g_chan/llm/base.py (parse_llm_json, MOOD_VALUES, LANGUAGE_VALUES)
"""
from __future__ import annotations

from pathlib import Path

_TEMPLATE_PATH = Path(__file__).resolve().parent / "output_rules.md"


def _load() -> str:
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


# 模块导入时一次性加载,避免运行时 IO
OUTPUT_RULES: str = _load()
