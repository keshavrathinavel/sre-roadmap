# Write a token bucket rate limiter.
#
# A token bucket answers one question per request: "is this allowed right now?"
# Tokens refill at a fixed rate (the sustained limit) up to a max capacity (the
# burst it tolerates). Each request costs 1 token; no token -> reject.
#
# Requirements:
#   - rate (tokens/sec) = sustained limit; capacity = max burst. Start full.
#   - Lazy refill: don't use a background timer. On each call compute how many
#     tokens dripped in since last access: tokens = min(capacity, tokens + elapsed*rate).
#   - Use time.monotonic() (never time.time() -- wall clock can jump backward).
#   - allow(cost=1) -> True (took a token) / False (reject, e.g. HTTP 429).
#
# Follow-ups (each builds on the last):
#   1. Make it thread-safe          -> lock wraps the WHOLE check-and-decrement (TOCTOU race).
#   2. Make it per-client           -> one bucket per API key/IP via defaultdict.
#   3. Do it as a sliding window    -> different tradeoff (precise but O(n) memory).
#
# Key one-liners:
#   - "The lock must wrap refill + check + decrement together; locking only the
#      refill leaves a check-then-decrement TOCTOU race."
#   - "Token bucket = O(1) state + burst tolerance. Sliding window = precise, no
#      overshoot, but O(n) memory per client (a timestamp per request). Gateways
#      pick token bucket because O(1)-per-key scales to millions of keys."

import time
import threading
from collections import defaultdict, deque


# --- 1. Base + thread-safe token bucket ------------------------------------

class TokenBucket:
    def __init__(self, rate, capacity):
        self.rate = rate            # tokens/sec -- sustained limit
        self.capacity = capacity    # max burst
        self.tokens = capacity      # start full
        self.last = time.monotonic()
        self._lock = threading.Lock()

    def allow(self, cost=1):
        # Lock wraps refill + check + decrement so they're atomic. Locking only
        # the refill would leave the check-then-decrement as a TOCTOU race:
        # two threads could both see tokens==1 and both be allowed on one token.
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last = now
            if self.tokens >= cost:
                self.tokens -= cost
                return True
            return False


# --- 2. Per-client rate limiter (the real gateway shape) -------------------

class RateLimiter:
    """One bucket per client_id (API key / IP). New clients start with a full bucket.

    Caveats to state in an interview, not build:
      - This dict lives in ONE process. Across N gateway replicas, move state to
        Redis with an atomic Lua script, or divide the limit by N.
      - _buckets grows forever -> memory leak. Real systems evict idle buckets
        (LRU / TTL).
    """

    def __init__(self, rate, capacity):
        self._buckets = defaultdict(lambda: TokenBucket(rate, capacity))

    def allow(self, client_id, cost=1):
        return self._buckets[client_id].allow(cost)


# --- 3. Sliding window log (the "do it differently" follow-up) -------------

class SlidingWindowLog:
    """Precise alternative: stores a timestamp per request and counts how many
    fall in the trailing window. No burst overshoot, but O(n) memory per client."""

    def __init__(self, limit, window_sec):
        self.limit = limit
        self.window = window_sec
        self.hits = deque()  # timestamps, oldest at the left

    def allow(self):
        now = time.monotonic()
        while self.hits and self.hits[0] <= now - self.window:
            self.hits.popleft()  # drop timestamps that fell out of the window
        if len(self.hits) < self.limit:
            self.hits.append(now)
            return True
        return False


# --- demo -------------------------------------------------------------------

if __name__ == "__main__":
    # capacity 5, refill 2/sec: first 5 burst through, then ~2/sec.
    bucket = TokenBucket(rate=2, capacity=5)
    print("Burst of 8 against a capacity-5 bucket:")
    print("  ", [bucket.allow() for _ in range(8)])  # 5x True, then False

    time.sleep(1)  # ~2 tokens refill
    print("After 1s sleep (~2 tokens back):")
    print("  ", [bucket.allow() for _ in range(3)])  # ~2x True, then False

    print("\nPer-client limiter (rate=1, capacity=2):")
    limiter = RateLimiter(rate=1, capacity=2)
    print("  alice:", [limiter.allow("alice") for _ in range(3)])  # True,True,False
    print("  bob:  ", [limiter.allow("bob") for _ in range(3)])    # independent bucket
