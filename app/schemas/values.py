from decimal import Decimal
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, computed_field, model_validator


class ValueRevisionResponse(BaseModel):
    id: str
    value_id: str
    statement: str
    weight_raw: Decimal
    weight_normalized: Decimal | None
    is_active: bool
    origin: str
    created_at: datetime
    
    model_config = {"from_attributes": True}


class ValueInsight(BaseModel):
    type: str
    message: str
    similar_value_id: Optional[str] = None
    similar_value_revision_id: Optional[str] = None
    similarity_score: Optional[float] = None


class ValueResponse(BaseModel):
    id: str
    user_id: str
    active_revision_id: str | None
    created_at: datetime
    updated_at: datetime
    revisions: list[ValueRevisionResponse] = []
    insights: list[ValueInsight] = []
    
    @computed_field
    @property
    def active_revision(self) -> ValueRevisionResponse | None:
        """Get the active revision from the revisions list."""
        if not self.active_revision_id:
            return None
        for rev in self.revisions:
            if rev.id == self.active_revision_id:
                return rev
        return None
    
    model_config = {"from_attributes": True}


class CreateValueRequest(BaseModel):
    statement: str
    weight_raw: Decimal
    origin: str = "declared"


class CreateValueRevisionRequest(BaseModel):
    statement: str
    weight_raw: Decimal
    origin: str = "declared"


class AcknowledgeValueInsightRequest(BaseModel):
    revision_id: Optional[str] = None


class ValuesListResponse(BaseModel):
    values: list[ValueResponse]


class ValueMatchRequest(BaseModel):
    query: str


class ValueMatchResponse(BaseModel):
    value_id: Optional[str] = None
