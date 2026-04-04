from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

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
    ValidatePriorityRequest,
    ValidatePriorityResponse,
    PriorityCheckResponse,
    StashPriorityRequest,
)
from app.services.priority_validation import validate_priority
from app.api.helpers.priority_helpers import (
    get_priority_or_404,
    reload_priority_with_eager_loading,
    reload_priority_with_active_revision,
    get_linked_values_for_revision,
    create_value_links,
    list_user_priorities,
    get_priority_revisions,
    validate_and_raise,
)

router = APIRouter(prefix="/priorities", tags=["priorities"])


@router.post("/validate", response_model=ValidatePriorityResponse, summary="Validate priority input")
async def validate_priority_endpoint(
    request: ValidatePriorityRequest,
) -> ValidatePriorityResponse:
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


@router.post("", response_model=PriorityResponse, status_code=status.HTTP_201_CREATED, summary="Create priority")
async def create_priority(
    request: CreatePriorityRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PriorityResponse:
    """Create a new priority with initial revision."""
    await validate_and_raise(request.title, request.why_matters)
    
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
    
    await create_value_links(db, revision.id, request.value_ids)
    await db.commit()
    priority = await reload_priority_with_active_revision(db, priority.id)
    return PriorityResponse.model_validate(priority)


@router.get("", response_model=PrioritiesListResponse, summary="List active priorities")
async def list_priorities(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrioritiesListResponse:
    """Get all active (non-stashed) priorities for the current user."""
    priorities = await list_user_priorities(db, user.id, stashed=False)
    return PrioritiesListResponse(
        priorities=[PriorityResponse.model_validate(p) for p in priorities]
    )


@router.get("/stashed", response_model=PrioritiesListResponse, summary="List stashed priorities")
async def list_stashed_priorities(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PrioritiesListResponse:
    """Get all stashed priorities for the current user."""
    priorities = await list_user_priorities(db, user.id, stashed=True)
    return PrioritiesListResponse(
        priorities=[PriorityResponse.model_validate(p) for p in priorities]
    )


@router.get("/{priority_id}/history", response_model=list[PriorityRevisionResponse], summary="Get priority history")
async def get_priority_history(
    priority_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[PriorityRevisionResponse]:
    """Get revision history for a priority."""
    await get_priority_or_404(db, user.id, priority_id)
    revisions = await get_priority_revisions(db, priority_id)
    return [PriorityRevisionResponse.model_validate(r) for r in revisions]


@router.post("/{priority_id}/revisions", response_model=PriorityResponse, summary="Create priority revision")
async def create_priority_revision(
    priority_id: str,
    request: CreatePriorityRevisionRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PriorityResponse:
    """Create a new revision for a priority."""
    priority = await get_priority_or_404(db, user.id, priority_id)
    await validate_and_raise(request.title, request.why_matters)
    
    # Check if we would create an orphaned anchored priority
    # (trying to unlink all values from an anchored priority)
    if not request.value_ids or len(request.value_ids) == 0:
        if priority.active_revision_id:
            current_revision = await db.get(PriorityRevision, priority.active_revision_id)
            if current_revision and current_revision.is_anchored:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={
                        "error": "Cannot orphan anchored priority",
                        "message": "A priority needs at least one linked value when anchored. You can either link at least one value, or unanchor this priority first.",
                        "code": "ORPHANED_ANCHORED_PRIORITY"
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
    
    await create_value_links(db, revision.id, request.value_ids)
    await db.commit()
    priority = await reload_priority_with_active_revision(db, priority.id)
    return PriorityResponse.model_validate(priority)


@router.post("/{priority_id}/anchor", response_model=PriorityResponse, summary="Anchor priority")
async def anchor_priority(
    priority_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PriorityResponse:
    """Anchor a priority (mark as protected)."""
    priority = await get_priority_or_404(db, user.id, priority_id)
    
    if priority.active_revision_id:
        active_revision = await db.get(PriorityRevision, priority.active_revision_id)
        if active_revision:
            active_revision.is_anchored = True
    
    await db.commit()
    priority = await reload_priority_with_eager_loading(db, priority_id)
    return PriorityResponse.model_validate(priority)


@router.post("/{priority_id}/unanchor", response_model=PriorityResponse, summary="Unanchor priority")
async def unanchor_priority(
    priority_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PriorityResponse:
    """Unanchor a priority (remove protection)."""
    priority = await get_priority_or_404(db, user.id, priority_id)
    
    if priority.active_revision_id:
        active_revision = await db.get(PriorityRevision, priority.active_revision_id)
        if active_revision:
            active_revision.is_anchored = False
    
    await db.commit()
    priority = await reload_priority_with_eager_loading(db, priority_id)
    return PriorityResponse.model_validate(priority)


@router.delete("/{priority_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete priority")
async def delete_priority(
    priority_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a priority."""
    priority = await get_priority_or_404(db, user.id, priority_id)
    await db.delete(priority)
    await db.commit()


@router.get("/{priority_id}/check-status", response_model=PriorityCheckResponse, summary="Check priority status")
async def check_priority_status(
    priority_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PriorityCheckResponse:
    """Check if priority has linked values and anchoring status."""
    priority = await get_priority_or_404(db, user.id, priority_id)
    
    if not priority.active_revision_id:
        return PriorityCheckResponse(
            priority_id=priority_id, has_linked_values=False,
            linked_value_count=0, linked_values=[],
            is_anchored=False, status="incomplete",
        )
    
    active_rev = await db.get(PriorityRevision, priority.active_revision_id)
    if not active_rev:
        return PriorityCheckResponse(
            priority_id=priority_id, has_linked_values=False,
            linked_value_count=0, linked_values=[],
            is_anchored=False, status="incomplete",
        )
    
    linked_values = await get_linked_values_for_revision(db, active_rev.id)
    # Truncate long statements
    for lv in linked_values:
        if len(lv.value_statement) > 100:
            lv.value_statement = lv.value_statement[:100] + "..."
    
    return PriorityCheckResponse(
        priority_id=priority_id,
        has_linked_values=len(linked_values) > 0,
        linked_value_count=len(linked_values),
        linked_values=linked_values,
        is_anchored=active_rev.is_anchored,
        status="complete" if linked_values else "incomplete",
    )


@router.post("/{priority_id}/stash", response_model=PriorityResponse, summary="Stash/unstash priority")
async def stash_priority(
    priority_id: str,
    request: StashPriorityRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PriorityResponse:
    """Stash or unstash a priority (archive/inactive)."""
    priority = await get_priority_or_404(db, user.id, priority_id)
    priority.is_stashed = request.is_stashed
    await db.commit()
    priority = await reload_priority_with_eager_loading(db, priority_id)
    return PriorityResponse.model_validate(priority)
