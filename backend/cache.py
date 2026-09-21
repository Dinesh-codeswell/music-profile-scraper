"""Thread-safe in-memory TTL cache (positive + negative entries)."""
from __future__ import annotations

import threading
import time
from typing import Any, Optional

_NEGATIVE = "__negative__"


class TTLCache:
    def __init__(self, ttl_positive: int = 86400, ttl_negative: int = 7200) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self.ttl_positive = ttl_positive
        self.ttl_negative = ttl_negative

    def get(self, key: str) -> Optional[Any]:
        now = time.time()
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires, value = entry
            if expires < now:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: Any, *, ttl: Optional[int] = None) -> None:
        expires = time.time() + (ttl if ttl is not None else self.ttl_positive)
        with self._lock:
            self._store[key] = (expires, value)

    def set_negative(self, key: str) -> None:
        self.set(key, _NEGATIVE, ttl=self.ttl_negative)

    def is_negative(self, value: Any) -> bool:
        return value is _NEGATIVE

    def delete(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def stats(self) -> dict[str, int]:
        with self._lock:
            now = time.time()
            live = sum(1 for exp, _ in self._store.values() if exp >= now)
            return {"live_entries": live, "total_slots": len(self._store)}
