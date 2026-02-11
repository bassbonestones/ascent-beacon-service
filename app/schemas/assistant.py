from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class CreateSessionRequest(BaseModel):
    context_mode: Optional[str] = Field(None, description="Context mode for the session (e.g., 'values', 'priorities')")


class SendMessageRequest(BaseModel):
    content: str = Field(..., description="Message content", min_length=1, max_length=5000)
    input_modality: str = Field(default="text", description="Input modality: 'text' or 'voice'")


class TurnResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    role: str
    content: str
    created_at: datetime
    input_modality: str


class SessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    user_id: str
    context_mode: Optional[str] = None
    is_active: bool
    created_at: datetime
    turns: list[TurnResponse] = []


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    session_id: str
    role: str
    content: str
    created_at: datetime
    response: str  # The LLM's response text
    recommendation_id: Optional[str] = None  # ID of created recommendation, if any
