from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, func
from loguru import logger

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.models import ValuePrompt, UserValueSelection, Value, ValueRevision
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


def strip_uuid_dashes(uuid_str: str) -> str:
    """Strip dashes from UUID for consistent comparison.
    
    SQLite stores UUIDs in different formats depending on how they were inserted.
    This normalizes to 32-char hex format for reliable comparison.
    """
    if not uuid_str:
        return uuid_str
    return uuid_str.replace("-", "")


@router.get("/prompts", response_model=DiscoveryPromptsResponse, summary="Get discovery prompts")
async def get_discovery_prompts(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DiscoveryPromptsResponse:
    """Get active value discovery prompts, excluding those already used by the user."""
    print(f"\n\n{'='*60}")
    print(f"GET /discovery/prompts called for user {user.id}")
    print(f"{'='*60}")
    
    # First check: How many values does this user have?
    values_result = await db.execute(
        select(Value).where(Value.user_id == user.id)
    )
    all_values = values_result.scalars().all()
    print(f"User has {len(all_values)} values total")
    
    # Check all value_revisions for this user
    all_revisions_result = await db.execute(
        select(ValueRevision.id, ValueRevision.source_prompt_id, ValueRevision.is_active, ValueRevision.statement)
        .join(Value, ValueRevision.value_id == Value.id)
        .where(Value.user_id == user.id)
    )
    all_revisions = all_revisions_result.all()
    print(f"User has {len(all_revisions)} total revisions:")
    for rev in all_revisions:
        print(f"  - id={rev[0][:8]}..., source_prompt_id={rev[1]}, is_active={rev[2]}, stmt={rev[3][:30]}...")
    
    # Get prompt IDs the user has already used for existing values
    used_prompts_result = await db.execute(
        select(ValueRevision.source_prompt_id)
        .join(Value, ValueRevision.value_id == Value.id)
        .where(
            Value.user_id == user.id,
            ValueRevision.source_prompt_id.isnot(None),
            ValueRevision.is_active == True,
        )
    )
    raw_ids = [row[0] for row in used_prompts_result.all()]
    print(f"Raw source_prompt_ids from active revisions: {raw_ids}")
    
    # Strip dashes from UUIDs for consistent comparison (SQLite stores formats inconsistently)
    used_prompt_ids = {strip_uuid_dashes(uid) for uid in raw_ids if uid}
    print(f"Stripped used_prompt_ids (32-char hex): {used_prompt_ids}")

    # Get all active prompts excluding used ones
    # Use REPLACE to strip dashes from value_prompts.id for consistent comparison
    query = select(ValuePrompt).where(ValuePrompt.active == True)
    if used_prompt_ids:
        # Compare both sides without dashes to handle format inconsistencies
        stripped_id = func.replace(ValuePrompt.id, "-", "")
        query = query.where(stripped_id.notin_(used_prompt_ids))
    query = query.order_by(ValuePrompt.primary_lens, ValuePrompt.display_order)

    result = await db.execute(query)
    prompts = result.scalars().all()
    print(f"Returning {len(prompts)} prompts (excluded {len(used_prompt_ids)})")
    print(f"{'='*60}\n\n")
    return DiscoveryPromptsResponse(prompts=[ValuePromptResponse.model_validate(p) for p in prompts])


@router.get("/selections", response_model=UserSelectionsResponse, summary="Get user selections")
async def get_user_selections(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserSelectionsResponse:
    """Get user's current value selections."""
    # Use explicit join to avoid lazy loading issues
    result = await db.execute(
        select(UserValueSelection, ValuePrompt)
        .join(ValuePrompt, UserValueSelection.prompt_id == ValuePrompt.id)
        .where(UserValueSelection.user_id == user.id)
        .order_by(UserValueSelection.bucket, UserValueSelection.display_order)
    )
    rows = result.all()
    
    # Build response with prompts attached
    response_selections = []
    for selection, prompt in rows:
        selection.prompt = prompt
        response_selections.append(UserValueSelectionResponse.model_validate(selection))
    
    return UserSelectionsResponse(selections=response_selections)


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
            UserValueSelection.prompt_id == str(selection.prompt_id),
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Selection already exists")
    
    new_selection = UserValueSelection(
        user_id=user.id,
        prompt_id=str(selection.prompt_id),
        bucket=selection.bucket,
        display_order=selection.display_order,
        custom_text=selection.custom_text,
    )
    db.add(new_selection)
    await db.commit()
    await db.refresh(new_selection)
    
    # Load with prompt via join
    result = await db.execute(
        select(UserValueSelection, ValuePrompt)
        .join(ValuePrompt, UserValueSelection.prompt_id == ValuePrompt.id)
        .where(UserValueSelection.id == new_selection.id)
    )
    row = result.one()
    loaded, prompt = row
    loaded.prompt = prompt
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
    
    # Load with prompt via join
    result = await db.execute(
        select(UserValueSelection, ValuePrompt)
        .join(ValuePrompt, UserValueSelection.prompt_id == ValuePrompt.id)
        .where(UserValueSelection.id == selection.id)
    )
    row = result.one()
    loaded, prompt = row
    loaded.prompt = prompt
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
            prompt_id=str(sel.prompt_id),
            bucket=sel.bucket,
            display_order=sel.display_order,
            custom_text=sel.custom_text,
        )
        for sel in bulk.selections
    ]
    db.add_all(new_selections)
    await db.commit()
    
    # Return updated list - need fresh session state
    # Use a new select to get all selections with their prompts via join
    result = await db.execute(
        select(UserValueSelection, ValuePrompt)
        .join(ValuePrompt, UserValueSelection.prompt_id == ValuePrompt.id)
        .where(UserValueSelection.user_id == user.id)
        .order_by(UserValueSelection.bucket, UserValueSelection.display_order)
    )
    rows = result.all()
    
    # Build response manually since we have tuples
    response_selections = []
    for selection, prompt in rows:
        selection.prompt = prompt  # Attach prompt to selection
        response_selections.append(UserValueSelectionResponse.model_validate(selection))
    
    return UserSelectionsResponse(selections=response_selections)
