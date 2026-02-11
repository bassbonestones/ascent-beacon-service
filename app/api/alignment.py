from typing import Annotated
from decimal import Decimal
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.core.auth import CurrentUser
from app.models.value import Value, ValueRevision
from app.models.priority import Priority, PriorityRevision
from app.models.priority_value_link import PriorityValueLink
from app.schemas.alignment import AlignmentCheckResponse
from app.services.llm_service import LLMService

router = APIRouter(prefix="/alignment", tags=["alignment"])


@router.post("/check", response_model=AlignmentCheckResponse)
async def check_alignment(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Check alignment between declared values and implied priorities."""
    
    # Get active values
    result = await db.execute(
        select(Value)
        .where(Value.user_id == user.id)
        .options(selectinload(Value.revisions))
    )
    values = result.scalars().all()
    
    # Build declared value distribution
    declared = {}
    total_weight = Decimal("0")
    
    for value in values:
        if value.active_revision_id:
            active_rev = next(
                (r for r in value.revisions if r.id == value.active_revision_id),
                None
            )
            if active_rev:
                declared[active_rev.id] = float(active_rev.weight_raw)
                total_weight += active_rev.weight_raw
    
    # Normalize declared weights
    if total_weight > 0:
        declared = {k: v / float(total_weight) for k, v in declared.items()}
    
    # Get active anchored priorities
    result = await db.execute(
        select(Priority)
        .where(Priority.user_id == user.id)
        .options(
            selectinload(Priority.revisions).selectinload(PriorityRevision.value_links)
        )
    )
    priorities = result.scalars().all()
    
    # Build implied value distribution
    implied_weights = defaultdict(float)
    
    for priority in priorities:
        if priority.active_revision_id:
            active_rev = next(
                (r for r in priority.revisions if r.id == priority.active_revision_id),
                None
            )
            if active_rev and active_rev.is_anchored:
                # Distribute priority strength across linked values
                total_link_weight = sum(
                    float(link.link_weight) for link in active_rev.value_links
                )
                
                if total_link_weight > 0:
                    for link in active_rev.value_links:
                        contribution = (
                            float(active_rev.strength)
                            * float(link.link_weight)
                            / total_link_weight
                        )
                        implied_weights[link.value_revision_id] += contribution
    
    # Normalize implied weights
    total_implied = sum(implied_weights.values())
    if total_implied > 0:
        implied = {k: v / total_implied for k, v in implied_weights.items()}
    else:
        implied = {}
    
    # Compute total variation distance
    all_value_revisions = set(declared.keys()) | set(implied.keys())
    tvd = sum(
        abs(declared.get(vr, 0.0) - implied.get(vr, 0.0))
        for vr in all_value_revisions
    ) / 2.0
    
    # Alignment fit (1 - TVD)
    alignment_fit = 1.0 - tvd
    
    # Get LLM reflection
    reflection = await LLMService.get_alignment_reflection(
        declared=declared,
        implied=implied,
        total_variation_distance=tvd,
    )
    
    return AlignmentCheckResponse(
        declared=declared,
        implied=implied,
        total_variation_distance=tvd,
        alignment_fit=alignment_fit,
        reflection=reflection,
    )
