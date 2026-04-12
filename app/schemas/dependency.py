"""
Pydantic schemas for Dependencies API (Phase 4i).

Implements occurrence-based task dependency system where dependencies
are evaluated occurrence-to-occurrence, not task-to-task.
"""
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ============================================================================
# Type Aliases
# ============================================================================

# Strength: how strict is this dependency?
# 'hard' = blocks completion (with 2-step override option)
# 'soft' = shows warning, user can proceed
DependencyStrength = Literal["hard", "soft"]

# Scope: how do occurrences relate?
# 'all_occurrences' = every downstream needs upstream (weekly prep → all daily)
# 'next_occurrence' = upstream satisfies only next downstream (gym → next meal)
# 'within_window' = upstream valid for time period (warmup valid 60 min)
DependencyScope = Literal["all_occurrences", "next_occurrence", "within_window"]

# Resolution source: how was this resolution created?
# 'manual' = user completed task individually
# 'chain' = auto-completed via "Complete All Prerequisites" flow
# 'override' = user bypassed hard dependency with 2-step confirm
# 'system' = auto-completed by system (AI, calendar sync, etc.)
ResolutionSource = Literal["manual", "chain", "override", "system"]

# Readiness state for dependency cache
# 'ready' = all deps met
# 'blocked' = hard dep unmet
# 'partial' = some deps met, some not
# 'advisory' = soft deps unmet (still completable)
ReadinessState = Literal["ready", "blocked", "partial", "advisory"]


# ============================================================================
# Nested/Shared Schemas
# ============================================================================


class TaskInfo(BaseModel):
    """Brief info about a task."""

    id: str
    title: str
    is_recurring: bool = False
    recurrence_rule: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Dependency Rule Schemas
# ============================================================================


class CreateDependencyRuleRequest(BaseModel):
    """Request to create a new dependency rule."""

    upstream_task_id: str = Field(
        ..., description="ID of the prerequisite task (must be completed first)"
    )
    downstream_task_id: str = Field(
        ..., description="ID of the dependent task (requires the prerequisite)"
    )
    strength: DependencyStrength = Field(
        default="soft",
        description="'hard' blocks completion, 'soft' shows warning only",
    )
    scope: DependencyScope = Field(
        default="next_occurrence",
        description="How occurrences relate: 'all_occurrences', 'next_occurrence', or 'within_window'",
    )
    required_occurrence_count: int = Field(
        default=1,
        ge=1,
        description="How many upstream completions required (e.g., 4 waters before gym)",
    )
    validity_window_minutes: int | None = Field(
        default=None,
        ge=1,
        description="For 'within_window' scope: how long upstream is valid (minutes). NULL = use upstream's recurrence interval",
    )

    @model_validator(mode="after")
    def validate_self_dependency(self) -> "CreateDependencyRuleRequest":
        """Ensure task doesn't depend on itself."""
        if self.upstream_task_id == self.downstream_task_id:
            raise ValueError("A task cannot depend on itself")
        return self


class UpdateDependencyRuleRequest(BaseModel):
    """Request to update an existing dependency rule."""

    strength: DependencyStrength | None = None
    scope: DependencyScope | None = None
    required_occurrence_count: int | None = Field(default=None, ge=1)
    validity_window_minutes: int | None = Field(default=None, ge=1)


class DependencyRuleResponse(BaseModel):
    """Response for a single dependency rule."""

    id: str
    user_id: str
    upstream_task_id: str
    downstream_task_id: str
    strength: str  # hard | soft
    scope: str  # all_occurrences | next_occurrence | within_window
    required_occurrence_count: int
    validity_window_minutes: int | None = None
    created_at: datetime
    updated_at: datetime

    # Nested task info (populated via eager loading)
    upstream_task: TaskInfo | None = None
    downstream_task: TaskInfo | None = None

    model_config = ConfigDict(from_attributes=True)


class DependencyRuleListResponse(BaseModel):
    """Response for listing dependency rules."""

    rules: list[DependencyRuleResponse]
    total: int = 0


# ============================================================================
# Dependency Resolution Schemas
# ============================================================================


class DependencyResolutionResponse(BaseModel):
    """Response for a single dependency resolution record."""

    id: str
    dependency_rule_id: str
    downstream_completion_id: str
    upstream_completion_id: str | None = None
    resolved_at: datetime
    occurrence_index: int  # For count-based: which of N (1-indexed)
    resolution_source: str  # manual | chain | override | system
    override_reason: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Cycle Validation Schemas
# ============================================================================


class CycleValidationRequest(BaseModel):
    """Request to validate if adding a dependency would create a cycle."""

    upstream_task_id: str
    downstream_task_id: str


class CycleValidationResponse(BaseModel):
    """Response for cycle validation."""

    valid: bool
    reason: str | None = None
    cycle_path: list[str] | None = None  # Task IDs forming the cycle


# ============================================================================
# Dependency Status Schemas (for checking deps before completing)
# ============================================================================


class DependencyBlocker(BaseModel):
    """Info about an unmet dependency blocking completion."""

    rule_id: str
    upstream_task: TaskInfo
    strength: str  # hard | soft
    scope: str
    required_count: int
    completed_count: int
    is_met: bool
    validity_window_minutes: int | None = Field(
        default=None,
        description=(
            "For within_window: resolved lookback in minutes (explicit rule value or "
            "upstream recurrence default). Null when scope is not within_window."
        ),
    )

    @property
    def progress_pct(self) -> int:
        """Completion progress as percentage."""
        if self.required_count == 0:
            return 100
        return int((self.completed_count / self.required_count) * 100)


class DependencyDependent(BaseModel):
    """Info about a downstream task that depends on this task."""

    rule_id: str
    downstream_task: TaskInfo
    strength: str  # hard | soft


class DependencyStatusResponse(BaseModel):
    """Response for checking dependency status of a task occurrence."""

    task_id: str
    scheduled_for: datetime | None = None

    # Dependencies (what this task requires)
    dependencies: list[DependencyBlocker] = []
    # Unmet hard prerequisites in topological order (recursive chain), for completion UI
    transitive_unmet_hard_prerequisites: list[DependencyBlocker] = []
    has_unmet_hard: bool = False
    has_unmet_soft: bool = False
    all_met: bool = True

    # Dependents (what relies on this task)
    dependents: list[DependencyDependent] = []

    # Cached readiness state
    readiness_state: ReadinessState = "ready"

    @model_validator(mode="after")
    def compute_states(self) -> "DependencyStatusResponse":
        """Compute derived state fields."""
        hard_unmet = any(
            d.strength == "hard" and not d.is_met for d in self.dependencies
        )
        soft_unmet = any(
            d.strength == "soft" and not d.is_met for d in self.dependencies
        )
        self.has_unmet_hard = hard_unmet
        self.has_unmet_soft = soft_unmet
        self.all_met = not hard_unmet and not soft_unmet

        # Determine readiness state
        if self.all_met:
            self.readiness_state = "ready"
        elif hard_unmet:
            # Check if partial (some hard deps met)
            hard_deps = [d for d in self.dependencies if d.strength == "hard"]
            if any(d.is_met for d in hard_deps) and any(
                not d.is_met for d in hard_deps
            ):
                self.readiness_state = "partial"
            else:
                self.readiness_state = "blocked"
        else:
            # Only soft deps unmet
            self.readiness_state = "advisory"

        return self


# ============================================================================
# State Cache Schemas
# ============================================================================


class DependencyStateCacheResponse(BaseModel):
    """Response for cached dependency state."""

    task_id: str
    scheduled_for: datetime
    readiness_state: str  # ready | blocked | partial | advisory
    unmet_hard_count: int
    unmet_soft_count: int
    total_progress_pct: int | None = None
    cached_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Dependency Blocked Response (for 409 Conflict)
# ============================================================================


class DependencyBlockedResponse(BaseModel):
    """
    Response when a task completion is blocked by unmet hard dependencies.
    
    Returned with HTTP 409 when attempting to complete a task with
    unmet hard dependencies without providing override confirmation.
    """

    message: str = "Cannot complete task due to unmet hard dependencies"
    task_id: str
    scheduled_for: datetime | None = None
    blockers: list[DependencyBlocker]
    can_override: bool = True  # Always true - user can override if they provide reason
    hint: str = "Retry with override_confirm=true and override_reason to bypass"
