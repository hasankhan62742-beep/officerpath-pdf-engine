# OfficerPath AI — PDF Engine (Phase 1A)
# In-memory per-user rate limiter (sliding window).
#
# DOCUMENTED LIMITATION: state lives in this process only. With a
# single Render free instance (the Stage-1 deploy shape, ADR-001)
# that is acceptable; with more than one replica a distributed
# limiter (e.g. Redis) is required, because a user could otherwise
# get N x the limit by hitting N replicas.

import time
from collections import deque

from app.core.errors import ApiError


class RateLimiter:
    def __init__(self) -> None:
        # key -> deque of request timestamps (seconds since epoch)
        self._buckets: dict[str, deque] = {}

    def check(self, key: str, limit: int, window_seconds: int) -> None:
        now = time.monotonic()
        bucket = self._buckets.setdefault(key, deque())
        while bucket and bucket[0] <= now - window_seconds:
            bucket.popleft()
        if len(bucket) >= limit:
            raise ApiError(
                status_code=429,
                code="rate_limited",
                message="Too many requests. Please wait and try again.",
            )
        bucket.append(now)

    def reset(self) -> None:
        self._buckets.clear()


rate_limiter = RateLimiter()
