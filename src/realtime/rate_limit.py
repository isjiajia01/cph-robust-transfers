from __future__ import annotations

import threading
import time


class TokenBucket:
    def __init__(self, rate_per_sec: float, capacity: int) -> None:
        self.rate_per_sec = rate_per_sec
        self.capacity = float(capacity)
        self.tokens = float(capacity)
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def acquire(self, tokens: float = 1.0) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                elapsed = now - self.last
                self.last = now
                self.tokens = min(self.capacity, self.tokens + elapsed * self.rate_per_sec)
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return
                missing = tokens - self.tokens
                wait = missing / self.rate_per_sec if self.rate_per_sec > 0 else 1.0
            time.sleep(max(wait, 0.01))
