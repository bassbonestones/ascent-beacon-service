"""Tests for email auth service with mocked email sending."""

import pytest
from unittest.mock import patch, AsyncMock
from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.email_auth_service import EmailAuthService
from app.models.user import User
from app.models.email_login_token import EmailLoginToken
from app.core.time import utc_now
from app.core.security import hash_token


# ============================================================================
# request_magic_link Tests
# ============================================================================


@pytest.mark.asyncio
async def test_request_magic_link_creates_token(db_session):
    """Test that request_magic_link creates a token in the database."""
    email = "test_magic@example.com"
    
    with patch(
        "app.services.email_auth_service.EmailService.send_verification_code",
        new_callable=AsyncMock,
    ) as mock_send:
        await EmailAuthService.request_magic_link(db_session, email)
        mock_send.assert_called_once()
    
    # Verify token was created
    result = await db_session.execute(
        select(EmailLoginToken).where(EmailLoginToken.email == email.lower())
    )
    token = result.scalar_one_or_none()
    
    assert token is not None
    assert token.email == email.lower()
    assert token.used_at is None
    # Token should expire in the future (just check it's set)
    assert token.expires_at is not None


@pytest.mark.asyncio
async def test_request_magic_link_normalizes_email(db_session):
    """Test that email is normalized (lowercased, stripped)."""
    email = "  Test@EXAMPLE.com  "
    
    with patch(
        "app.services.email_auth_service.EmailService.send_verification_code",
        new_callable=AsyncMock,
    ):
        await EmailAuthService.request_magic_link(db_session, email)
    
    result = await db_session.execute(
        select(EmailLoginToken).where(EmailLoginToken.email == "test@example.com")
    )
    token = result.scalar_one_or_none()
    
    assert token is not None
    assert token.email == "test@example.com"


@pytest.mark.asyncio
async def test_request_magic_link_sends_correct_email(db_session):
    """Test that the verification code is sent to the correct email."""
    email = "receiver@example.com"
    
    with patch(
        "app.services.email_auth_service.EmailService.send_verification_code",
        new_callable=AsyncMock,
    ) as mock_send:
        await EmailAuthService.request_magic_link(db_session, email)
        
        # Check email was sent to correct recipient
        call_args = mock_send.call_args
        assert call_args[0][0] == email.lower()
        # Second arg should be a 6-digit code
        code = call_args[0][1]
        assert len(code) == 6
        assert code.isdigit()


# ============================================================================
# verify_magic_link Tests
# ============================================================================


@pytest.mark.asyncio
async def test_verify_magic_link_invalid_token(db_session):
    """Test that invalid token raises ValueError."""
    with pytest.raises(ValueError, match="Invalid or expired token"):
        await EmailAuthService.verify_magic_link(
            db_session,
            token="000000",
            email="test@example.com",
        )


@pytest.mark.asyncio
async def test_verify_magic_link_expired_token(db_session):
    """Test that expired token raises ValueError."""
    from app.core.security import generate_verification_code
    
    email = "expired@example.com"
    code = generate_verification_code()
    
    # Create expired token
    expired_token = EmailLoginToken(
        email=email,
        token_hash=hash_token(code),
        expires_at=utc_now() - timedelta(minutes=5),  # Already expired
    )
    db_session.add(expired_token)
    await db_session.commit()
    
    with pytest.raises(ValueError, match="Invalid or expired token"):
        await EmailAuthService.verify_magic_link(db_session, token=code, email=email)


@pytest.mark.asyncio
async def test_verify_magic_link_creates_new_user(db_session):
    """Test that valid token for new email creates a user."""
    from app.core.security import generate_verification_code
    
    email = "newuser@example.com"
    code = generate_verification_code()
    
    # Create valid token
    token = EmailLoginToken(
        email=email,
        token_hash=hash_token(code),
        expires_at=utc_now() + timedelta(minutes=10),
    )
    db_session.add(token)
    await db_session.commit()
    
    with patch(
        "app.services.email_auth_service.TokenService.create_tokens_for_user",
        new_callable=AsyncMock,
        return_value={
            "access_token": "test_access",
            "refresh_token": "test_refresh",
            "expires_in": 3600,
            "token_type": "bearer",
        },
    ):
        result = await EmailAuthService.verify_magic_link(
            db_session,
            token=code,
            email=email,
        )
    
    assert "access_token" in result
    assert "user" in result
    assert result["user"].primary_email == email
    assert result["user"].is_email_verified is True


@pytest.mark.asyncio
async def test_verify_magic_link_existing_user(db_session, test_user: User):
    """Test verifying magic link for existing user."""
    from app.core.security import generate_verification_code
    from app.models.user_identity import UserIdentity
    
    email = test_user.primary_email
    code = generate_verification_code()
    
    # Create email identity for existing user
    identity = UserIdentity(
        user_id=test_user.id,
        provider="email",
        provider_subject=email,
        email=email,
    )
    db_session.add(identity)
    
    # Create valid token
    token = EmailLoginToken(
        email=email,
        token_hash=hash_token(code),
        expires_at=utc_now() + timedelta(minutes=10),
    )
    db_session.add(token)
    await db_session.commit()
    
    with patch(
        "app.services.email_auth_service.TokenService.create_tokens_for_user",
        new_callable=AsyncMock,
        return_value={
            "access_token": "test_access",
            "refresh_token": "test_refresh",
            "expires_in": 3600,
            "token_type": "bearer",
        },
    ):
        result = await EmailAuthService.verify_magic_link(
            db_session,
            token=code,
            email=email,
        )
    
    assert result["user"].id == test_user.id


@pytest.mark.asyncio
async def test_verify_magic_link_wrong_email(db_session):
    """Test that token with wrong email is rejected."""
    from app.core.security import generate_verification_code
    
    real_email = "real@example.com"
    wrong_email = "wrong@example.com"
    code = generate_verification_code()
    
    # Create token for real_email
    token = EmailLoginToken(
        email=real_email,
        token_hash=hash_token(code),
        expires_at=utc_now() + timedelta(minutes=10),
    )
    db_session.add(token)
    await db_session.commit()
    
    # Try to verify with wrong email
    with pytest.raises(ValueError, match="Invalid or expired token"):
        await EmailAuthService.verify_magic_link(
            db_session,
            token=code,
            email=wrong_email,
        )


@pytest.mark.asyncio
async def test_verify_magic_link_marks_token_used(db_session):
    """Test that verified token is marked as used."""
    from app.core.security import generate_verification_code
    
    email = "usedtoken@example.com"
    code = generate_verification_code()
    
    # Create valid token
    token = EmailLoginToken(
        email=email,
        token_hash=hash_token(code),
        expires_at=utc_now() + timedelta(minutes=10),
    )
    db_session.add(token)
    await db_session.commit()
    token_id = token.id
    
    with patch(
        "app.services.email_auth_service.TokenService.create_tokens_for_user",
        new_callable=AsyncMock,
        return_value={
            "access_token": "test_access",
            "refresh_token": "test_refresh",
            "expires_in": 3600,
            "token_type": "bearer",
        },
    ):
        await EmailAuthService.verify_magic_link(db_session, token=code, email=email)
    
    # Check token is marked as used
    await db_session.refresh(token)
    assert token.used_at is not None


@pytest.mark.asyncio
async def test_verify_magic_link_already_used_token(db_session):
    """Test that already used token is rejected."""
    from app.core.security import generate_verification_code
    
    email = "reused@example.com"
    code = generate_verification_code()
    
    # Create already-used token
    token = EmailLoginToken(
        email=email,
        token_hash=hash_token(code),
        expires_at=utc_now() + timedelta(minutes=10),
        used_at=utc_now(),  # Already used
    )
    db_session.add(token)
    await db_session.commit()
    
    with pytest.raises(ValueError, match="Invalid or expired token"):
        await EmailAuthService.verify_magic_link(db_session, token=code, email=email)
