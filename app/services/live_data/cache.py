import copy
import time
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True)
class CachedValue(Generic[T]):
    value: T
    age_seconds: float
    stale: bool


@dataclass
class _CacheEntry(Generic[T]):
    value: T
    stored_at: float
    expires_at: float


class TTLCache(Generic[T]):
    """Small in-process TTL cache; values are copied at the boundary."""

    def __init__(
        self,
        ttl_seconds: float = 300,
        max_stale_seconds: float = 3600,
        max_entries: int = 256,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_stale_seconds = max_stale_seconds
        self.max_entries = max_entries
        self._entries: dict[str, _CacheEntry[T]] = {}

    def get(self, key: str) -> CachedValue[T] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        now = time.monotonic()
        age = now - entry.stored_at
        if now > entry.expires_at:
            return None
        return CachedValue(copy.deepcopy(entry.value), age, stale=False)

    def get_stale(self, key: str) -> CachedValue[T] | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        age = time.monotonic() - entry.stored_at
        if age > self.max_stale_seconds:
            return None
        return CachedValue(copy.deepcopy(entry.value), age, stale=True)

    def put(self, key: str, value: T) -> None:
        now = time.monotonic()
        self._entries[key] = _CacheEntry(
            value=copy.deepcopy(value),
            stored_at=now,
            expires_at=now + self.ttl_seconds,
        )
        if len(self._entries) > self.max_entries:
            oldest = min(self._entries, key=lambda item: self._entries[item].stored_at)
            del self._entries[oldest]
