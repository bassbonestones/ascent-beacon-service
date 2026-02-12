from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, Field


class PriorityValueLinkInfo(BaseModel):
    """Info about a linked value in a priority revision."""
    value_id: str
    value_revision_id: str
    link_weight: Decimal = Decimal("1.0")
    
    model_config = {"from_attributes": True}


class PriorityRevisionResponse(BaseModel):
    id: str
    priority_id: str
    title: str
    why_matters: str
    score: int = Field(ge=1, le=5)
    scope: str  # 'ongoing', 'in_progress', 'habitual', 'seasonal'
    cadence: str | None = None
    constraints: str | None = None
    is_anchored: bool
    is_active: bool
    notes: str | None = None
    created_at: datetime
    value_links: list[PriorityValueLinkInfo] = []
    
    model_config = {"from_attributes": True}


class PriorityResponse(BaseModel):
    id: str
    user_id: str
    active_revision_id: str | None = None
    active_revision: PriorityRevisionResponse | None = None
    created_at: datetime
    updated_at: datetime
    
    model_config = {"from_attributes": True}


class CreatePriorityRequest(BaseModel):
    """Request to create a new priority (first revision)."""
    title: str = Field(min_length=1)
    why_matters: str = Field(min_length=20)
    score: int = Field(ge=1, le=5, default=3)
    scope: str = Field(default="ongoing")  # 'ongoing', 'in_progress', 'habitual', 'seasonal'
    cadence: str | None = None
    constraints: str | None = None
    notes: str | None = None
    value_ids: list[str] = []  # Values this priority supports


class CreatePriorityRevisionRequest(BaseModel):
    """Request to create a new revision of a priority."""
    title: str = Field(min_length=1)
    why_matters: str = Field(min_length=20)
    score: int = Field(ge=1, le=5, default=3)
    scope: str = Field(default="ongoing")
    cadence: str | None = None
    constraints: str | None = None
    notes: str | None = None
    value_ids: list[str] = []  # Values this priority supports


class PrioritiesListResponse(BaseModel):
    priorities: list[PriorityResponse]


class ValidatePriorityRequest(BaseModel):
    """Request to validate a priority name and why statement."""
    name: str = Field(min_length=1)
    why_statement: str = Field(min_length=20)


class RuleExample(BaseModel):
    """Example for a single validation rule."""
    rule_name: str
    rule_title: str
    good_examples: list[str]
    bad_examples: list[str]


class ValidatePriorityResponse(BaseModel):
    """Validation response for a priority."""
    name_valid: bool
    why_valid: bool
    name_feedback: list[str]
    why_feedback: list[str]
    why_passed_rules: dict[str, bool]
    rule_examples: dict[str, RuleExample] | None = None  # Examples for failed rules
    overall_valid: bool
