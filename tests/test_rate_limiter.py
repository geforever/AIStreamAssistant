from g_chan.rate_limiter import RateLimiter


def test_first_acquire_succeeds():
    rl = RateLimiter(window_ms=1000)
    assert rl.try_acquire() is True


def test_second_acquire_within_window_fails():
    rl = RateLimiter(window_ms=1000)
    rl.try_acquire()
    assert rl.try_acquire() is False


def test_acquire_succeeds_after_window(monkeypatch):
    # 用可控时间避免真 sleep
    now = [1000.0]  # ms
    def fake_now_ms() -> float:
        return now[0]

    rl = RateLimiter(window_ms=1000, now_ms=fake_now_ms)
    assert rl.try_acquire() is True
    now[0] += 500
    assert rl.try_acquire() is False
    now[0] += 600  # 累计 1100ms 后
    assert rl.try_acquire() is True


def test_zero_window_always_allows():
    rl = RateLimiter(window_ms=0)
    assert rl.try_acquire() is True
    assert rl.try_acquire() is True
