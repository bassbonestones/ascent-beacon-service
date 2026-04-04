"""Helper functions for the values API.

Re-exports from specialized helper modules for backward compatibility.
"""

import json
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.llm import llm_client
from app.models.value import Value, ValueRevision

# Re-export from similarity helpers
from app.api.helpers.value_similarity_helpers import (
    build_similarity_insight,
    build_value_response_with_insight,
    process_value_similarity,
)

# Re-export from impact helpers
from app.api.helpers.value_impact_helpers import (
    compute_value_edit_impact,
    get_affected_priorities_for_value,
)

# Export all for backward compatibility
__all__ = [
    "get_value_or_404",
    "build_similarity_insight",
    "build_value_response_with_insight",
    "process_value_similarity",
    "compute_value_edit_impact",
    "get_affected_priorities_for_value",
    "reload_value_with_revisions",
    "match_value_by_llm",
    "rebalance_values_equal_weight",
]


async def get_value_or_404(
    db: AsyncSession,
    user_id: str,
    value_id: str,
) -> Value:
    """Get a value and verify ownership.
    
    Raises HTTPException 404 if not found or not owned by user.
    """
    value = await db.get(Value, value_id)
    if not value or value.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Value not found",
        )
    return value


async def reload_value_with_revisions(db: AsyncSession, value_id: str) -> Value:
    """Reload a value with its revisions eagerly loaded."""
    result = await db.execute(
        select(Value)
        .where(Value.id == value_id)
        .options(selectinload(Value.revisions))
    )
    return result.scalar_one()


async def match_value_by_llm(
    db: AsyncSession,
    user_id: str,
    query: str,
) -> str | None:
    """Use LLM to match a query to the closest value for the user."""
    result = await db.execute(
        select(Value)
        .where(Value.user_id == user_id)
        .options(selectinload(Value.revisions))
        .order_by(Value.created_at)
    )
    values = result.scalars().all()

    candidates = []
    for value in values:
        if not value.active_revision_id:
            continue
        active_rev = next(
            (r for r in value.revisions if r.id == value.active_revision_id), None
        )
        if active_rev:
            candidates.append({"id": str(value.id), "statement": active_rev.statement})

    if not candidates:
        return None

    prompt = (
        "You match a user request to the closest value statement from the list. "
        "Return JSON with key value_id, or null if no good match.\n\n"
        f"User request: {query}\n\n"
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
        return None

    value_id: str | None = parsed.get("value_id")
    if value_id and any(item["id"] == value_id for item in candidates):
        return value_id

    return None


async def rebalance_values_equal_weight(
    db: AsyncSession,
    user_id: str,
    new_value_count: int = 0,
) -> None:
    """Rebalance all user's values to equal weight.
    
    If new_value_count > 0, includes that in the total count for calculating weight.
    """
    result = await db.execute(
        select(Value)
        .where(Value.user_id == user_id)
        .options(selectinload(Value.revisions))
    )
    existing_values = result.scalars().all()
    
    total_count = len(existing_values) + new_value_count
    if total_count == 0:
        return
    
    equal_weight = 100 / total_count
    
    for value in existing_values:
        if value.active_revision_id:
            revision = await db.get(ValueRevision, value.active_revision_id)
            if revision:
                revision.weight_raw = Decimal(str(equal_weight))
