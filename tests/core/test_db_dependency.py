"""Targeted tests for `app/core/db.py` dependency helper."""

from unittest.mock import AsyncMock, patch

import pytest

from app.core.db import get_db


class _SessionContext:
    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


@pytest.mark.asyncio
async def test_get_db_yields_session_and_closes_it() -> None:
    session = AsyncMock()

    with patch("app.core.db.AsyncSessionLocal", return_value=_SessionContext(session)):
        gen = get_db()
        yielded = await gen.__anext__()
        assert yielded is session

        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

    session.close.assert_awaited_once()
