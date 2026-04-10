"""Tests for email service with mocked HTTP calls."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from app.services.email_service import EmailService


# ============================================================================
# send_magic_link Tests
# ============================================================================


@pytest.mark.asyncio
async def test_send_magic_link_no_api_key():
    """Test that magic link is logged when no API key is set."""
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.resend_api_key = None
        mock_settings.magic_link_base_url = "https://test.com"
        
        with patch("app.services.email_service.logger") as mock_logger:
            await EmailService.send_magic_link("user@test.com", "abc123")
            mock_logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_send_magic_link_non_verified_email():
    """Test that magic link is logged for non-verified emails."""
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.resend_api_key = "test_key"
        mock_settings.magic_link_base_url = "https://test.com"
        
        with patch("app.services.email_service.logger") as mock_logger:
            await EmailService.send_magic_link("other@test.com", "abc123")
            mock_logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_send_magic_link_success():
    """Test successful magic link email sending."""
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.raise_for_status = MagicMock()
    
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.resend_api_key = "test_key"
        mock_settings.magic_link_base_url = "https://test.com"
        mock_settings.magic_link_from = "Test <test@test.com>"
        mock_settings.magic_link_ttl_minutes = 15
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            await EmailService.send_magic_link("jeremiah.stones@gmail.com", "token123")
            
            mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_send_magic_link_api_error():
    """Test handling of Resend API error."""
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.status_code = 400
    mock_response.json.return_value = {"error": "Bad request"}
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Bad request", request=MagicMock(), response=mock_response
    )
    
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.resend_api_key = "test_key"
        mock_settings.magic_link_base_url = "https://test.com"
        mock_settings.magic_link_from = "Test <test@test.com>"
        mock_settings.magic_link_ttl_minutes = 15
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            with patch("app.services.email_service.logger"):
                with pytest.raises(httpx.HTTPStatusError):
                    await EmailService.send_magic_link("jeremiah.stones@gmail.com", "token123")


@pytest.mark.asyncio
async def test_send_magic_link_api_error_text_response():
    """Test handling of API error with text (non-JSON) response."""
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.status_code = 500
    mock_response.json.side_effect = ValueError("Not JSON")
    mock_response.text = "Internal Server Error"
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Server error", request=MagicMock(), response=mock_response
    )
    
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.resend_api_key = "test_key"
        mock_settings.magic_link_base_url = "https://test.com"
        mock_settings.magic_link_from = "Test <test@test.com>"
        mock_settings.magic_link_ttl_minutes = 15
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            with patch("app.services.email_service.logger"):
                with pytest.raises(httpx.HTTPStatusError):
                    await EmailService.send_magic_link("jeremiah.stones@gmail.com", "token123")


# ============================================================================
# send_verification_code Tests
# ============================================================================


@pytest.mark.asyncio
async def test_send_verification_code_no_api_key():
    """Test that verification code is logged when no API key is set."""
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.resend_api_key = None
        
        with patch("app.services.email_service.logger") as mock_logger:
            await EmailService.send_verification_code("user@test.com", "123456")
            mock_logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_send_verification_code_non_verified_email():
    """Test that verification code is logged for non-verified emails."""
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.resend_api_key = "test_key"
        
        with patch("app.services.email_service.logger") as mock_logger:
            await EmailService.send_verification_code("other@test.com", "123456")
            mock_logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_send_verification_code_success():
    """Test successful verification code email sending."""
    mock_response = MagicMock()
    mock_response.is_success = True
    mock_response.raise_for_status = MagicMock()
    
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.resend_api_key = "test_key"
        mock_settings.magic_link_from = "Test <test@test.com>"
        mock_settings.magic_link_ttl_minutes = 15
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            await EmailService.send_verification_code("jeremiah.stones@gmail.com", "123456")
            
            mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_send_verification_code_api_error():
    """Test handling of Resend API error for verification code."""
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.status_code = 429
    mock_response.json.return_value = {"error": "Rate limited"}
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "Rate limited", request=MagicMock(), response=mock_response
    )
    
    with patch("app.services.email_service.settings") as mock_settings:
        mock_settings.resend_api_key = "test_key"
        mock_settings.magic_link_from = "Test <test@test.com>"
        mock_settings.magic_link_ttl_minutes = 15
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            with patch("app.services.email_service.logger"):
                with pytest.raises(httpx.HTTPStatusError):
                    await EmailService.send_verification_code("jeremiah.stones@gmail.com", "123456")


@pytest.mark.asyncio
async def test_email_service_api_error_handling():
    """Test email service handles API errors gracefully when JSON is invalid."""
    mock_response = MagicMock()
    mock_response.is_success = False
    mock_response.status_code = 500
    mock_response.json.side_effect = ValueError("Invalid JSON")
    mock_response.text = "Internal Server Error"
    
    with patch("app.services.email_service.httpx.AsyncClient") as mock_client:
        mock_instance = AsyncMock()
        mock_instance.post.return_value = mock_response
        mock_instance.__aenter__.return_value = mock_instance
        mock_instance.__aexit__.return_value = None
        mock_client.return_value = mock_instance
        
        # Should not raise, just log the error
        await EmailService.send_magic_link("test@example.com", "http://test.com")
