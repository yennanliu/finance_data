"""Custom exceptions for the analysis package."""


class AnalysisError(Exception):
    """Base exception for all analysis-related errors."""
    pass


class LLMError(AnalysisError):
    """Exception raised when LLM API calls fail."""
    pass


class RefusalError(LLMError):
    """Raised when a model still refuses after every refusal retry.

    Returning the refusal text instead let it be saved and published as a
    report (MRVL 2026-10-22). It is not a terminal error, so
    ``run_with_fallback`` moves on to the next provider.
    """
    pass


class DataFetchError(AnalysisError):
    """Exception raised when data fetching fails."""
    pass


class ConfigError(AnalysisError):
    """Exception raised for configuration errors."""
    pass
