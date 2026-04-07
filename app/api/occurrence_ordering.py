"""
Occurrence Ordering API endpoints.

Provides endpoints for reordering untimed task occurrences in Today/Upcoming views.
Supports both one-time daily overrides and permanent preferences.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, delete, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.core.time import utc_now
from app.models import Task
from app.models.occurrence_preference import OccurrencePreference
from app.models.daily_sort_override import DailySortOverride
from app.schemas.occurrence_ordering import (
    ReorderOccurrencesRequest,
    ReorderOccurrencesResponse,
    DayOrderResponse,
    DayOrderItem,
    DateRangeOrderResponse,
    PermanentOrderItem,
    DateOverrideItem,
)

router = APIRouter(prefix="/tasks", tags=["task-ordering"])


@router.post(
    "/reorder-occurrences",
    response_model=ReorderOccurrencesResponse,
    summary="Reorder task occurrences for a day",
    description="""
    Reorder untimed task occurrences for a specific date.
    
    **save_mode options:**
    - `today`: Creates one-time overrides for this date only
    - `permanent`: Updates persistent preferences that apply to all future days
    
    The occurrences list should be in desired order (first item = position 1, etc.).
    """,
)
async def reorder_occurrences(
    request: ReorderOccurrencesRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReorderOccurrencesResponse:
    """Reorder task occurrences for a specific date."""
    
    # Validate all task IDs belong to user
    task_ids = [occ.task_id for occ in request.occurrences]
    stmt = select(Task).where(
        and_(Task.id.in_(task_ids), Task.user_id == user.id)
    )
    result = await db.execute(stmt)
    valid_tasks = {task.id for task in result.scalars().all()}
    
    invalid_tasks = set(task_ids) - valid_tasks
    if invalid_tasks:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tasks not found: {', '.join(invalid_tasks)}",
        )
    
    if request.save_mode == "today":
        await _save_daily_overrides(db, user.id, request)
    else:  # permanent
        await _save_permanent_preferences(db, user.id, request)
    
    await db.commit()
    
    return ReorderOccurrencesResponse(
        save_mode=request.save_mode,
        date=request.date,
        count=len(request.occurrences),
    )


async def _save_daily_overrides(
    db: AsyncSession, user_id: str, request: ReorderOccurrencesRequest
) -> None:
    """Save one-time daily overrides for the specified date."""
    
    # Delete existing overrides for this date
    await db.execute(
        delete(DailySortOverride).where(
            and_(
                DailySortOverride.user_id == user_id,
                DailySortOverride.override_date == request.date,
            )
        )
    )
    
    # Create new overrides
    for position, occ in enumerate(request.occurrences, start=1):
        override = DailySortOverride(
            user_id=user_id,
            task_id=occ.task_id,
            occurrence_index=occ.occurrence_index,
            override_date=request.date,
            sort_position=position,
        )
        db.add(override)


async def _save_permanent_preferences(
    db: AsyncSession, user_id: str, request: ReorderOccurrencesRequest
) -> None:
    """Save permanent preferences for recurring tasks, daily overrides for single tasks.
    
    This is a hybrid save: recurring tasks get permanent preferences that apply to
    all future occurrences, while single (non-recurring) tasks get daily overrides
    since they only appear on one day.
    
    When saving permanent preferences for recurring tasks, any existing daily overrides
    for those tasks on this date are removed so the permanent preferences take effect.
    """
    import logging
    logger = logging.getLogger(__name__)
    
    # First, determine which tasks are recurring
    task_ids = [occ.task_id for occ in request.occurrences]
    stmt = select(Task.id, Task.is_recurring).where(Task.id.in_(task_ids))
    result = await db.execute(stmt)
    task_recurring_map = {row.id: row.is_recurring for row in result.all()}
    
    logger.info(f"[HYBRID SAVE] task_recurring_map: {task_recurring_map}")
    
    # Separate recurring and single tasks
    recurring_occs = []
    single_occs = []
    for occ in request.occurrences:
        if task_recurring_map.get(occ.task_id, False):
            recurring_occs.append(occ)
        else:
            single_occs.append(occ)
    
    logger.info(f"[HYBRID SAVE] recurring_occs: {[(o.task_id, o.occurrence_index) for o in recurring_occs]}")
    logger.info(f"[HYBRID SAVE] single_occs: {[(o.task_id, o.occurrence_index) for o in single_occs]}")
    
    now = utc_now()
    
    # Save permanent preferences for recurring tasks
    if recurring_occs:
        recurring_task_ids = [occ.task_id for occ in recurring_occs]
        
        # Delete any existing daily overrides for recurring tasks on this date
        # This ensures permanent preferences take effect without being overshadowed
        await db.execute(
            delete(DailySortOverride).where(
                and_(
                    DailySortOverride.user_id == user_id,
                    DailySortOverride.override_date == request.date,
                    DailySortOverride.task_id.in_(recurring_task_ids),
                )
            )
        )
        logger.info(f"[HYBRID SAVE] Deleted daily overrides for recurring tasks on {request.date}")
        
        # Get existing preferences for recurring task/occurrence combos
        stmt = select(OccurrencePreference).where(
            and_(
                OccurrencePreference.user_id == user_id,
                OccurrencePreference.task_id.in_(recurring_task_ids),
            )
        )
        result = await db.execute(stmt)
        existing_prefs = {
            (p.task_id, p.occurrence_index): p for p in result.scalars().all()
        }
        
        # Assign sequence numbers based on position in full list (preserves order)
        for occ in recurring_occs:
            position = next(
                i for i, o in enumerate(request.occurrences, start=1)
                if o.task_id == occ.task_id and o.occurrence_index == occ.occurrence_index
            )
            key = (occ.task_id, occ.occurrence_index)
            sequence_number = float(position)
            
            if key in existing_prefs:
                pref = existing_prefs[key]
                pref.sequence_number = sequence_number
                pref.updated_at = now
            else:
                pref = OccurrencePreference(
                    user_id=user_id,
                    task_id=occ.task_id,
                    occurrence_index=occ.occurrence_index,
                    sequence_number=sequence_number,
                    created_at=now,
                    updated_at=now,
                )
                db.add(pref)
    
    # Save daily overrides for single (non-recurring) tasks
    if single_occs:
        # Delete existing overrides for single tasks on this date
        single_task_ids = [occ.task_id for occ in single_occs]
        await db.execute(
            delete(DailySortOverride).where(
                and_(
                    DailySortOverride.user_id == user_id,
                    DailySortOverride.override_date == request.date,
                    DailySortOverride.task_id.in_(single_task_ids),
                )
            )
        )
        
        # Create new overrides for single tasks
        for occ in single_occs:
            position = next(
                i for i, o in enumerate(request.occurrences, start=1)
                if o.task_id == occ.task_id and o.occurrence_index == occ.occurrence_index
            )
            override = DailySortOverride(
                user_id=user_id,
                task_id=occ.task_id,
                occurrence_index=occ.occurrence_index,
                override_date=request.date,
                sort_position=position,
            )
            db.add(override)


@router.get(
    "/occurrence-order",
    response_model=DayOrderResponse,
    summary="Get task occurrence order for a day",
    description="""
    Get the effective ordering for task occurrences on a specific date.
    
    Returns items sorted by their effective sort value.
    `is_override=True` means the value comes from a daily override,
    `is_override=False` means it comes from permanent preferences.
    
    When both daily overrides and permanent preferences exist (hybrid save),
    both are returned and merged. The frontend should use sort_value to order.
    
    Tasks not in either table will not be returned - frontend should
    fall back to default ordering (e.g., created_at) for those.
    """,
)
async def get_day_order(
    date: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DayOrderResponse:
    """Get task occurrence order for a specific date."""
    
    # Get daily overrides for this date
    overrides_stmt = select(DailySortOverride).where(
        and_(
            DailySortOverride.user_id == user.id,
            DailySortOverride.override_date == date,
        )
    ).order_by(DailySortOverride.sort_position)
    
    overrides_result = await db.execute(overrides_stmt)
    overrides = list(overrides_result.scalars().all())
    
    # Get permanent preferences
    prefs_stmt = select(OccurrencePreference).where(
        OccurrencePreference.user_id == user.id
    ).order_by(OccurrencePreference.sequence_number)
    
    prefs_result = await db.execute(prefs_stmt)
    prefs = list(prefs_result.scalars().all())
    
    items: list[DayOrderItem] = []
    has_overrides = len(overrides) > 0
    
    # Track which task/occurrence pairs have overrides
    override_keys = set()
    
    # Add all overrides
    for override in overrides:
        override_keys.add((override.task_id, override.occurrence_index))
        items.append(DayOrderItem(
            task_id=override.task_id,
            occurrence_index=override.occurrence_index,
            sort_value=float(override.sort_position),
            is_override=True,
        ))
    
    # Add permanent preferences that don't have overrides
    for pref in prefs:
        if (pref.task_id, pref.occurrence_index) not in override_keys:
            items.append(DayOrderItem(
                task_id=pref.task_id,
                occurrence_index=pref.occurrence_index,
                sort_value=pref.sequence_number,
                is_override=False,
            ))
    
    # Sort by sort_value to maintain correct order
    items.sort(key=lambda x: x.sort_value)
    
    return DayOrderResponse(
        date=date,
        items=items,
        has_overrides=has_overrides,
    )


@router.delete(
    "/occurrence-order/{date}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear daily overrides for a date",
    description="Remove all daily sort overrides for a specific date, reverting to permanent preferences.",
)
async def clear_day_order(
    date: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Clear daily overrides for a specific date."""
    
    await db.execute(
        delete(DailySortOverride).where(
            and_(
                DailySortOverride.user_id == user.id,
                DailySortOverride.override_date == date,
            )
        )
    )
    await db.commit()


@router.get(
    "/occurrence-order/range",
    response_model=DateRangeOrderResponse,
    summary="Get task occurrence order for a date range",
    description="""
    Get ordering info for a range of dates in a single request.
    
    Returns:
    - permanent_order: Preferences that apply to all dates
    - daily_overrides: Dict mapping dates to their overrides (only dates with overrides are included)
    
    The frontend should:
    1. For a given date, check if daily_overrides has entries for that date
    2. If yes, use those overrides (they take precedence)
    3. If no, use permanent_order
    """,
)
async def get_date_range_order(
    start_date: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
    end_date: Annotated[str, Query(pattern=r"^\d{4}-\d{2}-\d{2}$")],
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DateRangeOrderResponse:
    """Get task occurrence order for a date range."""
    
    # Get all permanent preferences for this user
    prefs_stmt = select(OccurrencePreference).where(
        OccurrencePreference.user_id == user.id
    ).order_by(OccurrencePreference.sequence_number)
    
    prefs_result = await db.execute(prefs_stmt)
    prefs = list(prefs_result.scalars().all())
    
    permanent_order = [
        PermanentOrderItem(
            task_id=p.task_id,
            occurrence_index=p.occurrence_index,
            sequence_number=p.sequence_number,
        )
        for p in prefs
    ]
    
    # Get daily overrides within the date range
    overrides_stmt = select(DailySortOverride).where(
        and_(
            DailySortOverride.user_id == user.id,
            DailySortOverride.override_date >= start_date,
            DailySortOverride.override_date <= end_date,
        )
    ).order_by(DailySortOverride.override_date, DailySortOverride.sort_position)
    
    overrides_result = await db.execute(overrides_stmt)
    overrides = list(overrides_result.scalars().all())
    
    # Group overrides by date
    daily_overrides: dict[str, list[DateOverrideItem]] = {}
    for override in overrides:
        date_key = override.override_date
        if date_key not in daily_overrides:
            daily_overrides[date_key] = []
        daily_overrides[date_key].append(
            DateOverrideItem(
                task_id=override.task_id,
                occurrence_index=override.occurrence_index,
                sort_position=override.sort_position,
            )
        )
    
    return DateRangeOrderResponse(
        start_date=start_date,
        end_date=end_date,
        permanent_order=permanent_order,
        daily_overrides=daily_overrides,
    )
