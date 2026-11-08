
"""Custom exceptions for the TraceGuard application."""


class TraceGuardError(Exception):
    """Base exception for all TraceGuard application errors."""


class EventLoadingError(TraceGuardError):
    """Raised when event data cannot be loaded."""


class EventValidationError(TraceGuardError):
    """Raised when an event contains invalid data."""


class IntegrityError(TraceGuardError):
    """Raised when records contain contradictory information."""


class OrderNotFoundError(TraceGuardError):
    """Raised when the requested order does not exist."""


class InvestigationError(TraceGuardError):
    """Raised when an investigation operation fails."""


class ToolExecutionError(TraceGuardError):
    """Raised when an investigation tool cannot complete its operation."""
