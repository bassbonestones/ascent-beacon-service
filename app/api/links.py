from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.core.db import get_db
from app.core.auth import CurrentUser
from app.models.priority import PriorityRevision
from app.models.priority_value_link import PriorityValueLink
from app.schemas.links import SetLinksRequest, LinksResponse, PriorityValueLinkResponse

router = APIRouter(prefix="/priority-revisions", tags=["links"])


@router.put("/{priority_revision_id}/links", response_model=LinksResponse, summary="Set priority value links")
async def set_priority_value_links(
    priority_revision_id: str,
    request: SetLinksRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LinksResponse:
    """Set value links for a priority revision (replaces existing links)."""
    # Verify ownership
    result = await db.execute(
        select(PriorityRevision)
        .join(PriorityRevision.priority)
        .where(
            PriorityRevision.id == priority_revision_id,
            PriorityRevision.priority.has(user_id=user.id),
        )
    )
    revision = result.scalar_one_or_none()
    
    if not revision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Priority revision not found",
        )
    
    # Delete existing links
    await db.execute(
        delete(PriorityValueLink).where(
            PriorityValueLink.priority_revision_id == priority_revision_id
        )
    )
    
    # Create new links
    new_links = []
    for link_input in request.links:
        link = PriorityValueLink(
            priority_revision_id=priority_revision_id,
            value_revision_id=link_input.value_revision_id,
            link_weight=link_input.link_weight,
        )
        db.add(link)
        new_links.append(link)
    
    await db.commit()
    
    # Reload links with eager loading
    result = await db.execute(
        select(PriorityValueLink)
        .where(PriorityValueLink.priority_revision_id == priority_revision_id)
        .options(selectinload(PriorityValueLink.value_revision))
    )
    links = result.scalars().all()
    
    return LinksResponse(
        links=[PriorityValueLinkResponse.model_validate(link) for link in links]
    )


@router.get("/{priority_revision_id}/links", response_model=LinksResponse, summary="Get priority value links")
async def get_priority_value_links(
    priority_revision_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LinksResponse:
    """Get value links for a priority revision."""
    # Verify ownership
    result = await db.execute(
        select(PriorityRevision)
        .join(PriorityRevision.priority)
        .where(
            PriorityRevision.id == priority_revision_id,
            PriorityRevision.priority.has(user_id=user.id),
        )
    )
    revision = result.scalar_one_or_none()
    
    if not revision:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Priority revision not found",
        )
    
    # Get links with eager loading of value_revision
    result = await db.execute(
        select(PriorityValueLink)
        .where(PriorityValueLink.priority_revision_id == priority_revision_id)
        .options(selectinload(PriorityValueLink.value_revision))
    )
    links = result.scalars().all()
    
    return LinksResponse(
        links=[PriorityValueLinkResponse.model_validate(link) for link in links]
    )
