from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.core.auth import CurrentUser
from app.core.time import utc_now
from app.models.priority import Priority, PriorityRevision
from app.schemas.priorities import (
    CreatePriorityRequest,
    CreatePriorityRevisionRequest,
    PriorityResponse,
    PrioritiesListResponse,
    PriorityRevisionResponse,
)

router = APIRouter(prefix="/priorities", tags=["priorities"])


@router.post("", response_model=PriorityResponse, status_code=status.HTTP_201_CREATED)
async def create_priority(
    request: CreatePriorityRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new priority with initial revision."""
    # Create priority container
    priority = Priority(user_id=user.id)
    db.add(priority)
    await db.flush()
    
    # Create first revision
    revision = PriorityRevision(
        priority_id=priority.id,
        title=request.title,
        body=request.body,
        strength=request.strength,
        is_anchored=request.is_anchored,
        notes=request.notes,
        is_active=True,
    )
    db.add(revision)
    await db.flush()
    
    # Set active revision
    priority.active_revision_id = revision.id
    
    await db.commit()
    await db.refresh(priority)
    
    # Load with active revision
    result = await db.execute(
        select(Priority)
        .where(Priority.id == priority.id)
        .options(selectinload(Priority.revisions))
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
        .options(selectinload(Priority.revisions))
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
    
    # Deactivate current active revision
    if priority.active_revision_id:
        current_revision = await db.get(PriorityRevision, priority.active_revision_id)
        if current_revision:
            current_revision.is_active = False
    
    # Create new revision
    revision = PriorityRevision(
        priority_id=priority.id,
        title=request.title,
        body=request.body,
        strength=request.strength,
        is_anchored=request.is_anchored,
        notes=request.notes,
        is_active=True,
    )
    db.add(revision)
    await db.flush()
    
    # Update active revision
    priority.active_revision_id = revision.id
    priority.updated_at = utc_now()
    
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
