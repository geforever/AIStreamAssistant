"""批处理模式的 user message 构造 — 跟 Orchestrator._scheduled_flush 配套。

实际模板在同目录的 batch.md,使用 {{var}} 语法做变量替换。
当前支持的变量:
- {{messages}} — 编号列表形式的观众消息("[N] user: body")
"""
from __future__ import annotations

import re
from pathlib import Path

from g_chan.chat.base import ChatMessage

_TEMPLATE_PATH = Path(__file__).resolve().parent / "reply_prompt.md"

_VAR_RE = re.compile(r"\{\{(\w+)\}\}")


def _load_template() -> str:
    return _TEMPLATE_PATH.read_text(encoding="utf-8")


# 模块导入时一次性加载
_TEMPLATE: str = _load_template()


def _render(template: str, **vars: str) -> str:
    """把 {{var}} 替换成 vars[var]。未提供的变量原样保留(便于发现)。"""
    def _sub(m: re.Match) -> str:
        key = m.group(1)
        return vars.get(key, m.group(0))
    return _VAR_RE.sub(_sub, template)


def build_batch_user_message(messages: list[ChatMessage]) -> str:
    """把 buffer 的多条消息拼成 batch prompt(放进 LLMMessage.user)。
    """
    lines = [f"[{i}] {m.user}: {m.body}" for i, m in enumerate(messages, 1)]
    return _render(_TEMPLATE, messages="\n".join(lines)).strip()
