from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.models import ValuePrompt, UserValueSelection
from app.schemas.discovery import (
    DiscoveryPromptsResponse,
    ValuePromptResponse,
    UserValueSelectionCreate,
    UserValueSelectionUpdate,
    UserValueSelectionResponse,
    UserSelectionsResponse,
    BulkSelectionsUpdate,
)

router = APIRouter(prefix="/discovery", tags=["discovery"])


@router.get("/prompts", response_model=DiscoveryPromptsResponse, summary="Get discovery prompts")
async def get_discovery_prompts(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DiscoveryPromptsResponse:
    """Get all active value discovery prompts."""
    result = await db.execute(
        select(ValuePrompt)
        .where(ValuePrompt.active == True)
        .order_by(ValuePrompt.primary_lens, ValuePrompt.display_order)
    )
    prompts = result.scalars().all()
    return DiscoveryPromptsResponse(prompts=[ValuePromptResponse.model_validate(p) for p in prompts])


@router.get("/selections", response_model=UserSelectionsResponse, summary="Get user selections")
async def get_user_selections(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSelectionsResponse:
    """Get user's current value selections."""
    result = await db.execute(
        select(UserValueSelection)
        .where(UserValueSelection.user_id == user.id)
        .options(selectinload(UserValueSelection.prompt))
        .order_by(UserValueSelection.bucket, UserValueSelection.display_order)
    )
    selections = result.scalars().all()
    return UserSelectionsResponse(
        selections=[UserValueSelectionResponse.model_validate(s) for s in selections]
    )


@router.post("/selections", response_model=UserValueSelectionResponse, summary="Create selection")
async def create_selection(
    selection: UserValueSelectionCreate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserValueSelectionResponse:
    """Add a new value selection."""
    # Check if selection already exists
    existing = await db.execute(
        select(UserValueSelection).where(
            UserValueSelection.user_id == user.id,
            UserValueSelection.prompt_id == selection.prompt_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Selection already exists")
    
    new_selection = UserValueSelection(
        user_id=user.id,
        prompt_id=selection.prompt_id,
        bucket=selection.bucket,
        display_order=selection.display_order,
        custom_text=selection.custom_text,
    )
    db.add(new_selection)
    await db.commit()
    await db.refresh(new_selection)
    
    # Load with prompt
    result = await db.execute(
        select(UserValueSelection)
        .where(UserValueSelection.id == new_selection.id)
        .options(selectinload(UserValueSelection.prompt))
    )
    loaded = result.scalar_one()
    return UserValueSelectionResponse.model_validate(loaded)


@router.put("/selections/{selection_id}", response_model=UserValueSelectionResponse, summary="Update selection")
async def update_selection(
    selection_id: str,
    update: UserValueSelectionUpdate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserValueSelectionResponse:
    """Update a value selection (change bucket or order)."""
    result = await db.execute(
        select(UserValueSelection)
        .where(
            UserValueSelection.id == selection_id,
            UserValueSelection.user_id == user.id,
        )
    )
    selection = result.scalar_one_or_none()
    if not selection:
        raise HTTPException(status_code=404, detail="Selection not found")
    
    if update.bucket is not None:
        selection.bucket = update.bucket
    if update.display_order is not None:
        selection.display_order = update.display_order
    
    await db.commit()
    await db.refresh(selection)
    
    # Load with prompt
    result = await db.execute(
        select(UserValueSelection)
        .where(UserValueSelection.id == selection.id)
        .options(selectinload(UserValueSelection.prompt))
    )
    loaded = result.scalar_one()
    return UserValueSelectionResponse.model_validate(loaded)


@router.delete("/selections/{selection_id}", summary="Delete selection")
async def delete_selection(
    selection_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict[str, str]:
    """Remove a value selection."""
    result = await db.execute(
        select(UserValueSelection).where(
            UserValueSelection.id == selection_id,
            UserValueSelection.user_id == user.id,
        )
    )
    selection = result.scalar_one_or_none()
    if not selection:
        raise HTTPException(status_code=404, detail="Selection not found")
    
    await db.delete(selection)
    await db.commit()
    return {"status": "deleted"}


@router.post("/selections/bulk", response_model=UserSelectionsResponse, summary="Bulk update selections")
async def bulk_update_selections(
    bulk: BulkSelectionsUpdate,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSelectionsResponse:
    """Bulk update all selections (used for drag-and-drop reordering)."""
    # Delete all existing selections
    await db.execute(
        select(UserValueSelection).where(UserValueSelection.user_id == user.id)
    )
    await db.execute(
        delete(UserValueSelection).where(
            UserValueSelection.user_id == user.id
        )
    )
    
    # Create new selections
    new_selections = [
        UserValueSelection(
            user_id=user.id,
            prompt_id=sel.prompt_id,
            bucket=sel.bucket,
            display_order=sel.display_order,
            custom_text=sel.custom_text,
        )
        for sel in bulk.selections
    ]
    db.add_all(new_selections)
    await db.commit()
    
    # Return updated list
    result = await db.execute(
        select(UserValueSelection)
        .where(UserValueSelection.user_id == user.id)
        .options(selectinload(UserValueSelection.prompt))
        .order_by(UserValueSelection.bucket, UserValueSelection.display_order)
    )
    selections = result.scalars().all()
    return UserSelectionsResponse(
        selections=[UserValueSelectionResponse.model_validate(s) for s in selections]
    )
