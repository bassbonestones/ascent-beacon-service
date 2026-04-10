"""Tests for provider_auth service with mocked JWT validation."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from app.services.provider_auth import ProviderAuthService


# ============================================================================
# verify_google_token Tests
# ============================================================================


@pytest.mark.asyncio
async def test_verify_google_token_success():
    """Test successful Google token verification."""
    mock_signing_key = MagicMock()
    mock_signing_key.key = "mock_key"
    
    expected_payload = {
        "sub": "google_user_123",
        "email": "user@gmail.com",
        "email_verified": True,
    }
    
    with patch("app.services.provider_auth.settings") as mock_settings:
        mock_settings.google_client_ids = "client_id_1,client_id_2"
        
        with patch("app.services.provider_auth.PyJWKClient") as mock_jwks:
            mock_jwks_instance = MagicMock()
            mock_jwks_instance.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_jwks.return_value = mock_jwks_instance
            
            with patch("app.services.provider_auth.jwt.decode") as mock_decode:
                mock_decode.return_value = expected_payload
                
                result = await ProviderAuthService.verify_google_token("fake_token")
                
                assert result["sub"] == "google_user_123"
                assert result["email"] == "user@gmail.com"
                assert result["email_verified"] is True


@pytest.mark.asyncio
async def test_verify_google_token_no_client_ids():
    """Test that missing client IDs raises ValueError."""
    with patch("app.services.provider_auth.settings") as mock_settings:
        mock_settings.google_client_ids = ""
        
        with pytest.raises(ValueError, match="Google client IDs are not configured"):
            await ProviderAuthService.verify_google_token("fake_token")


@pytest.mark.asyncio
async def test_verify_google_token_no_client_ids_none():
    """Test that None client IDs raises ValueError."""
    with patch("app.services.provider_auth.settings") as mock_settings:
        mock_settings.google_client_ids = None
        
        with pytest.raises(ValueError, match="Invalid Google token"):
            await ProviderAuthService.verify_google_token("fake_token")


@pytest.mark.asyncio
async def test_verify_google_token_invalid_token():
    """Test that invalid token raises ValueError."""
    with patch("app.services.provider_auth.settings") as mock_settings:
        mock_settings.google_client_ids = "client_id_1"
        
        with patch("app.services.provider_auth.PyJWKClient") as mock_jwks:
            mock_jwks_instance = MagicMock()
            mock_jwks_instance.get_signing_key_from_jwt.side_effect = Exception("Invalid JWT")
            mock_jwks.return_value = mock_jwks_instance
            
            with pytest.raises(ValueError, match="Invalid Google token"):
                await ProviderAuthService.verify_google_token("invalid_token")


@pytest.mark.asyncio
async def test_verify_google_token_no_email():
    """Test Google token without email field."""
    mock_signing_key = MagicMock()
    mock_signing_key.key = "mock_key"
    
    expected_payload = {
        "sub": "google_user_456",
    }
    
    with patch("app.services.provider_auth.settings") as mock_settings:
        mock_settings.google_client_ids = "client_id_1"
        
        with patch("app.services.provider_auth.PyJWKClient") as mock_jwks:
            mock_jwks_instance = MagicMock()
            mock_jwks_instance.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_jwks.return_value = mock_jwks_instance
            
            with patch("app.services.provider_auth.jwt.decode") as mock_decode:
                mock_decode.return_value = expected_payload
                
                result = await ProviderAuthService.verify_google_token("fake_token")
                
                assert result["sub"] == "google_user_456"
                assert result["email"] is None
                assert result["email_verified"] is False


# ============================================================================
# verify_apple_token Tests
# ============================================================================


@pytest.mark.asyncio
async def test_verify_apple_token_success():
    """Test successful Apple token verification."""
    mock_signing_key = MagicMock()
    mock_signing_key.key = "mock_apple_key"
    
    expected_payload = {
        "sub": "apple_user_123",
        "email": "user@privaterelay.appleid.com",
        "email_verified": True,  # Bool value
    }
    
    with patch("app.services.provider_auth.settings") as mock_settings:
        mock_settings.apple_audience = "com.test.app"
        mock_settings.apple_issuer = "https://appleid.apple.com"
        
        with patch("app.services.provider_auth.PyJWKClient") as mock_jwks:
            mock_jwks_instance = MagicMock()
            mock_jwks_instance.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_jwks.return_value = mock_jwks_instance
            
            with patch("app.services.provider_auth.jwt.decode") as mock_decode:
                mock_decode.return_value = expected_payload
                
                result = await ProviderAuthService.verify_apple_token("fake_token")
                
                assert result["sub"] == "apple_user_123"
                assert result["email"] == "user@privaterelay.appleid.com"
                assert result["email_verified"] is True


@pytest.mark.asyncio
async def test_verify_apple_token_invalid():
    """Test that invalid Apple token raises ValueError."""
    with patch("app.services.provider_auth.settings") as mock_settings:
        mock_settings.apple_audience = "com.test.app"
        mock_settings.apple_issuer = "https://appleid.apple.com"
        
        with patch("app.services.provider_auth.PyJWKClient") as mock_jwks:
            mock_jwks_instance = MagicMock()
            mock_jwks_instance.get_signing_key_from_jwt.side_effect = Exception("Invalid JWT")
            mock_jwks.return_value = mock_jwks_instance
            
            with pytest.raises(ValueError, match="Invalid Apple token"):
                await ProviderAuthService.verify_apple_token("invalid_token")


@pytest.mark.asyncio
async def test_verify_apple_token_email_verified_string():
    """Test Apple token with email_verified as string 'true' is passed through."""
    mock_signing_key = MagicMock()
    mock_signing_key.key = "mock_apple_key"
    
    expected_payload = {
        "sub": "apple_user_789",
        "email": "user@icloud.com",
        "email_verified": "true",  # String from Apple
    }
    
    with patch("app.services.provider_auth.settings") as mock_settings:
        mock_settings.apple_audience = "com.test.app"
        mock_settings.apple_issuer = "https://appleid.apple.com"
        
        with patch("app.services.provider_auth.PyJWKClient") as mock_jwks:
            mock_jwks_instance = MagicMock()
            mock_jwks_instance.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_jwks.return_value = mock_jwks_instance
            
            with patch("app.services.provider_auth.jwt.decode") as mock_decode:
                mock_decode.return_value = expected_payload
                
                result = await ProviderAuthService.verify_apple_token("fake_token")
                
                # Service returns the raw value from payload
                assert result["email_verified"] == "true"


@pytest.mark.asyncio
async def test_verify_apple_token_no_email():
    """Test Apple token without email field."""
    mock_signing_key = MagicMock()
    mock_signing_key.key = "mock_apple_key"
    
    expected_payload = {
        "sub": "apple_user_no_email",
    }
    
    with patch("app.services.provider_auth.settings") as mock_settings:
        mock_settings.apple_audience = "com.test.app"
        mock_settings.apple_issuer = "https://appleid.apple.com"
        
        with patch("app.services.provider_auth.PyJWKClient") as mock_jwks:
            mock_jwks_instance = MagicMock()
            mock_jwks_instance.get_signing_key_from_jwt.return_value = mock_signing_key
            mock_jwks.return_value = mock_jwks_instance
            
            with patch("app.services.provider_auth.jwt.decode") as mock_decode:
                mock_decode.return_value = expected_payload
                
                result = await ProviderAuthService.verify_apple_token("fake_token")
                
                assert result["sub"] == "apple_user_no_email"
                assert result["email"] is None
                assert result["email_verified"] is False
