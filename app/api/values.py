from typing import Annotated
import json
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy  import select
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.core.auth import CurrentUser
from app.core.time import utc_now
from app.core.llm import llm_client
from app.models.embedding import Embedding
from app.models.value import Value, ValueRevision
from app.schemas.values import (
    CreateValueRequest,
    CreateValueRevisionRequest,
    AcknowledgeValueInsightRequest,
    ValueResponse,
    ValuesListResponse,
    ValueRevisionResponse,
    ValueInsight,
    ValueMatchRequest,
    ValueMatchResponse,
)
from app.services.value_service import normalize_value_weights
from app.services.value_similarity import (
    compute_value_similarity,
    EMBEDDING_MODEL,
)

router = APIRouter(prefix="/values", tags=["values"])

def build_similarity_insight(similar_statement: str, match: dict) -> ValueInsight:
    return ValueInsight(
        type="similar_value",
        similar_value_id=match["similar_value_id"],
        similar_value_revision_id=match["similar_value_revision_id"],
        similarity_score=match["similarity_score"],
        message=(
            f"This sounds a bit like \"{similar_statement}\". "
            "Totally fine - just flagging it in case you want to refine later."
        ),
    )


def build_value_response_with_insight(
    value: Value,
    revision_lookup: dict[str, ValueRevision],
) -> ValueResponse:
    response = ValueResponse.model_validate(value)

    active_rev_obj = next(
        (r for r in value.revisions if r.id == value.active_revision_id),
        None,
    )
    if not active_rev_obj:
        return response

    if not active_rev_obj.similar_value_revision_id:
        return response

    if active_rev_obj.similarity_acknowledged:
        return response

    similar_rev = revision_lookup.get(active_rev_obj.similar_value_revision_id)
    if not similar_rev:
        return response

    insight = build_similarity_insight(
        similar_rev.statement,
        {
            "similar_value_id": str(similar_rev.value_id),
            "similar_value_revision_id": str(similar_rev.id),
            "similarity_score": float(active_rev_obj.similarity_score or 0),
        },
    )

    return response.model_copy(update={"insights": [insight]})


@router.post("", response_model=ValueResponse, status_code=status.HTTP_201_CREATED)
async def create_value(
    request: CreateValueRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new value with initial revision."""
    # First, rebalance existing values to equal weight
    existing_result = await db.execute(
        select(Value)
        .where(Value.user_id == user.id)
        .options(selectinload(Value.revisions))
    )
    existing_values = existing_result.scalars().all()
    
    # Count how many values will exist after creation
    new_count = len(existing_values) + 1
    equal_weight = 100 / new_count
    
    # Update all existing active revisions to equal weight
    for value in existing_values:
        if value.active_revision_id:
            revision = await db.get(ValueRevision, value.active_revision_id)
            if revision:
                revision.weight_raw = equal_weight
    
    # Create value container
    value = Value(user_id=user.id)
    db.add(value)
    await db.flush()
    
    # Create first revision with equal weight
    revision = ValueRevision(
        value_id=value.id,
        statement=request.statement,
        weight_raw=equal_weight,
        origin=request.origin,
        is_active=True,
    )
    db.add(revision)
    await db.flush()
    
    # Set active revision
    value.active_revision_id = revision.id
    
    # Normalize weights across all user values
    await normalize_value_weights(db, user.id)

    insight = None
    try:
        match, proposed_embedding = await compute_value_similarity(
            db,
            user.id,
            request.statement,
            exclude_value_id=value.id,
        )
        if match:
            revision.similar_value_revision_id = match["similar_value_revision_id"]
            revision.similarity_score = Decimal(str(match["similarity_score"]))
            revision.similarity_acknowledged = False
            insight = build_similarity_insight(match["similar_statement"], match)
        
        # Check if embedding already exists before creating
        if proposed_embedding:
            existing_embedding = await db.execute(
                select(Embedding).where(
                    Embedding.entity_type == "value_revision",
                    Embedding.entity_id == revision.id,
                    Embedding.model == EMBEDDING_MODEL,
                )
            )
            if not existing_embedding.scalar_one_or_none():
                db.add(
                    Embedding(
                        entity_type="value_revision",
                        entity_id=revision.id,
                        model=EMBEDDING_MODEL,
                        dims=len(proposed_embedding),
                        embedding=proposed_embedding,
                    )
                )
                await db.flush()
    except Exception:
        insight = None

    await db.commit()
    await db.refresh(value)
    
    # Load with active revision
    result = await db.execute(
        select(Value)
        .where(Value.id == value.id)
        .options(selectinload(Value.revisions))
    )
    value = result.scalar_one()
    
    response = ValueResponse.model_validate(value)
    if insight:
        response = response.model_copy(update={"insights": [insight]})
    return response


@router.get("", response_model=ValuesListResponse)
async def list_values(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
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


@router.post("/match", response_model=ValueMatchResponse)
async def match_value(
    request: ValueMatchRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Use the LLM to match a query to the closest value for the user."""
    result = await db.execute(
        select(Value)
        .where(Value.user_id == user.id)
        .options(selectinload(Value.revisions))
        .order_by(Value.created_at)
    )
    values = result.scalars().all()

    candidates = []
    for value in values:
        if not value.active_revision_id:
            continue
        active_rev = next((r for r in value.revisions if r.id == value.active_revision_id), None)
        if active_rev:
            candidates.append({"id": str(value.id), "statement": active_rev.statement})

    if not candidates:
        return ValueMatchResponse(value_id=None)

    prompt = (
        "You match a user request to the closest value statement from the list. "
        "Return JSON with key value_id, or null if no good match.\n\n"
        f"User request: {request.query}\n\n"
        "Values:\n"
        + "\n".join([f"- {item['id']}: {item['statement']}" for item in candidates])
    )

    response = await llm_client.chat_completion(
        messages=[
            {"role": "system", "content": "You match user requests to value statements."},
            {"role": "user", "content": prompt},
        ],
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=200,
    )

    content = response["choices"][0]["message"].get("content") or "{}"
    try:
        parsed = json.loads(content)
    except Exception:
        return ValueMatchResponse(value_id=None)

    value_id = parsed.get("value_id")
    if value_id and any(item["id"] == value_id for item in candidates):
        return ValueMatchResponse(value_id=value_id)

    return ValueMatchResponse(value_id=None)


@router.get("/{value_id}/history", response_model=list[ValueRevisionResponse])
async def get_value_history(
    value_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get revision history for a value."""
    # Verify ownership
    value = await db.get(Value, value_id)
    if not value or value.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Value not found",
        )
    
    # Get revisions
    result = await db.execute(
        select(ValueRevision)
        .where(ValueRevision.value_id == value_id)
        .order_by(ValueRevision.created_at.desc())
    )
    revisions = result.scalars().all()
    
    return [ValueRevisionResponse.model_validate(r) for r in revisions]


@router.post("/{value_id}/revisions", response_model=ValueResponse)
async def create_value_revision(
    value_id: str,
    request: CreateValueRevisionRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new revision for a value."""
    # Verify ownership
    value = await db.get(Value, value_id)
    if not value or value.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Value not found",
        )
    
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
        is_active=True,
    )
    db.add(revision)
    await db.flush()
    
    # Update active revision
    value.active_revision_id = revision.id
    value.updated_at = utc_now()
    
    # Normalize weights across all user values
    await normalize_value_weights(db, user.id)

    insight = None
    try:
        match, proposed_embedding = await compute_value_similarity(
            db,
            user.id,
            request.statement,
            exclude_value_id=value.id,
        )
        if match:
            revision.similar_value_revision_id = match["similar_value_revision_id"]
            revision.similarity_score = Decimal(str(match["similarity_score"]))
            revision.similarity_acknowledged = False
            insight = build_similarity_insight(match["similar_statement"], match)
        
        # Check if embedding already exists before creating
        if proposed_embedding:
            existing_embedding = await db.execute(
                select(Embedding).where(
                    Embedding.entity_type == "value_revision",
                    Embedding.entity_id == revision.id,
                    Embedding.model == EMBEDDING_MODEL,
                )
            )
            if not existing_embedding.scalar_one_or_none():
                db.add(
                    Embedding(
                        entity_type="value_revision",
                        entity_id=revision.id,
                        model=EMBEDDING_MODEL,
                        dims=len(proposed_embedding),
                        embedding=proposed_embedding,
                    )
                )
                await db.flush()
    except Exception:
        insight = None

    await db.commit()
    await db.refresh(value)
    
    # Reload with revisions
    result = await db.execute(
        select(Value)
        .where(Value.id == value.id)
        .options(selectinload(Value.revisions))
    )
    value = result.scalar_one()
    
    response = ValueResponse.model_validate(value)
    if insight:
        response = response.model_copy(update={"insights": [insight]})
    return response


@router.post("/{value_id}/insights/acknowledge", response_model=ValueResponse)
async def acknowledge_value_insight(
    value_id: str,
    request: AcknowledgeValueInsightRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Acknowledge a similarity insight for a value revision."""
    value = await db.get(Value, value_id)
    if not value or value.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Value not found",
        )

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

    result = await db.execute(
        select(Value)
        .where(Value.id == value.id)
        .options(selectinload(Value.revisions))
    )
    value = result.scalar_one()

    revision_lookup = {}
    for rev in value.revisions:
        revision_lookup[str(rev.id)] = rev

    return build_value_response_with_insight(value, revision_lookup)


@router.put("/{value_id}", response_model=ValueResponse)
async def update_value(
    value_id: str,
    request: CreateValueRevisionRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Update a value (creates new revision)."""
    return await create_value_revision(value_id, request, user, db)


@router.delete("/{value_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_value(
    value_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Delete a value."""
    # Verify ownership
    value = await db.get(Value, value_id)
    if not value or value.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Value not found",
        )
    
    await db.delete(value)
    await db.commit()
    
    # Renormalize remaining values
    await normalize_value_weights(db, user.id)
    await db.commit()
