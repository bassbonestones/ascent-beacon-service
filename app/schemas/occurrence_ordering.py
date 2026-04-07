"""
Pydantic schemas for occurrence ordering API.
Used for reordering untimed tasks in Today/Upcoming views.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Type Aliases
# ============================================================================

SaveMode = Literal["today", "permanent"]


# ============================================================================
# Request Schemas
# ============================================================================


class OccurrenceItem(BaseModel):
    """Single occurrence in the reorder request."""

    task_id: str = Field(description="Task ID")
    occurrence_index: int = Field(
        default=0,
        ge=0,
        description="Occurrence index for multi-per-day tasks (0 for single)",
    )


class ReorderOccurrencesRequest(BaseModel):
    """Request to reorder task occurrences for a day."""

    date: str = Field(
        description="Date to reorder (YYYY-MM-DD format)",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
    )
    occurrences: list[OccurrenceItem] = Field(
        description="Ordered list of occurrences (first = position 1, etc.)",
        min_length=1,
    )
    save_mode: SaveMode = Field(
        description="'today' for one-time override, 'permanent' for persistent preference",
    )


# ============================================================================
# Response Schemas
# ============================================================================


class OccurrencePreferenceResponse(BaseModel):
    """Response for a single occurrence preference."""

    id: str
    task_id: str
    occurrence_index: int
    sequence_number: float
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DailySortOverrideResponse(BaseModel):
    """Response for a single daily sort override."""

    id: str
    task_id: str
    occurrence_index: int
    override_date: str
    sort_position: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ReorderOccurrencesResponse(BaseModel):
    """Response from reordering occurrences."""

    message: str = Field(default="Occurrences reordered successfully")
    save_mode: SaveMode
    date: str
    count: int = Field(description="Number of occurrences reordered")


class DayOrderItem(BaseModel):
    """Single task occurrence with its sort info for a given day."""

    task_id: str
    occurrence_index: int
    sort_value: float = Field(
        description="Effective sort value (from override or preference)"
    )
    is_override: bool = Field(
        description="True if from daily_sort_overrides, False if from occurrence_preferences"
    )


class DayOrderResponse(BaseModel):
    """Response with ordered occurrences for a specific day."""

    date: str
    items: list[DayOrderItem]
    has_overrides: bool = Field(
        description="True if any overrides exist for this date"
    )


class PermanentOrderItem(BaseModel):
    """Single permanent preference item."""

    task_id: str
    occurrence_index: int
    sequence_number: float


class DateOverrideItem(BaseModel):
    """Daily override for a specific task occurrence."""

    task_id: str
    occurrence_index: int
    sort_position: int


class DateRangeOrderResponse(BaseModel):
    """Response with ordering info for a date range.
    
    This returns both permanent preferences and daily overrides
    for efficient bulk loading. The frontend should:
    1. For a given date, check if daily_overrides has entries for that date
    2. If yes, use those overrides (they take precedence)
    3. If no, use permanent_order
    """

    start_date: str
    end_date: str
    permanent_order: list[PermanentOrderItem] = Field(
        description="Permanent preferences that apply to all dates"
    )
    daily_overrides: dict[str, list[DateOverrideItem]] = Field(
        description="Date -> overrides mapping. Only dates with overrides are included."
    )
