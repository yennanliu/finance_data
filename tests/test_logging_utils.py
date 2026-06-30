"""Unit tests for analysis.utils.logging_utils."""

import logging

import pytest

from scripts.analysis.utils.logging_utils import setup_logger

pytestmark = pytest.mark.unit


def test_returns_logger_with_name():
    logger = setup_logger("test_logger_a")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "test_logger_a"


def test_default_level_is_info():
    logger = setup_logger("test_logger_b")
    assert logger.level == logging.INFO


def test_custom_level():
    logger = setup_logger("test_logger_c", level=logging.DEBUG)
    assert logger.level == logging.DEBUG


def test_idempotent_handler_attachment():
    name = "test_logger_idempotent"
    first = setup_logger(name)
    handler_count = len(first.handlers)
    assert handler_count >= 1
    second = setup_logger(name)
    # Calling again must not stack duplicate handlers.
    assert len(second.handlers) == handler_count
    assert first is second


def test_handler_has_formatter():
    logger = setup_logger("test_logger_fmt")
    assert logger.handlers[0].formatter is not None
