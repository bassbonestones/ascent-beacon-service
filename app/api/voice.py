from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.auth import CurrentUser
from app.models.stt_request import STTRequest
from app.services.stt_service import STTService
from app.schemas.voice import STTResponse
from app.core.config import settings

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/stt", response_model=STTResponse)
async def transcribe_audio(
    audio: UploadFile = File(...),
    user: CurrentUser = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
):
    """Transcribe audio to text (ephemeral, no audio stored)."""
    try:
        # Read audio bytes
        audio_bytes = await audio.read()
        
        # Determine format from filename
        format = "m4a"
        if audio.filename:
            if audio.filename.endswith(".wav"):
                format = "wav"
            elif audio.filename.endswith(".webm"):
                format = "webm"
            elif audio.filename.endswith(".mp3"):
                format = "mp3"
        
        # Transcribe
        result = await STTService.transcribe_audio(audio_bytes, format)
        
        # Optionally store request metadata (no audio)
        stt_request = STTRequest(
            user_id=user.id,
            provider=settings.stt_provider,
            model=settings.stt_model,
            status="transcribed",
            transcript=result["transcript"],
            confidence=result.get("confidence"),
        )
        db.add(stt_request)
        await db.commit()
        await db.refresh(stt_request)
        
        return STTResponse(
            transcript=result["transcript"],
            confidence=result.get("confidence"),
            stt_request_id=stt_request.id,
        )
        
    except Exception as e:
        # Log error
        if user and db:
            stt_request = STTRequest(
                user_id=user.id,
                provider=settings.stt_provider,
                model=settings.stt_model,
                status="failed",
                error_message=str(e),
            )
            db.add(stt_request)
            await db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {e}",
        )
