import pytest

from g_chan.persona.loader import StreamContext
from g_chan.persona.stream_context import HelixClient, StreamContextProvider


class FakeHelix(HelixClient):
    def __init__(self):
        self.calls = 0
        self.next_response: StreamContext | None = StreamContext("初始", "Game A")
        self.should_raise: Exception | None = None

    async def fetch_channel(self, channel: str) -> StreamContext:
        self.calls += 1
        if self.should_raise:
            raise self.should_raise
        assert self.next_response is not None
        return self.next_response


@pytest.mark.asyncio
async def test_first_refresh_caches_value():
    helix = FakeHelix()
    p = StreamContextProvider(channel="alice", helix=helix)
    assert p.current() is None        # 还没拉
    await p.refresh()
    assert helix.calls == 1
    assert p.current() == StreamContext("初始", "Game A")


@pytest.mark.asyncio
async def test_failed_refresh_keeps_last_cached():
    helix = FakeHelix()
    p = StreamContextProvider(channel="alice", helix=helix)
    await p.refresh()
    helix.should_raise = RuntimeError("boom")
    await p.refresh()  # 失败不该抛
    assert p.current() == StreamContext("初始", "Game A")
    assert helix.calls == 2


@pytest.mark.asyncio
async def test_first_refresh_failure_yields_none():
    helix = FakeHelix()
    helix.should_raise = RuntimeError("boom")
    p = StreamContextProvider(channel="alice", helix=helix)
    await p.refresh()
    assert p.current() is None
