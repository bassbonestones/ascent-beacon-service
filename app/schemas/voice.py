from pydantic import BaseModel


class STTResponse(BaseModel):
    transcript: str
    confidence: float | None = None
    stt_request_id: str | None = None
