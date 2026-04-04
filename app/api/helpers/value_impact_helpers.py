"""Impact calculation helper functions for values API."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.priority import Priority, PriorityRevision
from app.models.priority_value_link import PriorityValueLink
from app.models.value import Value, ValueRevision
from app.schemas.values import AffectedPriorityInfo, ValueEditImpactInfo


async def compute_value_edit_impact(
    db: AsyncSession,
    user_id: str,
    value: Value,
    new_revision: ValueRevision,
    old_active_revision: ValueRevision | None,
    new_statement: str,
) -> ValueEditImpactInfo:
    """Compute the impact of editing a value (affected priorities, similarity changes)."""
    value_revisions = [vr.id for vr in value.revisions]

    priorities_result = await db.execute(
        select(Priority)
        .join(PriorityRevision, Priority.id == PriorityRevision.priority_id)
        .join(PriorityValueLink, PriorityValueLink.priority_revision_id == PriorityRevision.id)
        .where(
            Priority.user_id == user_id,
            PriorityValueLink.value_revision_id.in_(value_revisions),
            PriorityRevision.is_active == True,
        )
        .options(selectinload(Priority.active_revision))
        .distinct()
    )
    affected_priorities = priorities_result.scalars().all()

    affected_priority_infos = []
    for p in affected_priorities:
        if p.active_revision:
            affected_priority_infos.append(
                AffectedPriorityInfo(
                    priority_id=str(p.id),
                    title=p.active_revision.title,
                    is_anchored=p.active_revision.is_anchored,
                )
            )

    old_similar_id = old_active_revision.similar_value_revision_id if old_active_revision else None
    similarity_changed = old_similar_id != (new_revision.similar_value_revision_id or None)

    weight_verification_recommended = False
    if old_active_revision:
        old_len = len(old_active_revision.statement)
        new_len = len(new_statement)
        weight_verification_recommended = (
            abs(new_len - old_len) > 20
            or old_active_revision.statement.lower() != new_statement.lower()
        )

    return ValueEditImpactInfo(
        affected_priorities_count=len(affected_priority_infos),
        affected_priorities=affected_priority_infos,
        similarity_changed=similarity_changed,
        new_similar_value_id=str(new_revision.similar_value_revision_id) if new_revision.similar_value_revision_id else None,
        weight_verification_recommended=weight_verification_recommended,
    )


async def get_affected_priorities_for_value(
    db: AsyncSession,
    user_id: str,
    value_id: str,
) -> list[AffectedPriorityInfo]:
    """Get all priorities that link to any revision of a value."""
    revisions_result = await db.execute(
        select(ValueRevision).where(ValueRevision.value_id == value_id)
    )
    value_revisions = revisions_result.scalars().all()

    if not value_revisions:
        return []

    priorities_result = await db.execute(
        select(Priority)
        .join(PriorityRevision, Priority.id == PriorityRevision.priority_id)
        .join(PriorityValueLink, PriorityValueLink.priority_revision_id == PriorityRevision.id)
        .where(
            Priority.user_id == user_id,
            PriorityValueLink.value_revision_id.in_([vr.id for vr in value_revisions]),
            PriorityRevision.is_active == True,
        )
        .options(selectinload(Priority.active_revision))
        .distinct()
    )
    priorities = priorities_result.scalars().all()

    affected = []
    for p in priorities:
        if p.active_revision:
            affected.append(
                AffectedPriorityInfo(
                    priority_id=str(p.id),
                    title=p.active_revision.title,
                    is_anchored=p.active_revision.is_anchored,
                )
            )

    return affected
