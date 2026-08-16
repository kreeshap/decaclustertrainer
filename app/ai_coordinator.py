"""Priority-aware admission control, failover, and provider cooldowns."""

from __future__ import annotations

from contextlib import contextmanager
import re
import threading
import time

from .config import AI_MAX_CONCURRENT_REQUESTS, AI_PROVIDER_RETRIES, AI_RETRY_BASE_SECONDS


PRIORITIES = {"student": 0, "student_retry": 1, "admin_preview": 2, "audit": 3, "classification": 4}


class GenerationCoordinator:
    def __init__(self, max_active: int = AI_MAX_CONCURRENT_REQUESTS):
        self.max_active = max_active
        self._condition = threading.Condition()
        self._active = 0
        self._sequence = 0
        self._waiting: list[tuple[int, int]] = []
        self._cooldowns: dict[str, float] = {}

    @contextmanager
    def slot(self, priority: str):
        rank = PRIORITIES.get(priority, PRIORITIES["audit"])
        with self._condition:
            ticket = (rank, self._sequence)
            self._sequence += 1
            self._waiting.append(ticket)
            while self._active >= self.max_active or ticket != min(self._waiting):
                self._condition.wait()
            self._waiting.remove(ticket)
            self._active += 1
        try:
            yield
        finally:
            with self._condition:
                self._active -= 1
                self._condition.notify_all()

    def available(self, provider: str) -> bool:
        return self._cooldowns.get(provider, 0) <= time.monotonic()

    def cool_down(self, provider: str, error: str, attempt: int) -> float:
        retry_after = re.search(r"retry(?:-|_)?after[^0-9]*(\d+(?:\.\d+)?)", error, re.I)
        delay = float(retry_after.group(1)) if retry_after else AI_RETRY_BASE_SECONDS * (2 ** attempt)
        if "429" in error or "resource_exhausted" in error.lower() or "rate limit" in error.lower():
            delay = max(delay, 15.0)
        self._cooldowns[provider] = time.monotonic() + delay
        return delay

    def run(self, providers: list[tuple[str, callable]], priority: str) -> tuple[object | None, str | None, str | None]:
        errors: list[str] = []
        with self.slot(priority):
            for name, call in providers:
                if not self.available(name):
                    errors.append(f"{name}: temporarily cooling down")
                    continue
                for attempt in range(AI_PROVIDER_RETRIES + 1):
                    result, error = call()
                    if not error:
                        return result, None, name
                    errors.append(f"{name}: {error}")
                    retryable = any(token in error.lower() for token in ("429", "resource_exhausted", "rate limit", "timeout", "504", "temporar"))
                    if not retryable or attempt >= AI_PROVIDER_RETRIES:
                        if retryable:
                            self.cool_down(name, error, attempt)
                        break
                    time.sleep(min(self.cool_down(name, error, attempt), 5.0))
        return None, " | ".join(errors), None


coordinator = GenerationCoordinator()
