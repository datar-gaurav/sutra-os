"""Circuit breaker pattern for external service calls (LLM providers, APIs, tools)."""

import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is in OPEN state and the call is rejected."""

    def __init__(self, breaker_name: str, cooldown_remaining: float):
        self.breaker_name = breaker_name
        self.cooldown_remaining = cooldown_remaining
        super().__init__(
            f"Circuit '{breaker_name}' is OPEN. "
            f"Retry after {cooldown_remaining:.0f}s."
        )


class CircuitBreaker:
    """
    Three-state circuit breaker: CLOSED → OPEN → HALF_OPEN → CLOSED.

    CLOSED:    Normal operation. Track failures.
    OPEN:      After threshold failures, reject all calls for cooldown_seconds.
    HALF_OPEN: After cooldown, allow one test call. Success → CLOSED, Failure → OPEN.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        window_seconds: int = 60,
        cooldown_seconds: int = 30,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.window_seconds = window_seconds
        self.cooldown_seconds = cooldown_seconds

        self.state: str = "CLOSED"
        self._failures: list[float] = []
        self._last_failure_time: float = 0
        self._success_count: int = 0
        self._total_calls: int = 0

    async def call(self, func, *args, **kwargs):
        """Execute func through the circuit breaker."""
        self._total_calls += 1

        if self.state == "OPEN":
            elapsed = time.monotonic() - self._last_failure_time
            if elapsed >= self.cooldown_seconds:
                self.state = "HALF_OPEN"
                logger.info(f"Circuit '{self.name}' → HALF_OPEN (testing recovery)")
            else:
                raise CircuitOpenError(self.name, self.cooldown_seconds - elapsed)

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        """Record a successful call."""
        self._success_count += 1
        if self.state == "HALF_OPEN":
            self.state = "CLOSED"
            self._failures.clear()
            logger.info(f"Circuit '{self.name}' → CLOSED (recovered)")

    def _on_failure(self):
        """Record a failed call and potentially trip the breaker."""
        now = time.monotonic()
        # Prune old failures outside the window
        self._failures = [t for t in self._failures if now - t < self.window_seconds]
        self._failures.append(now)
        self._last_failure_time = now

        if self.state == "HALF_OPEN":
            self.state = "OPEN"
            logger.warning(f"Circuit '{self.name}' → OPEN (half-open test failed)")
        elif len(self._failures) >= self.failure_threshold:
            self.state = "OPEN"
            logger.warning(
                f"Circuit '{self.name}' → OPEN "
                f"({len(self._failures)} failures in {self.window_seconds}s)"
            )

    @property
    def stats(self) -> dict:
        return {
            "name": self.name,
            "state": self.state,
            "recent_failures": len(self._failures),
            "total_calls": self._total_calls,
            "success_count": self._success_count,
        }

    def reset(self):
        """Manually reset the circuit breaker to CLOSED."""
        self.state = "CLOSED"
        self._failures.clear()
        logger.info(f"Circuit '{self.name}' manually reset to CLOSED")


# ── Global registry ──────────────────────────────────────────────────────────

_breakers: dict[str, CircuitBreaker] = {}


def get_breaker(
    name: str,
    failure_threshold: int = 5,
    window_seconds: int = 60,
    cooldown_seconds: int = 30,
) -> CircuitBreaker:
    """Get or create a named circuit breaker."""
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(
            name=name,
            failure_threshold=failure_threshold,
            window_seconds=window_seconds,
            cooldown_seconds=cooldown_seconds,
        )
    return _breakers[name]


def get_all_breakers() -> dict[str, dict]:
    """Return stats for all registered circuit breakers."""
    return {name: cb.stats for name, cb in _breakers.items()}
