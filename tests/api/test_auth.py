"""Tests for auth API endpoints."""

import pytest
from unittest.mock import patch, MagicMock
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.core.security import create_access_token, generate_random_token, hash_token
from app.core.time import utc_now
from datetime import timedelta


@pytest.mark.asyncio
async def test_onboarding_status_complete(client: AsyncClient, test_user: User):
    """Test onboarding status returns correctly for complete user."""
    response = await client.get("/auth/onboarding/status")
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["user"]["id"] == test_user.id
    assert "needs_display_name" in data
    assert "needs_email_verification" in data


@pytest.mark.asyncio
async def test_onboarding_status_needs_display_name(client: AsyncClient, db_session: AsyncSession, test_user: User):
    """Test onboarding status when user needs display name."""
    # Remove display name
    test_user.display_name = None
    await db_session.commit()
    
    response = await client.get("/auth/onboarding/status")
    
    assert response.status_code == 200
    data = response.json()
    assert data["needs_display_name"] is True


@pytest.mark.asyncio
async def test_set_display_name(client: AsyncClient, db_session: AsyncSession, test_user: User):
    """Test setting display name during onboarding."""
    test_user.display_name = None
    await db_session.commit()
    
    response = await client.post(
        "/auth/onboarding/display-name",
        json={"display_name": "New Display Name"},
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "New Display Name"


@pytest.mark.asyncio
async def test_refresh_token(db_session: AsyncSession, test_user: User):
    """Test refreshing an access token."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    # Create a refresh token directly in the database
    refresh_token = generate_random_token()
    refresh_record = RefreshToken(
        user_id=test_user.id,
        token_hash=hash_token(refresh_token),
        expires_at=utc_now() + timedelta(days=7),
        device_id="test-device",
        device_name="Test Device",
    )
    db_session.add(refresh_record)
    await db_session.commit()
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/auth/refresh",
            json={"refresh_token": refresh_token},
        )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_refresh_token_invalid(db_session: AsyncSession):
    """Test refreshing with invalid token fails."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/auth/refresh",
            json={"refresh_token": "invalid-token-that-does-not-exist"},
        )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout(db_session: AsyncSession, test_user: User):
    """Test logging out revokes refresh token."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    # Create a refresh token
    refresh_token = generate_random_token()
    refresh_record = RefreshToken(
        user_id=test_user.id,
        token_hash=hash_token(refresh_token),
        expires_at=utc_now() + timedelta(days=7),
        device_id="test-device",
        device_name="Test Device",
    )
    db_session.add(refresh_record)
    await db_session.commit()
    token_id = refresh_record.id
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    access_token = create_access_token(user_id=test_user.id)
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {access_token}"},
    ) as client:
        response = await client.post(
            "/auth/logout",
            json={"refresh_token": refresh_token},
        )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    assert response.json()["ok"] is True
    
    # Verify token is revoked (revoked_at should be set)
    await db_session.refresh(refresh_record)
    assert refresh_record.revoked_at is not None


@pytest.mark.asyncio
async def test_update_email(client: AsyncClient, test_user: User):
    """Test updating user email (creates verification token)."""
    response = await client.post(
        "/auth/onboarding/email",
        json={"primary_email": "newemail@example.com"},
    )
    
    assert response.status_code == 200
    data = response.json()
    # Email should be updated
    assert data["primary_email"] == "newemail@example.com"


@pytest.mark.asyncio
async def test_dev_login(db_session: AsyncSession):
    """Test dev login works when env is local."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Mock settings to enable dev login
    with patch("app.api.auth.settings") as mock_settings:
        mock_settings.env = "local"
        mock_settings.refresh_token_ttl_minutes = 60 * 24 * 7
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/auth/dev-login")
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


@pytest.mark.asyncio
async def test_dev_login_not_local(db_session: AsyncSession):
    """Test dev login fails when not in local environment."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    # Mock settings to not be local
    with patch("app.api.auth.settings") as mock_settings:
        mock_settings.env = "production"
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post("/auth/dev-login")
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_fails():
    """Test that endpoints requiring auth fail without token."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/auth/onboarding/status")
    
    # Can be 401 (Unauthorized) or 403 (Forbidden) depending on implementation
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_google_login_new_user(db_session: AsyncSession):
    """Test Google login creates new user."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    with patch("app.services.auth_service.ProviderAuthService.verify_google_token") as mock:
        mock.return_value = {
            "sub": "google-user-123",
            "email": "newgoogleuser@example.com",
            "email_verified": True,
        }
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/auth/google",
                json={"id_token": "fake-google-token"},
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["user"]["primary_email"] == "newgoogleuser@example.com"


@pytest.mark.asyncio
async def test_google_login_existing_user(db_session: AsyncSession, test_user: User):
    """Test Google login returns existing user."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    from app.models.user_identity import UserIdentity
    
    # Create an identity for the test user
    identity = UserIdentity(
        user_id=test_user.id,
        provider="google",
        provider_subject="google-existing-123",
        email=test_user.primary_email,
    )
    db_session.add(identity)
    await db_session.commit()
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    with patch("app.services.auth_service.ProviderAuthService.verify_google_token") as mock:
        mock.return_value = {
            "sub": "google-existing-123",
            "email": test_user.primary_email,
            "email_verified": True,
        }
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/auth/google",
                json={"id_token": "fake-google-token"},
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    assert data["user"]["id"] == test_user.id


@pytest.mark.asyncio
async def test_google_login_invalid_token(db_session: AsyncSession):
    """Test Google login fails with invalid token."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    with patch("app.services.auth_service.ProviderAuthService.verify_google_token") as mock:
        mock.side_effect = ValueError("Invalid token")
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/auth/google",
                json={"id_token": "invalid-token"},
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_google_login_unverified_email(db_session: AsyncSession):
    """Test Google login handles unverified email."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    with patch("app.services.auth_service.ProviderAuthService.verify_google_token") as mock:
        mock.return_value = {
            "sub": "google-unverified-user",
            "email": "unverified@example.com",
            "email_verified": False,  # Email not verified
        }
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/auth/google",
                json={"id_token": "fake-google-token"},
            )
    
    app.dependency_overrides.clear()
    
    # Should still succeed but potentially without email
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_apple_login(db_session: AsyncSession):
    """Test Apple authentication endpoint."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    with patch("app.services.auth_service.AuthService.authenticate_with_apple") as mock:
        mock.return_value = {
            "access_token": "fake-access-token",
            "refresh_token": "fake-refresh-token",
            "user": MagicMock(
                id="user-123",
                display_name="Apple User",
                primary_email="apple@example.com",
                is_email_verified=True,
                created_at=utc_now(),
                updated_at=utc_now(),
            ),
        }
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/auth/apple",
                json={"id_token": "fake-apple-token"},
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_apple_login_invalid_token(db_session: AsyncSession):
    """Test Apple authentication with invalid token."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    with patch("app.services.auth_service.AuthService.authenticate_with_apple") as mock:
        mock.side_effect = ValueError("Invalid Apple token")
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/auth/apple",
                json={"id_token": "invalid-token"},
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_request_magic_link(db_session: AsyncSession):
    """Test requesting a magic link."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    with patch("app.services.auth_service.AuthService.request_magic_link") as mock:
        mock.return_value = None  # Method returns nothing
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/auth/email/request",
                json={"email": "test@example.com"},
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    assert response.json()["ok"] is True


@pytest.mark.asyncio
async def test_verify_magic_link(db_session: AsyncSession):
    """Test verifying a magic link."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    with patch("app.services.auth_service.AuthService.verify_magic_link") as mock:
        mock.return_value = {
            "access_token": "fake-access-token",
            "refresh_token": "fake-refresh-token",
            "user": MagicMock(
                id="user-123",
                display_name="Email User",
                primary_email="test@example.com",
                is_email_verified=True,
                created_at=utc_now(),
                updated_at=utc_now(),
            ),
        }
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/auth/email/verify",
                json={"token": "magic-token", "email": "test@example.com"},
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data


@pytest.mark.asyncio
async def test_verify_magic_link_invalid(db_session: AsyncSession):
    """Test verifying invalid magic link."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    with patch("app.services.auth_service.AuthService.verify_magic_link") as mock:
        mock.side_effect = ValueError("Invalid or expired token")
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/auth/email/verify",
                json={"token": "invalid-token", "email": "test@example.com"},
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_invalid_token(db_session: AsyncSession, test_user: User):
    """Test logout with invalid refresh token."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    access_token = create_access_token(user_id=test_user.id)
    
    with patch("app.services.auth_service.AuthService.logout") as mock:
        mock.side_effect = ValueError("Invalid token")
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {access_token}"},
        ) as client:
            response = await client.post(
                "/auth/logout",
                json={"refresh_token": "invalid-refresh-token"},
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_set_display_name_error(db_session: AsyncSession, test_user: User):
    """Test setting display name with error."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    access_token = create_access_token(user_id=test_user.id)
    
    with patch("app.services.auth_service.AuthService.update_display_name") as mock:
        mock.side_effect = ValueError("Invalid display name")
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {access_token}"},
        ) as client:
            response = await client.post(
                "/auth/onboarding/display-name",
                json={"display_name": ""},
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_update_email_error(db_session: AsyncSession, test_user: User):
    """Test updating email with error."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    access_token = create_access_token(user_id=test_user.id)
    
    with patch("app.services.auth_service.AuthService.update_and_verify_email") as mock:
        mock.side_effect = ValueError("Email already in use")
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {access_token}"},
        ) as client:
            response = await client.post(
                "/auth/onboarding/email",
                json={"primary_email": "taken@example.com"},
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_verify_onboarding_email(db_session: AsyncSession, test_user: User):
    """Test verifying email during onboarding."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    access_token = create_access_token(user_id=test_user.id)
    
    with patch("app.services.auth_service.AuthService.verify_onboarding_email") as mock:
        mock.return_value = test_user
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {access_token}"},
        ) as client:
            response = await client.post(
                "/auth/onboarding/verify-email",
                json={"token": "verification-token", "email": test_user.primary_email},
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_verify_onboarding_email_error(db_session: AsyncSession, test_user: User):
    """Test verifying email during onboarding with invalid token."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.core.db import get_db
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    access_token = create_access_token(user_id=test_user.id)
    
    with patch("app.services.auth_service.AuthService.verify_onboarding_email") as mock:
        mock.side_effect = ValueError("Invalid verification token")
        
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {access_token}"},
        ) as client:
            response = await client.post(
                "/auth/onboarding/verify-email",
                json={"token": "invalid-token", "email": test_user.primary_email},
            )
    
    app.dependency_overrides.clear()
    
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient, test_user: User):
    """Test getting current authenticated user via /me endpoint."""
    response = await client.get("/me")
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user.id


# ============================================================================
# Refresh Token Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_auth_refresh_with_malformed_token(unauthenticated_client: AsyncClient):
    """Test refresh endpoint with malformed token."""
    response = await unauthenticated_client.post(
        "/auth/refresh",
        json={"refresh_token": "not.a.valid.jwt.token"},
    )
    assert response.status_code in [401, 422]


@pytest.mark.asyncio
async def test_refresh_token_invalid_rejects_unauthenticated_client_request(unauthenticated_client: AsyncClient):
    """Test refresh token with invalid token."""
    response = await unauthenticated_client.post(
        "/auth/refresh",
        json={"refresh_token": "invalid-token"},
    )
    # Should fail with 401 or similar
    assert response.status_code in [401, 422]


# ---- migrated from tests/mocked/test_pure_functions_services_auth_migrated.py ----

"""Migrated pure-function service auth/security tests."""

from tests.core.test_security import *  # noqa: F403


# ---- migrated from tests/mocked/test_services_auth_migrated.py ----

"""Migrated auth service tests split from mixed services file."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_invalid_refresh_token(client: AsyncClient):
    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": "invalid_token_here"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_logout_invalid_token(client: AsyncClient):
    response = await client.post(
        "/auth/logout",
        json={"refresh_token": "invalid_token"},
    )
    assert response.status_code == 401


# ---- migrated from tests/mocked/test_services_external_auth.py ----

"""Auth API error scenarios."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_auth_invalid_refresh_token__legacyservices_external_auth(client: AsyncClient):
    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": "invalid_token_here"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_logout_invalid_token__legacyservices_external_auth(client: AsyncClient):
    response = await client.post(
        "/auth/logout",
        json={"refresh_token": "invalid_token"},
    )
    assert response.status_code == 401
