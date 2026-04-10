"""Tests for voice API endpoints."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from io import BytesIO
from httpx import AsyncClient

from app.models.user import User


# ============================================================================
# Transcribe Audio Tests
# ============================================================================


@pytest.mark.asyncio
async def test_transcribe_audio_success(client: AsyncClient):
    """Test successful audio transcription."""
    # Create fake audio file
    audio_content = b"fake audio content"
    
    mock_result = {
        "transcript": "Hello, this is a test.",
        "confidence": 0.95,
    }
    
    with patch(
        "app.api.voice.STTService.transcribe_audio",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        response = await client.post(
            "/voice/stt",
            files={"audio": ("test.m4a", BytesIO(audio_content), "audio/mp4")},
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] == "Hello, this is a test."
    assert data["confidence"] == 0.95


@pytest.mark.asyncio
async def test_transcribe_audio_wav_format(client: AsyncClient):
    """Test transcription with WAV format."""
    audio_content = b"fake wav content"
    
    mock_result = {
        "transcript": "WAV audio test",
        "confidence": 0.90,
    }
    
    with patch(
        "app.api.voice.STTService.transcribe_audio",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        response = await client.post(
            "/voice/stt",
            files={"audio": ("recording.wav", BytesIO(audio_content), "audio/wav")},
        )
    
    assert response.status_code == 200
    assert response.json()["transcript"] == "WAV audio test"


@pytest.mark.asyncio
async def test_transcribe_audio_mp3_format(client: AsyncClient):
    """Test transcription with MP3 format."""
    audio_content = b"fake mp3 content"
    
    mock_result = {
        "transcript": "MP3 audio test",
    }
    
    with patch(
        "app.api.voice.STTService.transcribe_audio",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        response = await client.post(
            "/voice/stt",
            files={"audio": ("recording.mp3", BytesIO(audio_content), "audio/mpeg")},
        )
    
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_transcribe_audio_webm_format(client: AsyncClient):
    """Test transcription with WebM format."""
    audio_content = b"fake webm content"
    
    mock_result = {
        "transcript": "WebM audio test",
    }
    
    with patch(
        "app.api.voice.STTService.transcribe_audio",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        response = await client.post(
            "/voice/stt",
            files={"audio": ("recording.webm", BytesIO(audio_content), "audio/webm")},
        )
    
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_transcribe_audio_empty_transcript(client: AsyncClient):
    """Test transcription that returns empty transcript."""
    audio_content = b"silent audio"
    
    mock_result = {
        "transcript": "",
        "confidence": 0.0,
    }
    
    with patch(
        "app.api.voice.STTService.transcribe_audio",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        response = await client.post(
            "/voice/stt",
            files={"audio": ("silent.m4a", BytesIO(audio_content), "audio/mp4")},
        )
    
    assert response.status_code == 200
    assert response.json()["transcript"] == ""


@pytest.mark.asyncio
async def test_transcribe_audio_no_confidence(client: AsyncClient):
    """Test transcription without confidence score."""
    audio_content = b"audio data"
    
    mock_result = {
        "transcript": "Test without confidence",
    }
    
    with patch(
        "app.api.voice.STTService.transcribe_audio",
        new_callable=AsyncMock,
        return_value=mock_result,
    ):
        response = await client.post(
            "/voice/stt",
            files={"audio": ("test.m4a", BytesIO(audio_content), "audio/mp4")},
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["transcript"] == "Test without confidence"


@pytest.mark.asyncio
async def test_transcribe_audio_service_error(client: AsyncClient):
    """Test handling of STT service error."""
    audio_content = b"problematic audio"
    
    with patch(
        "app.api.voice.STTService.transcribe_audio",
        new_callable=AsyncMock,
        side_effect=Exception("STT service unavailable"),
    ):
        response = await client.post(
            "/voice/stt",
            files={"audio": ("test.m4a", BytesIO(audio_content), "audio/mp4")},
        )
    
    # Should return 500 error
    assert response.status_code == 500
