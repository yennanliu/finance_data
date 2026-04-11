"""Custom exceptions for the analysis package."""


class AnalysisError(Exception):
    """Base exception for all analysis-related errors."""
    pass


class LLMError(AnalysisError):
    """Exception raised when LLM API calls fail."""
    pass


class DataFetchError(AnalysisError):
    """Exception raised when data fetching fails."""
    pass


class ConfigError(AnalysisError):
    """Exception raised for configuration errors."""
    pass
