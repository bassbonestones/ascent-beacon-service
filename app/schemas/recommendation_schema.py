from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    session_id: str
    created_at: datetime
    status: str
    proposed_action: str
    payload: dict[str, Any]
    rationale: Optional[str] = None
    llm_provider: str
    llm_model: str
    result_entity_type: Optional[str] = None
    result_entity_id: Optional[str] = None


class AcceptRecommendationRequest(BaseModel):
    pass  # No additional data needed for now


class RejectRecommendationRequest(BaseModel):
    reason: Optional[str] = Field(None, description="Optional reason for rejection")
