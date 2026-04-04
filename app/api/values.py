from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.core.auth import CurrentUser
from app.core.time import utc_now
from app.models.value import Value, ValueRevision
from app.models.priority_value_link import PriorityValueLink
from app.schemas.values import (
    CreateValueRequest,
    CreateValueRevisionRequest,
    AcknowledgeValueInsightRequest,
    ValueResponse,
    ValuesListResponse,
    ValueRevisionResponse,
    ValueMatchRequest,
    ValueMatchResponse,
    ValueEditResponse,
    AffectedPriorityInfo,
    ValueDeleteConflict,
)
from app.services.value_service import normalize_value_weights
from app.api.helpers.value_helpers import (
    build_value_response_with_insight,
    process_value_similarity,
    compute_value_edit_impact,
    get_affected_priorities_for_value,
    reload_value_with_revisions,
    match_value_by_llm,
    rebalance_values_equal_weight,
    get_value_or_404,
)

router = APIRouter(prefix="/values", tags=["values"])


@router.post("", response_model=ValueResponse, status_code=status.HTTP_201_CREATED, summary="Create value")
async def create_value(
    request: CreateValueRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ValueResponse:
    """Create a new value with initial revision."""
    print(f"\n\n{'='*60}")
    print(f"POST /values called")
    print(f"Request body: {request}")
    print(f"source_prompt_id received: {request.source_prompt_id}")
    print(f"source_prompt_id type: {type(request.source_prompt_id)}")
    print(f"{'='*60}")
    
    # Rebalance existing values to make room for the new one
    await rebalance_values_equal_weight(db, user.id, new_value_count=1)
    
    # Create value container
    value = Value(user_id=user.id)
    db.add(value)
    await db.flush()

    # Get the equal weight for all values
    result = await db.execute(select(Value).where(Value.user_id == user.id))
    total_count = len(result.scalars().all())
    equal_weight = 100 / total_count

    # Create first revision with equal weight
    revision = ValueRevision(
        value_id=value.id,
        statement=request.statement,
        weight_raw=equal_weight,
        origin=request.origin,
        source_prompt_id=request.source_prompt_id,
        is_active=True,
    )
    print(f"Created revision with source_prompt_id: {revision.source_prompt_id}")
    db.add(revision)
    await db.flush()
    print(f"After flush, revision.source_prompt_id: {revision.source_prompt_id}")

    # Set active revision
    value.active_revision_id = revision.id

    # Normalize weights across all user values
    await normalize_value_weights(db, user.id)

    # Process similarity
    insight = await process_value_similarity(
        db, user.id, request.statement, revision, value.id
    )

    await db.commit()
    await db.refresh(value)

    # Load with active revision
    value = await reload_value_with_revisions(db, value.id)

    response = ValueResponse.model_validate(value)
    if insight:
        response = response.model_copy(update={"insights": [insight]})
    return response


@router.get("", response_model=ValuesListResponse, summary="List user values")
async def list_values(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ValuesListResponse:
    """Get all values for the current user."""
    result = await db.execute(
        select(Value)
        .where(Value.user_id == user.id)
        .options(selectinload(Value.revisions))
        .order_by(Value.created_at)
    )
    values = result.scalars().all()
    
    revision_lookup = {}
    for value in values:
        for revision in value.revisions:
            revision_lookup[str(revision.id)] = revision

    return ValuesListResponse(
        values=[build_value_response_with_insight(v, revision_lookup) for v in values]
    )


@router.post("/match", response_model=ValueMatchResponse, summary="Match value by query")
async def match_value(
    request: ValueMatchRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ValueMatchResponse:
    """Use the LLM to match a query to the closest value for the user."""
    value_id = await match_value_by_llm(db, user.id, request.query)
    return ValueMatchResponse(value_id=value_id)


@router.get("/{value_id}/history", response_model=list[ValueRevisionResponse], summary="Get value history")
async def get_value_history(
    value_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[ValueRevisionResponse]:
    """Get revision history for a value."""
    await get_value_or_404(db, user.id, value_id)
    
    # Get revisions
    result = await db.execute(
        select(ValueRevision)
        .where(ValueRevision.value_id == value_id)
        .order_by(ValueRevision.created_at.desc())
    )
    revisions = result.scalars().all()
    
    return [ValueRevisionResponse.model_validate(r) for r in revisions]


@router.post("/{value_id}/revisions", response_model=ValueEditResponse, summary="Create value revision")
async def create_value_revision(
    value_id: str,
    request: CreateValueRevisionRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ValueEditResponse:
    """Create a new revision for a value."""
    value = await get_value_or_404(db, user.id, value_id)

    # Store old revision info for impact detection
    old_active_revision = None
    if value.active_revision_id:
        old_active_revision = await db.get(ValueRevision, value.active_revision_id)

    # Deactivate current active revision
    if value.active_revision_id:
        current_revision = await db.get(ValueRevision, value.active_revision_id)
        if current_revision:
            current_revision.is_active = False

    # Create new revision
    revision = ValueRevision(
        value_id=value.id,
        statement=request.statement,
        weight_raw=request.weight_raw,
        origin=request.origin,
        source_prompt_id=request.source_prompt_id,
        is_active=True,
    )
    db.add(revision)
    await db.flush()

    # Update active revision
    value.active_revision_id = revision.id
    value.updated_at = utc_now()

    # Normalize weights across all user values
    await normalize_value_weights(db, user.id)

    # Process similarity
    insight = await process_value_similarity(
        db, user.id, request.statement, revision, value.id
    )

    await db.commit()
    await db.refresh(value)

    # Reload with revisions
    value = await reload_value_with_revisions(db, value.id)

    response = ValueResponse.model_validate(value)
    if insight:
        response = response.model_copy(update={"insights": [insight]})

    # Compute impact info
    impact_info = await compute_value_edit_impact(
        db, user.id, value, revision, old_active_revision, request.statement
    )

    return ValueEditResponse(
        **response.model_dump(),
        impact_info=impact_info,
    )


@router.post("/{value_id}/insights/acknowledge", response_model=ValueResponse, summary="Acknowledge value insight")
async def acknowledge_value_insight(
    value_id: str,
    request: AcknowledgeValueInsightRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ValueResponse:
    """Acknowledge a similarity insight for a value revision."""
    value = await get_value_or_404(db, user.id, value_id)

    revision_id = request.revision_id or value.active_revision_id
    if not revision_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active revision to acknowledge",
        )

    revision = await db.get(ValueRevision, revision_id)
    if not revision or revision.value_id != value.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Revision not found",
        )

    revision.similarity_acknowledged = True
    await db.commit()

    value = await reload_value_with_revisions(db, value.id)

    revision_lookup = {}
    for rev in value.revisions:
        revision_lookup[str(rev.id)] = rev

    return build_value_response_with_insight(value, revision_lookup)


@router.put("/{value_id}", response_model=ValueEditResponse, summary="Update value")
async def update_value(
    value_id: str,
    request: CreateValueRevisionRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ValueEditResponse:
    """Update a value (creates new revision)."""
    return await create_value_revision(value_id, request, user, db)


@router.delete("/{value_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete value")
async def delete_value(
    value_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    cascade: bool = False,
) -> None:
    """Delete a value.
    
    Args:
        cascade: If True, unlinks all priorities before deleting.
                 If False and value has linked priorities, returns 409 Conflict.
    """
    value = await get_value_or_404(db, user.id, value_id)
    
    # Check for linked priorities
    affected_priorities = await get_affected_priorities_for_value(db, user.id, value_id)
    
    if affected_priorities and not cascade:
        # Return 409 Conflict with details
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=ValueDeleteConflict(
                message=f"Value is linked to {len(affected_priorities)} priority(ies). Use cascade=true to delete anyway.",
                affected_priorities=affected_priorities,
            ).model_dump(),
        )
    
    if affected_priorities and cascade:
        # Delete all links to this value's revisions
        revisions_result = await db.execute(
            select(ValueRevision.id).where(ValueRevision.value_id == value_id)
        )
        revision_ids = [r for r in revisions_result.scalars().all()]
        
        if revision_ids:
            await db.execute(
                select(PriorityValueLink).where(
                    PriorityValueLink.value_revision_id.in_(revision_ids)
                )
            )
            # Actually delete the links
            from sqlalchemy import delete as sql_delete
            await db.execute(
                sql_delete(PriorityValueLink).where(
                    PriorityValueLink.value_revision_id.in_(revision_ids)
                )
            )
    
    await db.delete(value)
    await db.commit()
    
    # Renormalize remaining values
    await normalize_value_weights(db, user.id)
    await db.commit()


@router.get("/{value_id}/linked-priorities", response_model=list[AffectedPriorityInfo], summary="Get linked priorities")
async def get_linked_priorities(
    value_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[AffectedPriorityInfo]:
    """Get all priorities that link to this value (via any revision)."""
    await get_value_or_404(db, user.id, value_id)
    return await get_affected_priorities_for_value(db, user.id, value_id)
