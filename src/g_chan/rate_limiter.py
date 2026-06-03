"""全局窗口限流:单一时间窗口,无人粒度。"""
from __future__ import annotations

import time
from collections.abc import Callable


def _default_now_ms() -> float:
    return time.monotonic() * 1000


class RateLimiter:
    def __init__(self, window_ms: int, *, now_ms: Callable[[], float] = _default_now_ms):
        self.window_ms = window_ms
        self._last_fire_at: float = -float("inf")
        self._now_ms = now_ms

    def try_acquire(self) -> bool:
        if self.window_ms <= 0:
            return True
        now = self._now_ms()
        if now - self._last_fire_at < self.window_ms:
            return False
        self._last_fire_at = now
        return True
