from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.core.auth import CurrentUser
from app.core.time import utc_now
from app.models.priority import Priority, PriorityRevision
from app.models.priority_value_link import PriorityValueLink
from app.models.value import Value
from app.schemas.priorities import (
    CreatePriorityRequest,
    CreatePriorityRevisionRequest,
    PriorityResponse,
    PrioritiesListResponse,
    PriorityRevisionResponse,
    ValidatePriorityRequest,
    ValidatePriorityResponse,
)
from app.services.priority_validation import validate_priority

router = APIRouter(prefix="/priorities", tags=["priorities"])


@router.post("/validate", response_model=ValidatePriorityResponse)
async def validate_priority_endpoint(
    request: ValidatePriorityRequest,
):
    """Validate a priority name and why statement before saving."""
    result = await validate_priority(request.name, request.why_statement)
    
    # Convert rule_examples list of dicts to list of RuleExample objects if present
    rule_examples_data = result.get("rule_examples")
    if rule_examples_data:
        from app.schemas.priorities import RuleExample
        rule_examples = {
            rule_name: RuleExample(**example_data)
            for rule_name, example_data in rule_examples_data.items()
        }
        result["rule_examples"] = rule_examples
    
    return ValidatePriorityResponse(**result)


@router.post("", response_model=PriorityResponse, status_code=status.HTTP_201_CREATED)
async def create_priority(
    request: CreatePriorityRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new priority with initial revision."""
    # Validate before creating
    validation = await validate_priority(request.title, request.why_matters)
    if not validation["overall_valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Priority validation failed",
                "name_feedback": validation["name_feedback"],
                "why_feedback": validation["why_feedback"],
            }
        )
    
    # Create priority container
    priority = Priority(user_id=user.id)
    db.add(priority)
    await db.flush()
    
    # Create first revision
    revision = PriorityRevision(
        priority_id=priority.id,
        title=request.title,
        why_matters=request.why_matters,
        score=request.score,
        scope=request.scope,
        cadence=request.cadence,
        constraints=request.constraints,
        notes=request.notes,
        is_active=True,
        is_anchored=False,  # Default to unanchored on creation
    )
    db.add(revision)
    await db.flush()
    
    # Set active revision
    priority.active_revision_id = revision.id
    
    # Create value links if provided
    if request.value_ids:
        for value_id in request.value_ids:
            # Get the active revision for this value
            value = await db.get(Value, value_id)
            if value and value.active_revision_id:
                link = PriorityValueLink(
                    priority_revision_id=revision.id,
                    value_revision_id=value.active_revision_id,
                )
                db.add(link)
    
    await db.commit()
    await db.refresh(priority)
    
    # Reload with active_revision and its value_links
    result = await db.execute(
        select(Priority)
        .where(Priority.id == priority.id)
        .options(
            selectinload(Priority.active_revision).selectinload(PriorityRevision.value_links).selectinload(PriorityValueLink.value_revision)
        )
    )
    priority = result.scalar_one()
    
    return PriorityResponse.model_validate(priority)


@router.get("", response_model=PrioritiesListResponse)
async def list_priorities(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get all priorities for the current user."""
    result = await db.execute(
        select(Priority)
        .where(Priority.user_id == user.id)
        .options(
            selectinload(Priority.active_revision).selectinload(PriorityRevision.value_links).selectinload(PriorityValueLink.value_revision)
        )
        .order_by(Priority.created_at)
    )
    priorities = result.scalars().all()
    
    return PrioritiesListResponse(
        priorities=[PriorityResponse.model_validate(p) for p in priorities]
    )


@router.get("/{priority_id}/history", response_model=list[PriorityRevisionResponse])
async def get_priority_history(
    priority_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get revision history for a priority."""
    # Verify ownership
    priority = await db.get(Priority, priority_id)
    if not priority or priority.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Priority not found",
        )
    
    # Get revisions
    result = await db.execute(
        select(PriorityRevision)
        .where(PriorityRevision.priority_id == priority_id)
        .order_by(PriorityRevision.created_at.desc())
    )
    revisions = result.scalars().all()
    
    return [PriorityRevisionResponse.model_validate(r) for r in revisions]


@router.post("/{priority_id}/revisions", response_model=PriorityResponse)
async def create_priority_revision(
    priority_id: str,
    request: CreatePriorityRevisionRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new revision for a priority."""
    # Verify ownership
    priority = await db.get(Priority, priority_id)
    if not priority or priority.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Priority not found",
        )
    
    # Validate before creating
    validation = await validate_priority(request.title, request.why_matters)
    if not validation["overall_valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Priority validation failed",
                "name_feedback": validation["name_feedback"],
                "why_feedback": validation["why_feedback"],
            }
        )
    
    # Deactivate current active revision
    if priority.active_revision_id:
        current_revision = await db.get(PriorityRevision, priority.active_revision_id)
        if current_revision:
            current_revision.is_active = False
    
    # Create new revision
    revision = PriorityRevision(
        priority_id=priority.id,
        title=request.title,
        why_matters=request.why_matters,
        score=request.score,
        scope=request.scope,
        cadence=request.cadence,
        constraints=request.constraints,
        notes=request.notes,
        is_active=True,
        is_anchored=False,  # New revisions start unanchored
    )
    db.add(revision)
    await db.flush()
    
    # Update active revision
    priority.active_revision_id = revision.id
    priority.updated_at = utc_now()
    
    # Create value links if provided
    if request.value_ids:
        for value_id in request.value_ids:
            # Get the active revision for this value
            value = await db.get(Value, value_id)
            if value and value.active_revision_id:
                link = PriorityValueLink(
                    priority_revision_id=revision.id,
                    value_revision_id=value.active_revision_id,
                )
                db.add(link)
    
    await db.commit()
    await db.refresh(priority)
    
    # Reload with active_revision and its value_links
    result = await db.execute(
        select(Priority)
        .where(Priority.id == priority.id)
        .options(
            selectinload(Priority.active_revision).selectinload(PriorityRevision.value_links).selectinload(PriorityValueLink.value_revision)
        )
    )
    priority = result.scalar_one()
    
    return PriorityResponse.model_validate(priority)


@router.post("/{priority_id}/anchor", response_model=PriorityResponse)
async def anchor_priority(
    priority_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Anchor a priority (mark as protected)."""
    priority = await db.get(Priority, priority_id)
    if not priority or priority.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Priority not found",
        )
    
    if priority.active_revision_id:
        active_revision = await db.get(PriorityRevision, priority.active_revision_id)
        if active_revision:
            active_revision.is_anchored = True
    
    await db.commit()
    await db.refresh(priority)
    
    # Reload with revisions
    result = await db.execute(
        select(Priority)
        .where(Priority.id == priority.id)
        .options(selectinload(Priority.revisions))
    )
    priority = result.scalar_one()
    
    return PriorityResponse.model_validate(priority)


@router.post("/{priority_id}/unanchor", response_model=PriorityResponse)
async def unanchor_priority(
    priority_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Unanchor a priority (remove protection)."""
    priority = await db.get(Priority, priority_id)
    if not priority or priority.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Priority not found",
        )
    
    if priority.active_revision_id:
        active_revision = await db.get(PriorityRevision, priority.active_revision_id)
        if active_revision:
            active_revision.is_anchored = False
    
    await db.commit()
    await db.refresh(priority)
    
    # Reload with revisions
    result = await db.execute(
        select(Priority)
        .where(Priority.id == priority.id)
        .options(selectinload(Priority.revisions))
    )
    priority = result.scalar_one()
    
    return PriorityResponse.model_validate(priority)


@router.delete("/{priority_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_priority(
    priority_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a priority."""
    priority = await db.get(Priority, priority_id)
    if not priority or priority.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Priority not found",
        )
    
    await db.delete(priority)
    await db.commit()
