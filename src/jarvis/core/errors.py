"""Exception hierarchy used across JARVIS."""
from __future__ import annotations


class JarvisError(Exception):
    """Base class for all expected, user-presentable errors."""


class ConfigError(JarvisError):
    pass


class ProviderError(JarvisError):
    """The AI provider call failed."""


class ProviderAuthError(ProviderError):
    pass


class ProviderRateLimitError(ProviderError):
    pass


class ToolError(JarvisError):
    """A tool failed in a way that should be reported to the user."""


class ToolTimeout(ToolError):
    pass


class ToolNotFound(ToolError):
    pass


class PermissionDenied(JarvisError):
    pass


class ValidationError(JarvisError):
    pass


class Cancelled(JarvisError):
    """Raised when the user hits the emergency stop."""