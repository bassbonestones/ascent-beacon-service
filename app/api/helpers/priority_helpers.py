"""Helper functions for priority API endpoints."""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.models.priority import Priority, PriorityRevision
from app.models.priority_value_link import PriorityValueLink
from app.models.value import Value
from app.schemas.priorities import PriorityResponse, LinkedValueInfo


async def get_priority_or_404(
    db: AsyncSession,
    user_id: str,
    priority_id: str,
) -> Priority:
    """
    Get a priority by ID, verifying user ownership.
    
    Raises HTTPException 404 if not found or not owned by user.
    """
    priority = await db.get(Priority, priority_id)
    if not priority or priority.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Priority not found",
        )
    return priority


async def reload_priority_with_eager_loading(
    db: AsyncSession,
    priority_id: str,
) -> Priority:
    """
    Reload a priority with all relationships eagerly loaded.
    
    Includes: revisions -> value_links -> value_revision
    """
    result = await db.execute(
        select(Priority)
        .where(Priority.id == priority_id)
        .options(
            selectinload(Priority.revisions)
            .selectinload(PriorityRevision.value_links)
            .selectinload(PriorityValueLink.value_revision)
        )
    )
    return result.scalar_one()


async def reload_priority_with_active_revision(
    db: AsyncSession,
    priority_id: str,
) -> Priority:
    """
    Reload a priority with active_revision and its value_links.
    
    Used after create/update when we only need the active revision.
    """
    result = await db.execute(
        select(Priority)
        .where(Priority.id == priority_id)
        .options(
            selectinload(Priority.active_revision)
            .selectinload(PriorityRevision.value_links)
            .selectinload(PriorityValueLink.value_revision)
        )
    )
    return result.scalar_one()


def build_priority_response(priority: Priority) -> PriorityResponse:
    """Build a PriorityResponse from a Priority model."""
    return PriorityResponse.model_validate(priority)


async def get_linked_values_for_revision(
    db: AsyncSession,
    revision_id: str,
) -> list[LinkedValueInfo]:
    """Get linked value info for a priority revision."""
    result = await db.execute(
        select(PriorityValueLink)
        .where(PriorityValueLink.priority_revision_id == revision_id)
        .options(selectinload(PriorityValueLink.value_revision))
    )
    links = result.scalars().all()
    
    linked_values = []
    for link in links:
        if link.value_revision:
            linked_values.append(
                LinkedValueInfo(
                    value_id=link.value_revision.value_id,
                    value_statement=link.value_revision.statement,
                    link_weight=link.link_weight,
                )
            )
    return linked_values


async def create_value_links(
    db: AsyncSession,
    revision_id: str,
    value_ids: list[str] | None,
) -> None:
    """Create value links for a priority revision.
    
    Links each value's active revision to the priority revision.
    """
    if not value_ids:
        return
    for value_id in value_ids:
        value = await db.get(Value, value_id)
        if value and value.active_revision_id:
            link = PriorityValueLink(
                priority_revision_id=revision_id,
                value_revision_id=value.active_revision_id,
            )
            db.add(link)


async def list_user_priorities(
    db: AsyncSession,
    user_id: str,
    stashed: bool,
) -> list[Priority]:
    """List priorities for a user, filtered by stashed status."""
    result = await db.execute(
        select(Priority)
        .where(Priority.user_id == user_id, Priority.is_stashed == stashed)
        .options(
            selectinload(Priority.active_revision)
            .selectinload(PriorityRevision.value_links)
            .selectinload(PriorityValueLink.value_revision)
        )
        .order_by(Priority.created_at)
    )
    return list(result.scalars().all())


async def get_priority_revisions(
    db: AsyncSession,
    priority_id: str,
) -> list[PriorityRevision]:
    """Get all revisions for a priority, ordered by created_at desc."""
    result = await db.execute(
        select(PriorityRevision)
        .where(PriorityRevision.priority_id == priority_id)
        .options(
            selectinload(PriorityRevision.value_links)
            .selectinload(PriorityValueLink.value_revision)
        )
        .order_by(PriorityRevision.created_at.desc())
    )
    return list(result.scalars().all())


async def validate_and_raise(title: str, why_matters: str) -> None:
    """Validate priority fields and raise HTTPException if invalid."""
    from app.services.priority_validation import validate_priority
    validation = await validate_priority(title, why_matters)
    if not validation["overall_valid"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "Priority validation failed",
                "name_feedback": validation["name_feedback"],
                "why_feedback": validation["why_feedback"],
            }
        )
