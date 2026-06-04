"""LLM 输出规则 — 单个模板,用 {{expressions_list}} / {{motions_list}} 注入。

调整 .md 文件时,必须同步检查:
- src/g_chan/llm/schemas/chat_reply.py (build_chat_reply_schema)
- src/g_chan/llm/base.py (parse_llm_json, MOOD_VALUES, LANGUAGE_VALUES)
"""
from __future__ import annotations

import re
from pathlib import Path

_TEMPLATE_PATH = Path(__file__).resolve().parent / "output_rules.md"

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def _render(template: str, **vars: str) -> str:
    def _sub(m: re.Match) -> str:
        return vars.get(m.group(1), m.group(0))
    return _VAR_RE.sub(_sub, template)


def render_output_rules(
    *,
    expressions: list[str] | None = None,
    motions: list[str] | None = None,
) -> str:
    """返回 LLM 看到的输出规则文本。

    expressions / motions 为空 → 列表渲染成 "(无)",LLM 只能选 None。
    """
    template = _TEMPLATE_PATH.read_text(encoding="utf-8")
    return _render(
        template,
        expressions_list=", ".join(expressions or []) or "(无)",
        motions_list=", ".join(motions or []) or "(无)",
    )
