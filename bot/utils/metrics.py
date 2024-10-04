"""
Metrics Collector for Discord Bot.

This module provides functionality for collecting and recording various bot metrics.
It uses Prometheus client library for metrics.
"""

import time
import asyncio
from functools import wraps
from typing import Callable, Any
from prometheus_client import Counter, Histogram, Gauge

# Define metrics
MESSAGE_COUNTER = Counter('bot_messages_processed', 'Number of messages processed')
COMMAND_COUNTER = Counter('bot_commands_executed', 'Number of commands executed', ['command'])
API_LATENCY = Histogram('bot_api_latency_seconds', 'Latency of API calls in seconds', ['api'])
THREAD_GAUGE = Gauge('bot_active_threads', 'Number of active threads being monitored')
CENSORED_MESSAGES = Counter('bot_censored_messages', 'Number of messages censored')
PLUGIN_ERRORS = Counter('bot_plugin_errors', 'Number of plugin errors', ['plugin'])
DB_QUERY_LATENCY = Histogram('bot_db_query_latency_seconds', 'Latency of database queries in seconds')
MEMORY_USAGE = Gauge('bot_memory_usage_bytes', 'Memory usage of the bot in bytes')
CPU_USAGE = Gauge('bot_cpu_usage_percent', 'CPU usage of the bot as a percentage')

class MetricsCollector:
    """
    A class for collecting and recording various bot metrics.

    This class provides static methods for incrementing counters,
    recording latencies, and updating gauges.
    """

    @staticmethod
    def increment_message() -> None:
        """Increment the counter for processed messages."""
        MESSAGE_COUNTER.inc()

    @staticmethod
    def increment_command(command_name: str) -> None:
        """
        Increment the counter for executed commands.

        Args:
            command_name (str): The name of the command executed.
        """
        COMMAND_COUNTER.labels(command=command_name).inc()

    @staticmethod
    def record_api_latency(api_name: str):
        """
        Decorator for recording API call latencies.

        Args:
            api_name (str): The name of the API being called.

        Returns:
            Callable: Decorated function that records API latency.
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start_time = time.perf_counter()
                result = await func(*args, **kwargs)
                latency = time.perf_counter() - start_time
                API_LATENCY.labels(api=api_name).observe(latency)
                return result

            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                start_time = time.perf_counter()
                result = func(*args, **kwargs)
                latency = time.perf_counter() - start_time
                API_LATENCY.labels(api=api_name).observe(latency)
                return result

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator

    @staticmethod
    def set_active_threads(count: int) -> None:
        """
        Set the number of active threads being monitored.

        Args:
            count (int): The number of active threads.
        """
        THREAD_GAUGE.set(count)

    @staticmethod
    def increment_censored_message() -> None:
        """Increment the counter for censored messages."""
        CENSORED_MESSAGES.inc()

    @staticmethod
    def increment_plugin_error(plugin_name: str) -> None:
        """
        Increment the counter for plugin errors.

        Args:
            plugin_name (str): The name of the plugin that encountered an error.
        """
        PLUGIN_ERRORS.labels(plugin=plugin_name).inc()

    @staticmethod
    def record_db_query_latency():
        """
        Decorator for recording database query latencies.

        Returns:
            Callable: Decorated function that records database query latency.
        """
        def decorator(func: Callable) -> Callable:
            @wraps(func)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                start_time = time.perf_counter()
                result = await func(*args, **kwargs)
                latency = time.perf_counter() - start_time
                DB_QUERY_LATENCY.observe(latency)
                return result

            @wraps(func)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                start_time = time.perf_counter()
                result = func(*args, **kwargs)
                latency = time.perf_counter() - start_time
                DB_QUERY_LATENCY.observe(latency)
                return result

            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            else:
                return sync_wrapper

        return decorator

    @staticmethod
    def set_memory_usage(usage_bytes: float) -> None:
        """
        Set the current memory usage of the bot.

        Args:
            usage_bytes (float): The memory usage in bytes.
        """
        MEMORY_USAGE.set(usage_bytes)

    @staticmethod
    def set_cpu_usage(usage_percent: float) -> None:
        """
        Set the current CPU usage of the bot.

        Args:
            usage_percent (float): The CPU usage as a percentage.
        """
        CPU_USAGE.set(usage_percent)