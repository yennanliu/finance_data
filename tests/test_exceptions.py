"""Unit tests for the analysis exception hierarchy."""

import pytest

from scripts.analysis.exceptions import (
    AnalysisError, LLMError, DataFetchError, ConfigError,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("exc", [LLMError, DataFetchError, ConfigError])
def test_subclasses_of_analysis_error(exc):
    assert issubclass(exc, AnalysisError)
    assert issubclass(exc, Exception)


def test_analysis_error_is_exception():
    assert issubclass(AnalysisError, Exception)


def test_can_raise_and_catch_as_base():
    with pytest.raises(AnalysisError):
        raise LLMError("boom")


def test_message_preserved():
    err = DataFetchError("network down")
    assert str(err) == "network down"
