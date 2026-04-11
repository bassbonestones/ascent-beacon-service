"""
Dependencies API endpoints (Phase 4i).
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.core.time import utc_now
from app.models.dependency import DependencyRule
from app.schemas.dependency import (
    CreateDependencyRuleRequest,
    CycleValidationRequest,
    CycleValidationResponse,
    DependencyRuleListResponse,
    DependencyRuleResponse,
    UpdateDependencyRuleRequest,
)
from app.api.helpers.dependency_helpers import (
    get_rule_or_404,
    get_task_or_404_for_dep,
    check_rule_exists,
    detect_cycle,
    rule_to_response,
)

router = APIRouter(prefix="/dependencies", tags=["dependencies"])


def normalize_uuid(uuid_str: str | None) -> str | None:
    """Normalize UUID by removing hyphens for consistent comparison."""
    return uuid_str.replace("-", "") if uuid_str else None


@router.post(
    "",
    response_model=DependencyRuleResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create dependency rule",
)
async def create_dependency_rule(
    request: CreateDependencyRuleRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DependencyRuleResponse:
    """Create a new dependency rule between two tasks."""
    await get_task_or_404_for_dep(db, request.upstream_task_id, user.id)
    await get_task_or_404_for_dep(db, request.downstream_task_id, user.id)

    # Check if rule already exists
    if await check_rule_exists(
        db, request.upstream_task_id, request.downstream_task_id
    ):
        raise HTTPException(
            status_code=400,
            detail="A dependency rule already exists between these tasks",
        )

    # Check for cycles
    has_cycle, cycle_path = await detect_cycle(
        db, user.id, request.upstream_task_id, request.downstream_task_id
    )
    if has_cycle:
        cycle_str = " → ".join(cycle_path[::-1]) if cycle_path else "unknown"
        raise HTTPException(
            status_code=400,
            detail=f"Would create cycle: {cycle_str}",
        )

    # Create rule
    rule = DependencyRule(
        user_id=user.id,
        upstream_task_id=request.upstream_task_id,
        downstream_task_id=request.downstream_task_id,
        strength=request.strength,
        scope=request.scope,
        required_occurrence_count=request.required_occurrence_count,
        validity_window_minutes=request.validity_window_minutes,
    )
    db.add(rule)
    await db.commit()

    # Reload with relationships
    rule = await get_rule_or_404(db, rule.id, user.id)
    return rule_to_response(rule)


@router.get("", response_model=DependencyRuleListResponse, summary="List dependency rules")
async def list_dependency_rules(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    upstream_task_id: str | None = Query(
        default=None, description="Filter by upstream (prerequisite) task"
    ),
    downstream_task_id: str | None = Query(
        default=None, description="Filter by downstream (dependent) task"
    ),
    task_id: str | None = Query(
        default=None,
        description="Filter by task (either upstream or downstream)",
    ),
) -> DependencyRuleListResponse:
    """Get all dependency rules, optionally filtered by task."""
    # Normalize UUIDs for consistent comparison
    norm_upstream = normalize_uuid(upstream_task_id)
    norm_downstream = normalize_uuid(downstream_task_id)
    norm_task = normalize_uuid(task_id)

    stmt = (
        select(DependencyRule)
        .options(
            selectinload(DependencyRule.upstream_task),
            selectinload(DependencyRule.downstream_task),
        )
        .where(DependencyRule.user_id == user.id)
    )

    if norm_upstream:
        stmt = stmt.where(DependencyRule.upstream_task_id == norm_upstream)

    if norm_downstream:
        stmt = stmt.where(DependencyRule.downstream_task_id == norm_downstream)

    if norm_task:
        # Match either upstream or downstream
        stmt = stmt.where(
            (DependencyRule.upstream_task_id == norm_task)
            | (DependencyRule.downstream_task_id == norm_task)
        )

    stmt = stmt.order_by(DependencyRule.created_at.desc())
    result = await db.execute(stmt)
    rules = result.scalars().all()

    return DependencyRuleListResponse(
        rules=[rule_to_response(r) for r in rules],
        total=len(rules),
    )


@router.get("/{rule_id}", response_model=DependencyRuleResponse, summary="Get dependency rule")
async def get_dependency_rule(
    rule_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DependencyRuleResponse:
    """Get a single dependency rule by ID."""
    rule = await get_rule_or_404(db, rule_id, user.id)
    return rule_to_response(rule)


@router.patch(
    "/{rule_id}",
    response_model=DependencyRuleResponse,
    summary="Update dependency rule",
)
async def update_dependency_rule(
    rule_id: str,
    request: UpdateDependencyRuleRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DependencyRuleResponse:
    """Update a dependency rule's strength, scope, count, or window."""
    rule = await get_rule_or_404(db, rule_id, user.id)

    if request.strength is not None:
        rule.strength = request.strength
    if request.scope is not None:
        rule.scope = request.scope
    if request.required_occurrence_count is not None:
        rule.required_occurrence_count = request.required_occurrence_count
    if request.validity_window_minutes is not None:
        rule.validity_window_minutes = request.validity_window_minutes

    rule.updated_at = utc_now()
    await db.commit()

    # Reload with relationships
    rule = await get_rule_or_404(db, rule.id, user.id)
    return rule_to_response(rule)


@router.delete(
    "/{rule_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete dependency rule",
)
async def delete_dependency_rule(
    rule_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a dependency rule."""
    rule = await get_rule_or_404(db, rule_id, user.id)
    await db.delete(rule)
    await db.commit()


# ============================================================================
# Cycle Validation Endpoint
# ============================================================================


@router.post(
    "/validate",
    response_model=CycleValidationResponse,
    summary="Validate dependency (cycle check)",
)
async def validate_dependency(
    request: CycleValidationRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> CycleValidationResponse:
    """Check if adding a dependency would create a cycle."""
    if request.upstream_task_id == request.downstream_task_id:
        return CycleValidationResponse(
            valid=False, reason="A task cannot depend on itself"
        )

    try:
        await get_task_or_404_for_dep(db, request.upstream_task_id, user.id)
        await get_task_or_404_for_dep(db, request.downstream_task_id, user.id)
    except HTTPException:
        return CycleValidationResponse(
            valid=False, reason="One or both tasks not found"
        )

    if await check_rule_exists(
        db, request.upstream_task_id, request.downstream_task_id
    ):
        return CycleValidationResponse(
            valid=False,
            reason="A dependency rule already exists between these tasks",
        )

    has_cycle, cycle_path = await detect_cycle(
        db, user.id, request.upstream_task_id, request.downstream_task_id
    )
    if has_cycle:
        cycle_str = " → ".join(cycle_path[::-1]) if cycle_path else "unknown"
        return CycleValidationResponse(
            valid=False,
            reason=f"Would create cycle: {cycle_str}",
            cycle_path=cycle_path,
        )

    return CycleValidationResponse(valid=True)
