# utils/circuit_breaker.py

"""
Circuit Breaker for Discord Bot.

This module implements the Circuit Breaker pattern to handle failures in external service calls.
It helps to prevent cascading failures and allows the system to recover from errors.
"""

import time
from enum import Enum
import asyncio

from utils.custom_exceptions import CircuitBreakerError

class CircuitState(Enum):
    """Enum representing the possible states of the circuit breaker."""
    CLOSED = 'closed'       # Normal operation, requests are allowed
    OPEN = 'open'           # Failure threshold exceeded, requests are blocked
    HALF_OPEN = 'half_open' # Transitional state, allowing a test request

class CircuitBreaker:
    """
    Implementation of the Circuit Breaker pattern.
    """

    __slots__ = ('failure_threshold', 'recovery_time', 'reset_timeout', 'state', 'failures', 'last_failure_time', '_lock')

    def __init__(self, failure_threshold: int, recovery_time: float, reset_timeout: float = 60.0):
        """
        Initialize the CircuitBreaker.

        Args:
            failure_threshold (int): Number of failures before opening the circuit.
            recovery_time (float): Time in seconds to wait before attempting recovery.
            reset_timeout (float): Time in seconds to reset the failure count in the CLOSED state.
        """
        self.failure_threshold = failure_threshold
        self.recovery_time = recovery_time
        self.reset_timeout = reset_timeout
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time = None
        self._lock = asyncio.Lock()

    async def call(self, func, *args, **kwargs):
        """
        Execute a function with circuit breaker protection.
        """
        async with self._lock:
            if self.state == CircuitState.OPEN:
                current_time = time.time()
                if current_time - self.last_failure_time >= self.recovery_time:
                    self.state = CircuitState.HALF_OPEN
                else:
                    raise CircuitBreakerError("Circuit is open. Requests are temporarily blocked.")

            elif self.state == CircuitState.CLOSED:
                self._reset_failure_count_if_needed()

        try:
            result = await func(*args, **kwargs)
            if self.state == CircuitState.HALF_OPEN:
                await self._reset()
            return result
        except Exception as e:
            await self._record_failure()
            raise e

    async def _record_failure(self):
        """
        Record a failure and potentially open the circuit.
        """
        async with self._lock:
            self.failures += 1
            self.last_failure_time = time.time()
            if self.failures >= self.failure_threshold:
                self.state = CircuitState.OPEN

    async def _reset(self):
        """
        Reset the circuit breaker to its initial closed state.
        """
        async with self._lock:
            self.failures = 0
            self.state = CircuitState.CLOSED
            self.last_failure_time = None

    def _reset_failure_count_if_needed(self):
        """
        Reset the failure count if the reset timeout has expired.
        """
        if self.last_failure_time and (time.time() - self.last_failure_time) >= self.reset_timeout:
            self.failures = 0
            self.last_failure_time = None