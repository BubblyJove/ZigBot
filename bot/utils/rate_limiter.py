"""
Rate Limiter for Discord Bot.

This module provides classes for implementing rate limiting functionality.
It includes a general RateLimiter class and a specific CommandRateLimiter for use with bot commands.
"""

import time
from collections import defaultdict
from discord.ext import commands

from utils.custom_exceptions import RateLimitError

class RateLimiter:
    """
    A general-purpose rate limiter.

    This class implements a simple rate limiting mechanism based on a maximum number of
    calls within a given time frame.
    """

    def __init__(self, max_calls: int, time_frame: float):
        """
        Initialize the RateLimiter.

        Args:
            max_calls (int): The maximum number of calls allowed within the time frame.
            time_frame (float): The time frame in seconds.
        """
        self.max_calls = max_calls
        self.time_frame = time_frame
        self.call_history = defaultdict(list)

    def check_rate_limit(self, key):
        """
        Check if a new call is allowed under the rate limit.

        Args:
            key: The key to check the rate limit for (e.g., user ID, API endpoint).

        Raises:
            RateLimitError: If the rate limit has been exceeded.
        """
        current_time = time.time()
        history = self.call_history[key]
        # Remove stale entries
        while history and current_time - history[0] > self.time_frame:
            history.pop(0)
        if len(history) >= self.max_calls:
            raise RateLimitError(f"Rate limit exceeded for key: {key}")
        history.append(current_time)

    def get_remaining_calls(self, key) -> int:
        """
        Get the number of remaining calls allowed for a key.

        Args:
            key: The key to check.

        Returns:
            int: The number of remaining calls allowed.
        """
        current_time = time.time()
        history = self.call_history[key]
        history = [t for t in history if current_time - t < self.time_frame]
        self.call_history[key] = history
        return max(0, self.max_calls - len(history))

    def get_reset_time(self, key) -> float:
        """
        Get the time until the rate limit resets for a key.

        Args:
            key: The key to check.

        Returns:
            float: The number of seconds until the rate limit resets.
        """
        history = self.call_history.get(key, [])
        if not history:
            return 0.0
        current_time = time.time()
        oldest_call = history[0]
        return max(0.0, self.time_frame - (current_time - oldest_call))

class CommandRateLimiter(RateLimiter):
    """
    A rate limiter specifically for Discord bot commands.

    This class extends RateLimiter to provide a convenient way to
    apply rate limiting to Discord bot commands.
    """

    def __init__(self, max_calls: int = 5, time_frame: float = 60.0):
        """
        Initialize the CommandRateLimiter.

        Args:
            max_calls (int): The maximum number of calls allowed within the time frame. Default is 5.
            time_frame (float): The time frame in seconds. Default is 60 seconds.
        """
        super().__init__(max_calls, time_frame)

    async def __call__(self, ctx):
        """
        Check rate limit for a command invocation.

        Args:
            ctx (commands.Context): The invocation context.

        Returns:
            bool: True if the command is allowed, False if the rate limit is exceeded.
        """
        key = f"{ctx.command.qualified_name}:{ctx.author.id}"
        try:
            self.check_rate_limit(key)
            return True
        except RateLimitError:
            remaining_time = self.get_reset_time(key)
            await ctx.send(
                f"You're using this command too frequently. Please wait {remaining_time:.1f} seconds."
            )
            return False

def dynamic_cooldown(rate: int, per: float):
    """
    Create a dynamic cooldown for commands based on the user's role or other factors.

    Args:
        rate (int): The number of uses permitted before the cooldown.
        per (float): The number of seconds to wait before resetting the cooldown.

    Returns:
        function: A cooldown check function for use with Discord commands.
    """
    def cooldown_check(ctx):
        if ctx.author.guild_permissions.administrator:
            return None  # No cooldown for administrators
        return commands.Cooldown(rate, per)
    return commands.dynamic_cooldown(cooldown_check)