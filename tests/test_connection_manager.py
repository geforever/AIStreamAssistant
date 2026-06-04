import pytest

from g_chan.server.connection_manager import ConnectionManager


class FakeWS:
    """模拟 FastAPI WebSocket 的最小接口(accept/send_json)。"""
    def __init__(self, *, fail_on_send: bool = False):
        self.sent: list[dict] = []
        self.accepted = False
        self.fail_on_send = fail_on_send

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict) -> None:
        if self.fail_on_send:
            raise RuntimeError("simulated disconnect")
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_connect_adds_client_and_accepts():
    cm = ConnectionManager()
    ws = FakeWS()
    await cm.connect(ws)
    assert ws.accepted is True
    assert cm.client_count() == 1


@pytest.mark.asyncio
async def test_disconnect_removes_client():
    cm = ConnectionManager()
    ws = FakeWS()
    await cm.connect(ws)
    cm.disconnect(ws)
    assert cm.client_count() == 0


@pytest.mark.asyncio
async def test_disconnect_unknown_client_does_not_raise():
    cm = ConnectionManager()
    cm.disconnect(FakeWS())   # 不在 set 里 — 不应抛


@pytest.mark.asyncio
async def test_broadcast_sends_to_all_clients():
    cm = ConnectionManager()
    a = FakeWS()
    b = FakeWS()
    await cm.connect(a)
    await cm.connect(b)
    payload = {"type": "expression", "name": "smile"}
    await cm.broadcast(payload)
    assert a.sent == [payload]
    assert b.sent == [payload]


@pytest.mark.asyncio
async def test_broadcast_drops_failing_clients():
    """send 抛异常的 client 会被 evict,不影响其他 client。"""
    cm = ConnectionManager()
    good = FakeWS()
    bad = FakeWS(fail_on_send=True)
    await cm.connect(good)
    await cm.connect(bad)
    await cm.broadcast({"type": "ping"})
    assert good.sent == [{"type": "ping"}]
    assert cm.client_count() == 1   # bad 被踢


@pytest.mark.asyncio
async def test_broadcast_with_no_clients_is_noop():
    cm = ConnectionManager()
    await cm.broadcast({"type": "ping"})   # 不抛
    assert cm.client_count() == 0
