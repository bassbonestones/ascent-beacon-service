"""Tests for `app/core/logging.py`."""

from unittest.mock import patch

from app.core.logging import configure_logging, get_request_logger


def test_configure_logging_local_environment() -> None:
    with (
        patch("app.core.logging.settings.env", "local"),
        patch("app.core.logging.logger.remove") as remove_mock,
        patch("app.core.logging.logger.add") as add_mock,
        patch("app.core.logging.logger.info") as info_mock,
    ):
        configure_logging()

    remove_mock.assert_called_once()
    # local adds stderr handler only
    assert add_mock.call_count == 1
    info_mock.assert_called_once()


def test_configure_logging_non_local_adds_file_handler() -> None:
    with (
        patch("app.core.logging.settings.env", "production"),
        patch("app.core.logging.logger.remove") as remove_mock,
        patch("app.core.logging.logger.add") as add_mock,
        patch("app.core.logging.logger.info") as info_mock,
    ):
        configure_logging()

    remove_mock.assert_called_once()
    # non-local adds stderr + file handlers
    assert add_mock.call_count == 2
    info_mock.assert_called_once()


def test_get_request_logger_binds_request_id() -> None:
    with patch("app.core.logging.logger.bind") as bind_mock:
        get_request_logger("req-123")

    bind_mock.assert_called_once_with(request_id="req-123")
