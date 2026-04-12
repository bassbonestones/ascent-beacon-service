"""Tests for token_service module."""

import pytest
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.token_service import TokenService
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.core.time import utc_now
from app.core.security import hash_token


@pytest.mark.asyncio
async def test_create_tokens_for_user(db_session, test_user):
    """Test creating access and refresh tokens for a user."""
    tokens = await TokenService.create_tokens_for_user(
        db_session, 
        test_user,
        device_id="test-device",
        device_name="Test Device",
    )
    
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    assert tokens["access_token"] is not None
    assert tokens["refresh_token"] is not None
    
    # Verify refresh token was stored
    from sqlalchemy import select
    result = await db_session.execute(
        select(RefreshToken).where(RefreshToken.user_id == test_user.id)
    )
    refresh_tokens = result.scalars().all()
    assert len(refresh_tokens) >= 1


@pytest.mark.asyncio
async def test_create_tokens_without_device_info(db_session, test_user):
    """Test creating tokens without device info."""
    tokens = await TokenService.create_tokens_for_user(db_session, test_user)
    
    assert "access_token" in tokens
    assert "refresh_token" in tokens


@pytest.mark.asyncio
async def test_refresh_access_token_success(db_session, test_user):
    """Test refreshing access token with valid refresh token."""
    # First create tokens
    tokens = await TokenService.create_tokens_for_user(
        db_session, 
        test_user,
        device_id="test-device",
    )
    await db_session.commit()
    
    # Now refresh
    new_tokens = await TokenService.refresh_access_token(
        db_session, 
        tokens["refresh_token"],
    )
    
    assert "access_token" in new_tokens
    assert "refresh_token" in new_tokens
    # New tokens should be different
    assert new_tokens["refresh_token"] != tokens["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_access_token_user_not_found_mocked() -> None:
    """Valid refresh row but missing User raises (lines 76–78)."""
    rt_obj = MagicMock()
    rt_obj.token_hash = "h"
    rt_obj.user_id = "user-1"

    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = [rt_obj]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=exec_result)
    mock_db.get = AsyncMock(return_value=None)

    with patch(
        "app.services.token_service.verify_token_hash",
        return_value=True,
    ):
        with pytest.raises(ValueError, match="User not found"):
            await TokenService.refresh_access_token(mock_db, "raw-token")


@pytest.mark.asyncio
async def test_logout_finds_second_matching_hash() -> None:
    """Logout loop skips non-matching rows before revoking (lines 118–122)."""
    rt1 = MagicMock()
    rt1.token_hash = "first"
    rt2 = MagicMock()
    rt2.token_hash = "second"

    exec_result = MagicMock()
    exec_result.scalars.return_value.all.return_value = [rt1, rt2]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=exec_result)

    with patch(
        "app.services.token_service.verify_token_hash",
        side_effect=[False, True],
    ):
        await TokenService.logout(mock_db, "presented")

    assert rt2.revoked_at is not None


@pytest.mark.asyncio
async def test_refresh_access_token_invalid(db_session):
    """Test refreshing with invalid token raises error."""
    with pytest.raises(ValueError) as exc_info:
        await TokenService.refresh_access_token(db_session, "invalid-token")
    
    assert "Invalid or expired refresh token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_refresh_access_token_expired(db_session, test_user):
    """Test refreshing with expired token raises error."""
    # Manually create an expired refresh token
    expired_token = "expired-test-token"
    refresh_record = RefreshToken(
        user_id=test_user.id,
        token_hash=hash_token(expired_token),
        expires_at=utc_now() - timedelta(hours=1),  # Already expired
    )
    db_session.add(refresh_record)
    await db_session.commit()
    
    with pytest.raises(ValueError) as exc_info:
        await TokenService.refresh_access_token(db_session, expired_token)
    
    assert "Invalid or expired refresh token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_refresh_access_token_revoked(db_session, test_user):
    """Test refreshing with revoked token raises error."""
    # Manually create a revoked refresh token
    revoked_token = "revoked-test-token"
    refresh_record = RefreshToken(
        user_id=test_user.id,
        token_hash=hash_token(revoked_token),
        expires_at=utc_now() + timedelta(hours=1),
        revoked_at=utc_now(),  # Already revoked
    )
    db_session.add(refresh_record)
    await db_session.commit()
    
    with pytest.raises(ValueError) as exc_info:
        await TokenService.refresh_access_token(db_session, revoked_token)
    
    assert "Invalid or expired refresh token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_logout_success(db_session, test_user):
    """Test logout revokes refresh token."""
    # Create tokens
    tokens = await TokenService.create_tokens_for_user(db_session, test_user)
    await db_session.commit()
    
    # Logout
    await TokenService.logout(db_session, tokens["refresh_token"])
    
    # Verify token is revoked
    from sqlalchemy import select
    result = await db_session.execute(
        select(RefreshToken).where(
            RefreshToken.user_id == test_user.id,
            RefreshToken.revoked_at.is_not(None),
        )
    )
    revoked_tokens = result.scalars().all()
    assert len(revoked_tokens) >= 1


@pytest.mark.asyncio
async def test_logout_invalid_token(db_session, test_user):
    """Test logout with invalid token raises error."""
    with pytest.raises(ValueError) as exc_info:
        await TokenService.logout(db_session, "invalid-token")
    
    assert "Refresh token not found" in str(exc_info.value)


@pytest.mark.asyncio
async def test_logout_already_revoked_token(db_session, test_user):
    """Test logout with already revoked token raises error."""
    # Create and immediately revoke a token
    revoked_token = "already-revoked-token"
    refresh_record = RefreshToken(
        user_id=test_user.id,
        token_hash=hash_token(revoked_token),
        expires_at=utc_now() + timedelta(hours=1),
        revoked_at=utc_now(),
    )
    db_session.add(refresh_record)
    await db_session.commit()
    
    with pytest.raises(ValueError) as exc_info:
        await TokenService.logout(db_session, revoked_token)
    
    assert "Refresh token not found" in str(exc_info.value)
