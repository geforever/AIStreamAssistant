"""Persona 拼装:用户人设 + 直播上下文 + 程序输出契约。

输出契约文本由调用方(__main__ 装配时)预先 render 好后注入。
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class StreamContext:
    title: str
    game_name: str


class PersonaLoader:
    def __init__(
        self,
        *,
        base_path: str | Path,
        output_rules_text: str,
        include_stream_context: bool = True,
    ):
        self._base_path = Path(base_path)
        self._output_rules_text = output_rules_text
        self._include_stream_context = include_stream_context

    def assemble(self, *, stream_ctx: StreamContext | None) -> str:
        base = self._base_path.read_text(encoding="utf-8").strip()
        sections = [base]
        if self._include_stream_context and stream_ctx is not None:
            sections.append(
                "[当前直播上下文]\n"
                f"直播间标题: {stream_ctx.title}\n"
                f"正在玩: {stream_ctx.game_name}\n"
                "[/当前直播上下文]\n"
                "如果观众问到你在玩什么/做什么,基于上述上下文回答。"
            )
        sections.append(self._output_rules_text)
        return "\n\n".join(sections)
