"""共用 fakes / fixtures。"""
from __future__ import annotations

from g_chan.chat.base import ChatAdapter, ChatHandler, ChatMessage
from g_chan.llm.base import LLMMessage, LLMProvider, LLMReply, Mood


class FakeLLM(LLMProvider):
    def __init__(self):
        self.calls: list[list[LLMMessage]] = []
        self.next_reply: LLMReply | None = None
        self.should_raise: Exception | None = None

    async def generate(
        self,
        messages: list[LLMMessage],
        *,
        temperature: float = 0.9,
        max_tokens: int = 300,
        timeout_s: float = 10.0,
    ) -> LLMReply:
        self.calls.append(messages)
        if self.should_raise:
            raise self.should_raise
        assert self.next_reply is not None
        return self.next_reply


class FakeChat(ChatAdapter):
    def __init__(self):
        self.sent: list[str] = []
        self.handler: ChatHandler | None = None

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    def on_trigger(self, handler: ChatHandler) -> None:
        self.handler = handler
    async def send(self, text: str) -> None:
        self.sent.append(text)

    async def emit(self, user: str, body: str) -> None:
        assert self.handler is not None
        await self.handler(ChatMessage(user=user, body=body, raw=f"@G酱 {body}"))


def make_reply(text: str, mood: Mood = "happy") -> LLMReply:
    return LLMReply(text=text, mood=mood, raw=text, latency_ms=42,
                    tokens_in=10, tokens_out=20)
