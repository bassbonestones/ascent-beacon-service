"""Targeted tests for `app/main.py` startup/shutdown paths."""

from fastapi import FastAPI
from unittest.mock import AsyncMock, patch

import pytest

from app.main import lifespan, root_redirect


@pytest.mark.asyncio
async def test_lifespan_runs_startup_and_shutdown_hooks() -> None:
    app = FastAPI()
    close_mock = AsyncMock()

    with (
        patch("app.main.configure_logging") as configure_mock,
        patch("app.main.logger.info") as info_mock,
        patch("app.core.llm.llm_client.close", close_mock),
    ):
        async with lifespan(app):
            pass

    configure_mock.assert_called_once()
    close_mock.assert_awaited_once()
    assert info_mock.call_count >= 2


@pytest.mark.asyncio
async def test_root_redirect_points_to_docs() -> None:
    response = await root_redirect()
    assert response.headers["location"] == "/docs"
