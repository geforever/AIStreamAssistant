"""聊天平台抽象 — Twitch / YouTube / ... 都实现这个接口。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass


@dataclass
class ChatMessage:
    user: str           # 发送者用户名
    body: str           # 消息正文(已去除 trigger 前缀)
    raw: str            # 原始整行(含 trigger,用于日志)
    is_priority: bool = False   # True = mod / broadcaster / vip,走即时路径


# 收到 @G酱 触发消息后的回调
ChatHandler = Callable[[ChatMessage], Awaitable[None]]


class ChatAdapter(ABC):
    @abstractmethod
    async def connect(self) -> None: ...

    @abstractmethod
    async def disconnect(self) -> None: ...

    @abstractmethod
    def on_trigger(self, handler: ChatHandler) -> None:
        """注册回调,只在消息以 trigger 开头时被调用。"""

    @abstractmethod
    async def send(self, text: str) -> None:
        """向频道发送文本(原样发送,调用方负责拼 @user)。"""
