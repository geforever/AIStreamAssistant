"""Persona 拼装:用户人设(可编辑) + 直播上下文 + 程序输出契约。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from g_chan.prompts import OUTPUT_RULES


@dataclass
class StreamContext:
    title: str
    game_name: str


class PersonaLoader:
    def __init__(
        self,
        *,
        base_path: str | Path,
        include_stream_context: bool = True,
    ):
        self._base_path = Path(base_path)
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
        # 程序契约(代码注入,用户改不到)
        sections.append(OUTPUT_RULES)
        return "\n\n".join(sections)
