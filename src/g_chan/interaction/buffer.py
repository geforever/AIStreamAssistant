"""MessageBuffer — 普通观众 @G酱 消息的滚动 buffer。

特性:
- per-user latest-wins(同一 user 多次 @ 只留最新一条)
- LRU eviction 当超过 max_size 时
- 记录 first_at_ms(第一条进入 buffer 的时间戳),用于 scheduled flush
- max_size=0 → 不限容量
"""
from __future__ import annotations

from collections import OrderedDict

from g_chan.chat.base import ChatMessage


class MessageBuffer:
    def __init__(self, max_size: int):
        if max_size < 0:
            raise ValueError("max_size must be >= 0")
        self._max_size = max_size
        # key = user name, value = ChatMessage
        # OrderedDict 保留插入/更新顺序,最末位是"最新激活"的
        self._items: OrderedDict[str, ChatMessage] = OrderedDict()
        self._first_at_ms: float | None = None

    def add(self, msg: ChatMessage, *, now_ms: float) -> None:
        """添加(或更新)一条消息。同一 user 多次 add 只保留最新一条。"""
        if self._first_at_ms is None:
            self._first_at_ms = now_ms

        if msg.user in self._items:
            # 同一 user 再次发声 → 更新消息,刷新到最新位置
            self._items.move_to_end(msg.user)
            self._items[msg.user] = msg
            return

        # 新 user
        self._items[msg.user] = msg
        # 如有容量限制,LRU evict 最老的
        if self._max_size > 0:
            while len(self._items) > self._max_size:
                self._items.popitem(last=False)

    def latest_n(self, n: int) -> list[ChatMessage]:
        """返回最近 n 条(按插入/激活顺序,最新在末尾)。n<=0 → 返回全部。"""
        items = list(self._items.values())
        if n > 0:
            items = items[-n:]
        return items

    def is_empty(self) -> bool:
        return not self._items

    def first_at_ms(self) -> float | None:
        return self._first_at_ms

    def clear(self) -> None:
        self._items.clear()
        self._first_at_ms = None
