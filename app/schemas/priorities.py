from decimal import Decimal
from pydantic import BaseModel


class PriorityRevisionResponse(BaseModel):
    id: str
    priority_id: str
    title: str
    body: str | None
    strength: Decimal
    is_anchored: bool
    is_active: bool
    notes: str | None
    created_at: str
    
    model_config = {"from_attributes": True}


class PriorityResponse(BaseModel):
    id: str
    user_id: str
    active_revision_id: str | None
    active_revision: PriorityRevisionResponse | None = None
    created_at: str
    updated_at: str
    
    model_config = {"from_attributes": True}


class CreatePriorityRequest(BaseModel):
    title: str
    body: str | None = None
    strength: Decimal = Decimal("1.0")
    is_anchored: bool = False
    notes: str | None = None


class CreatePriorityRevisionRequest(BaseModel):
    title: str
    body: str | None = None
    strength: Decimal = Decimal("1.0")
    is_anchored: bool = False
    notes: str | None = None


class PrioritiesListResponse(BaseModel):
    priorities: list[PriorityResponse]
