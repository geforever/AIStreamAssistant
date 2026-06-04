"""批处理模式的 user message 构造 — 跟 Orchestrator._scheduled_flush 配套。"""
from __future__ import annotations

from g_chan.chat.base import ChatMessage


def build_batch_user_message(messages: list[ChatMessage]) -> str:
    """把 buffer 的多条消息拼成 batch prompt(放进 LLMMessage.user)。

    LLM 看到这种格式会知道"挑 1 个回应 / 合并 / 沉默"的元上下文。
    """
    lines = [f"[{i}] {m.user}: {m.body}" for i, m in enumerate(messages, 1)]
    return (
        "下面是最近收到的普通观众 @G酱 消息(已按用户 dedup,每人最新一条):\n\n"
        + "\n".join(lines)
        + "\n\n请按你的人设标准从中挑选 1 个最值得回应的(或合并相似的多条,用一句话呼应),"
        + "实在没意思可保持沉默 (text 留空字符串)。"
    )
