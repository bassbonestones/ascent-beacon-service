"""Tests for STT service with mocked HTTP calls."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import httpx

from app.services.stt_service import STTService


# ============================================================================
# transcribe_audio Tests
# ============================================================================


@pytest.mark.asyncio
async def test_transcribe_audio_no_api_key():
    """Test that missing API key raises ValueError."""
    with patch("app.services.stt_service.settings") as mock_settings:
        mock_settings.stt_api_key = None
        
        with pytest.raises(ValueError, match="STT API key not configured"):
            await STTService.transcribe_audio(b"fake audio")


@pytest.mark.asyncio
async def test_transcribe_audio_empty_api_key():
    """Test that empty API key raises ValueError."""
    with patch("app.services.stt_service.settings") as mock_settings:
        mock_settings.stt_api_key = ""
        
        with pytest.raises(ValueError, match="STT API key not configured"):
            await STTService.transcribe_audio(b"fake audio")


@pytest.mark.asyncio
async def test_transcribe_audio_success():
    """Test successful audio transcription."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"text": "Hello, world!"}
    
    with patch("app.services.stt_service.settings") as mock_settings:
        mock_settings.stt_api_key = "test_api_key"
        mock_settings.stt_model = "whisper-1"
        mock_settings.stt_base_url = "https://api.openai.com/v1"
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            result = await STTService.transcribe_audio(b"audio data")
            
            assert result["transcript"] == "Hello, world!"
            assert result["confidence"] is None
            mock_post.assert_called_once()


@pytest.mark.asyncio
async def test_transcribe_audio_with_wav_format():
    """Test transcription with WAV format."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"text": "WAV transcription"}
    
    with patch("app.services.stt_service.settings") as mock_settings:
        mock_settings.stt_api_key = "test_key"
        mock_settings.stt_model = "whisper-1"
        mock_settings.stt_base_url = "https://api.openai.com/v1"
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            result = await STTService.transcribe_audio(b"wav data", format="wav")
            
            assert result["transcript"] == "WAV transcription"


@pytest.mark.asyncio
async def test_transcribe_audio_empty_result():
    """Test transcription that returns empty text."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {}  # No "text" field
    
    with patch("app.services.stt_service.settings") as mock_settings:
        mock_settings.stt_api_key = "test_key"
        mock_settings.stt_model = "whisper-1"
        mock_settings.stt_base_url = "https://api.openai.com/v1"
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            result = await STTService.transcribe_audio(b"silent audio")
            
            assert result["transcript"] == ""


@pytest.mark.asyncio
async def test_transcribe_audio_api_error():
    """Test handling of API error."""
    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "API error", request=MagicMock(), response=mock_response
    )
    
    with patch("app.services.stt_service.settings") as mock_settings:
        mock_settings.stt_api_key = "test_key"
        mock_settings.stt_model = "whisper-1"
        mock_settings.stt_base_url = "https://api.openai.com/v1"
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            with pytest.raises(httpx.HTTPStatusError):
                await STTService.transcribe_audio(b"audio data")


@pytest.mark.asyncio
async def test_transcribe_audio_mp3_format():
    """Test transcription with MP3 format."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"text": "MP3 transcription"}
    
    with patch("app.services.stt_service.settings") as mock_settings:
        mock_settings.stt_api_key = "test_key"
        mock_settings.stt_model = "whisper-1"
        mock_settings.stt_base_url = "https://api.openai.com/v1"
        
        with patch("httpx.AsyncClient") as mock_client:
            mock_post = AsyncMock(return_value=mock_response)
            mock_client.return_value.__aenter__.return_value.post = mock_post
            
            result = await STTService.transcribe_audio(b"mp3 data", format="mp3")
            
            assert result["transcript"] == "MP3 transcription"
