import time
from contextlib import contextmanager
from typing import Any, Dict, Optional


class RoutePerf:
    def __init__(self, route: str, user_id: Optional[str] = None):
        self.route = route
        self.user_id = user_id
        self.started_at = time.perf_counter()
        self.steps: Dict[str, float] = {}
        self.counts: Dict[str, int] = {}
        self.meta: Dict[str, Any] = {}

    @contextmanager
    def step(self, name: str):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.steps[name] = round((time.perf_counter() - started) * 1000, 1)

    def add_count(self, key: str, amount: int = 1):
        self.counts[key] = self.counts.get(key, 0) + amount

    def set_meta(self, key: str, value: Any):
        self.meta[key] = value

    def total_ms(self) -> float:
        return round((time.perf_counter() - self.started_at) * 1000, 1)

    def to_log_fields(self) -> Dict[str, Any]:
        return {
            "route": self.route,
            "user_id": self.user_id,
            "total_ms": self.total_ms(),
            "steps_ms": self.steps,
            "counts": self.counts,
            "meta": self.meta,
        }

