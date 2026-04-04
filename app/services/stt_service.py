from typing import Any

import httpx

from app.core.config import settings


class STTService:
    """Service for speech-to-text transcription."""
    
    @staticmethod
    async def transcribe_audio(audio_bytes: bytes, format: str = "m4a") -> dict[str, Any]:
        """Transcribe audio using OpenAI Whisper API."""
        if not settings.stt_api_key:
            raise ValueError("STT API key not configured")
        
        # Prepare multipart form data
        files = {
            "file": (f"audio.{format}", audio_bytes, f"audio/{format}"),
        }
        
        data = {
            "model": settings.stt_model,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{settings.stt_base_url}/audio/transcriptions",
                headers={
                    "Authorization": f"Bearer {settings.stt_api_key}",
                },
                files=files,
                data=data,
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()
        
        return {
            "transcript": result.get("text", ""),
            "confidence": None,  # Whisper doesn't return confidence
        }
