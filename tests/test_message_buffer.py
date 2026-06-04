import pytest

from g_chan.chat.base import ChatMessage
from g_chan.interaction.buffer import MessageBuffer


def _msg(user: str, body: str = "...") -> ChatMessage:
    return ChatMessage(user=user, body=body, raw=f"@G酱 {body}")


def test_empty_buffer_starts_with_no_first_at():
    buf = MessageBuffer(max_size=10)
    assert buf.is_empty()
    assert buf.first_at_ms() is None


def test_first_add_records_first_at_ms():
    buf = MessageBuffer(max_size=10)
    buf.add(_msg("alice"), now_ms=1000)
    assert not buf.is_empty()
    assert buf.first_at_ms() == 1000


def test_subsequent_adds_do_not_change_first_at():
    buf = MessageBuffer(max_size=10)
    buf.add(_msg("alice"), now_ms=1000)
    buf.add(_msg("bob"), now_ms=1500)
    buf.add(_msg("charlie"), now_ms=2000)
    assert buf.first_at_ms() == 1000


def test_same_user_keeps_latest_message():
    """同一 user 多次 add,只留最新一条(latest wins)。"""
    buf = MessageBuffer(max_size=10)
    buf.add(_msg("alice", body="hello"), now_ms=1000)
    buf.add(_msg("alice", body="how are you"), now_ms=1500)
    buf.add(_msg("alice", body="anyone there"), now_ms=2000)
    items = buf.latest_n(10)
    assert len(items) == 1
    assert items[0].user == "alice"
    assert items[0].body == "anyone there"


def test_lru_eviction_when_exceeds_max_size():
    """超过 max_size 时,evict 最老的 user(LRU)。"""
    buf = MessageBuffer(max_size=3)
    buf.add(_msg("alice"), now_ms=1000)
    buf.add(_msg("bob"), now_ms=1100)
    buf.add(_msg("charlie"), now_ms=1200)
    buf.add(_msg("dave"), now_ms=1300)  # 应 evict alice
    items = buf.latest_n(10)
    users = [m.user for m in items]
    assert users == ["bob", "charlie", "dave"]


def test_updating_existing_user_refreshes_lru_position():
    """已存在的 user 再 add,把它移到最新位置(不会被下一个新 user 撞掉)。"""
    buf = MessageBuffer(max_size=3)
    buf.add(_msg("alice"), now_ms=1000)
    buf.add(_msg("bob"), now_ms=1100)
    buf.add(_msg("charlie"), now_ms=1200)
    buf.add(_msg("alice", body="hi again"), now_ms=1300)  # alice 刷新到最新
    buf.add(_msg("dave"), now_ms=1400)  # 现在 evict 谁?bob(已是最老)
    items = buf.latest_n(10)
    users = [m.user for m in items]
    assert users == ["charlie", "alice", "dave"]


def test_latest_n_returns_most_recent():
    buf = MessageBuffer(max_size=10)
    buf.add(_msg("alice"), now_ms=1000)
    buf.add(_msg("bob"), now_ms=1100)
    buf.add(_msg("charlie"), now_ms=1200)
    items = buf.latest_n(2)
    users = [m.user for m in items]
    assert users == ["bob", "charlie"]


def test_max_size_zero_means_unlimited():
    """max_size=0 → 不 evict,可以装无限多 user。"""
    buf = MessageBuffer(max_size=0)
    for i in range(100):
        buf.add(_msg(f"user{i}"), now_ms=1000 + i)
    items = buf.latest_n(100)
    assert len(items) == 100


def test_clear_resets_buffer_and_first_at():
    buf = MessageBuffer(max_size=10)
    buf.add(_msg("alice"), now_ms=1000)
    buf.clear()
    assert buf.is_empty()
    assert buf.first_at_ms() is None


def test_after_clear_first_add_records_new_first_at():
    buf = MessageBuffer(max_size=10)
    buf.add(_msg("alice"), now_ms=1000)
    buf.clear()
    buf.add(_msg("bob"), now_ms=5000)
    assert buf.first_at_ms() == 5000


def test_negative_max_size_raises():
    with pytest.raises(ValueError):
        MessageBuffer(max_size=-1)
