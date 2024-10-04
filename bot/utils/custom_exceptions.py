"""
Custom Exceptions for Discord Bot.

This module defines custom exception classes used throughout the bot.
These exceptions provide more specific error handling and messaging.
"""

class BotException(Exception):
    """Base exception for the bot."""

class ConfigurationError(BotException):
    """Raised when there's an error in the configuration."""

class DatabaseError(BotException):
    """Raised when there's a database-related error."""

class APIError(BotException):
    """Raised when there's an API-related error."""

class ThreadManagementError(BotException):
    """Raised when there's an error in thread management."""

class CensorshipError(BotException):
    """Raised when there's an error in the censorship system."""

class PluginError(BotException):
    """Raised when there's an error related to plugins."""

class RateLimitError(BotException):
    """Raised when rate limits are exceeded."""

class CircuitBreakerError(BotException):
    """Raised when the circuit breaker is triggered."""

class BackupError(BotException):
    """Raised when there's an error during backup operations."""

class CommandError(BotException):
    """Raised when there's an error executing a command."""

class PermissionError(BotException):
    """Raised when a user doesn't have the required permissions."""