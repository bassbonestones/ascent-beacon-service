"""Tests for `app/core/auth.py`."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.core.auth import get_current_user
from app.models.user import User


@pytest.mark.asyncio
async def test_get_current_user_returns_user_when_token_valid() -> None:
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")
    user = User(
        id="00000000-0000-0000-0000-000000000001",
        display_name="Test User",
        primary_email="user@example.com",
        is_email_verified=True,
    )
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = user
    db.execute.return_value = execute_result

    with patch("app.core.auth.decode_access_token", return_value={"sub": user.id}):
        resolved = await get_current_user(credentials, db)

    assert resolved.id == user.id


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_sub_claim() -> None:
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="bad-token")
    db = AsyncMock()

    with patch("app.core.auth.decode_access_token", return_value={}):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials, db)

    assert exc.value.status_code == 401
    assert "Invalid authentication credentials" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_rejects_missing_user_record() -> None:
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid-token")
    db = AsyncMock()
    execute_result = MagicMock()
    execute_result.scalar_one_or_none.return_value = None
    db.execute.return_value = execute_result

    with patch("app.core.auth.decode_access_token", return_value={"sub": "missing-user"}):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials, db)

    assert exc.value.status_code == 401
    assert "User not found" in exc.value.detail


@pytest.mark.asyncio
async def test_get_current_user_maps_decode_errors_to_401() -> None:
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="expired-token")
    db = AsyncMock()

    with patch("app.core.auth.decode_access_token", side_effect=ValueError("Token expired")):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials, db)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token expired"
