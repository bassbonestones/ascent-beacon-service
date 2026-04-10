"""Tests for auth service with mocked external dependencies."""

import pytest
from unittest.mock import patch, AsyncMock
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_service import AuthService
from app.models.user import User


# ============================================================================
# _find_or_create_user_for_oauth Tests
# ============================================================================


@pytest.mark.asyncio
async def test_find_or_create_user_new_user(db_session):
    """Test creating a new user via OAuth."""
    user, is_new = await AuthService._find_or_create_user_for_oauth(
        db_session,
        provider="google",
        provider_subject="google123",
        email="newuser@test.com",
    )
    
    assert is_new is True
    assert user.primary_email == "newuser@test.com"
    await db_session.commit()


@pytest.mark.asyncio
async def test_find_or_create_user_existing_identity(db_session, test_user: User):
    """Test finding existing user by OAuth identity."""
    from app.models.user_identity import UserIdentity
    
    # Create identity for test_user
    identity = UserIdentity(
        user_id=test_user.id,
        provider="google",
        provider_subject="existing_sub",
        email=test_user.primary_email,
    )
    db_session.add(identity)
    await db_session.commit()
    
    # Should find existing user
    user, is_new = await AuthService._find_or_create_user_for_oauth(
        db_session,
        provider="google",
        provider_subject="existing_sub",
        email=test_user.primary_email,
    )
    
    assert is_new is False
    assert user.id == test_user.id


@pytest.mark.asyncio
async def test_find_or_create_user_existing_email_new_provider(db_session, test_user: User):
    """Test linking new provider to existing user by email."""
    # User exists but no Apple identity yet
    user, is_new = await AuthService._find_or_create_user_for_oauth(
        db_session,
        provider="apple",
        provider_subject="apple123",
        email=test_user.primary_email,  # Same email as existing user
    )
    
    # Should link to existing user
    assert user.id == test_user.id
    await db_session.commit()


# ============================================================================
# authenticate_with_google Tests
# ============================================================================


@pytest.mark.asyncio
async def test_authenticate_with_google_new_user(db_session):
    """Test Google authentication for new user."""
    mock_payload = {
        "sub": "google_sub_123",
        "email": "newgoogle@test.com",
        "email_verified": True,
    }
    
    mock_tokens = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 3600,
        "token_type": "bearer",
    }
    
    with patch(
        "app.services.auth_service.ProviderAuthService.verify_google_token",
        new_callable=AsyncMock,
        return_value=mock_payload,
    ), patch(
        "app.services.auth_service.TokenService.create_tokens_for_user",
        new_callable=AsyncMock,
        return_value=mock_tokens,
    ):
        result = await AuthService.authenticate_with_google(
            db_session,
            id_token="fake_google_token",
            device_id="device123",
            device_name="Test Device",
        )
    
    assert "access_token" in result
    assert "refresh_token" in result
    assert "user" in result
    assert result["user"].primary_email == "newgoogle@test.com"


@pytest.mark.asyncio
async def test_authenticate_with_google_unverified_email(db_session):
    """Test Google auth doesn't use unverified email."""
    mock_payload = {
        "sub": "google_sub_456",
        "email": "unverified@test.com",
        "email_verified": False,  # Email not verified
    }
    
    mock_tokens = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 3600,
        "token_type": "bearer",
    }
    
    with patch(
        "app.services.auth_service.ProviderAuthService.verify_google_token",
        new_callable=AsyncMock,
        return_value=mock_payload,
    ), patch(
        "app.services.auth_service.TokenService.create_tokens_for_user",
        new_callable=AsyncMock,
        return_value=mock_tokens,
    ):
        result = await AuthService.authenticate_with_google(
            db_session,
            id_token="fake_google_token",
        )
    
    # User created without email since it wasn't verified
    assert result["user"].primary_email is None


# ============================================================================
# authenticate_with_apple Tests
# ============================================================================


@pytest.mark.asyncio
async def test_authenticate_with_apple_new_user(db_session):
    """Test Apple authentication for new user."""
    mock_payload = {
        "sub": "apple_sub_123",
        "email": "newapple@test.com",
        "email_verified": True,
    }
    
    mock_tokens = {
        "access_token": "test_access_token",
        "refresh_token": "test_refresh_token",
        "expires_in": 3600,
        "token_type": "bearer",
    }
    
    with patch(
        "app.services.auth_service.ProviderAuthService.verify_apple_token",
        new_callable=AsyncMock,
        return_value=mock_payload,
    ), patch(
        "app.services.auth_service.TokenService.create_tokens_for_user",
        new_callable=AsyncMock,
        return_value=mock_tokens,
    ):
        result = await AuthService.authenticate_with_apple(
            db_session,
            id_token="fake_apple_token",
            device_id="device456",
        )
    
    assert "access_token" in result
    assert "user" in result


# ============================================================================
# update_display_name Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_display_name_success(db_session, test_user: User):
    """Test updating user's display name."""
    new_name = "Updated Name"
    
    updated_user = await AuthService.update_display_name(
        db_session,
        test_user.id,
        new_name,
    )
    
    assert updated_user.display_name == new_name


@pytest.mark.asyncio
async def test_update_display_name_user_not_found(db_session):
    """Test updating display name for non-existent user."""
    with pytest.raises(ValueError, match="User not found"):
        await AuthService.update_display_name(
            db_session,
            "00000000-0000-0000-0000-000000000000",
            "New Name",
        )


# ============================================================================
# Delegation Methods Tests
# ============================================================================


@pytest.mark.asyncio
async def test_request_magic_link_delegates(db_session):
    """Test that request_magic_link delegates to EmailAuthService."""
    with patch(
        "app.services.auth_service.EmailAuthService.request_magic_link",
        new_callable=AsyncMock,
    ) as mock_request:
        await AuthService.request_magic_link(db_session, "test@test.com")
        mock_request.assert_called_once_with(db_session, "test@test.com")


@pytest.mark.asyncio
async def test_verify_magic_link_delegates(db_session):
    """Test that verify_magic_link delegates to EmailAuthService."""
    mock_result = {"access_token": "token", "user": None}
    
    with patch(
        "app.services.auth_service.EmailAuthService.verify_magic_link",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_verify:
        result = await AuthService.verify_magic_link(
            db_session,
            token="123456",
            email="test@test.com",
        )
        
        mock_verify.assert_called_once()
        assert result == mock_result


@pytest.mark.asyncio
async def test_refresh_access_token_delegates(db_session):
    """Test that refresh_access_token delegates to TokenService."""
    mock_result = {"access_token": "new_token"}
    
    with patch(
        "app.services.auth_service.TokenService.refresh_access_token",
        new_callable=AsyncMock,
        return_value=mock_result,
    ) as mock_refresh:
        result = await AuthService.refresh_access_token(db_session, "old_refresh_token")
        
        mock_refresh.assert_called_once_with(db_session, "old_refresh_token")
        assert result == mock_result


@pytest.mark.asyncio
async def test_logout_delegates(db_session):
    """Test that logout delegates to TokenService."""
    with patch(
        "app.services.auth_service.TokenService.logout",
        new_callable=AsyncMock,
    ) as mock_logout:
        await AuthService.logout(db_session, "refresh_token_to_revoke")
        
        mock_logout.assert_called_once_with(db_session, "refresh_token_to_revoke")
