# src/exceptions.py
# Custom exception classes for our pipeline.
#
# WHY custom exceptions?
# Built-in exceptions (ValueError, ConnectionError) are too generic.
# When you see "PipelineExtractError" in a log, you know immediately
# which phase failed and why. Generic exceptions make debugging hard.

class PipelineError(Exception):
    """
    Base class for all our pipeline exceptions.
    All our custom exceptions inherit from this,
    so you can catch any pipeline error with: except PipelineError
    """
    pass


class ExtractError(PipelineError):
    """Raised when data extraction from an API fails."""
    pass


class TransformError(PipelineError):
    """Raised when data cleaning or transformation fails."""
    pass


class LoadError(PipelineError):
    """Raised when loading data into the database fails."""
    pass


class APIRateLimitError(ExtractError):
    """
    Raised when an API returns HTTP 429 (Too Many Requests).
    This is a special case — we should wait and retry,
    not give up immediately.
    """
    pass


class APIAuthError(ExtractError):
    """
    Raised when an API returns HTTP 401 or 403.
    This means our API key is wrong or expired.
    Retrying won't help — human intervention needed.
    """
    pass
