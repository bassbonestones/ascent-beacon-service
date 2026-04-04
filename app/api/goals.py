"""
Goals API endpoints.

Provides CRUD operations for goals and management of priority links.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.core.db import get_db
from app.core.time import utc_now
from app.models import Goal
from app.schemas.goals import (
    CreateGoalRequest,
    GoalListResponse,
    GoalResponse,
    GoalWithSubGoalsResponse,
    RescheduleGoalsRequest,
    SetPriorityLinksRequest,
    UpdateGoalRequest,
    UpdateGoalStatusRequest,
)
from app.api.helpers.goal_helpers import (
    get_goal_or_404,
    reload_goal_with_eager_loading,
    goal_to_response,
    create_priority_links,
    get_reschedule_count,
    check_priority_link_exists,
    delete_priority_link,
    validate_goal_status,
    build_goal_tree,
    list_goals_query,
    apply_goal_status,
    validate_parent_goal,
    reschedule_goals_bulk,
)

router = APIRouter(prefix="/goals", tags=["goals"])


@router.post(
    "",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create goal",
)
async def create_goal(
    request: CreateGoalRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoalResponse:
    """Create a new goal, optionally linked to priorities and/or as a sub-goal."""
    # Validate parent goal if specified
    if request.parent_goal_id:
        await get_goal_or_404(db, request.parent_goal_id, user.id)

    # Create goal
    goal = Goal(
        user_id=user.id,
        parent_goal_id=request.parent_goal_id,
        title=request.title,
        description=request.description,
        target_date=request.target_date,
        status="not_started",
    )
    db.add(goal)
    await db.flush()

    # Create priority links
    if request.priority_ids:
        await create_priority_links(db, goal.id, user.id, request.priority_ids)

    await db.commit()
    goal = await reload_goal_with_eager_loading(db, goal.id)
    return goal_to_response(goal)


@router.get("", response_model=GoalListResponse, summary="List goals")
async def list_goals(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    priority_id: str | None = Query(default=None, description="Filter by priority"),
    status_filter: str | None = Query(
        default=None, alias="status", description="Filter by status"
    ),
    include_completed: bool = Query(
        default=False, description="Include completed goals"
    ),
    parent_only: bool = Query(
        default=False, description="Only return root goals (no parent)"
    ),
    past_target_date: bool = Query(
        default=False, description="Only return goals past target date"
    ),
) -> GoalListResponse:
    """Get all goals for the current user, with optional filters."""
    goals = await list_goals_query(
        db,
        user.id,
        priority_id=priority_id,
        status_filter=status_filter,
        include_completed=include_completed,
        parent_only=parent_only,
        past_target_date=past_target_date,
    )
    reschedule_count = await get_reschedule_count(db, user.id)

    return GoalListResponse(
        goals=[goal_to_response(g) for g in goals],
        reschedule_count=reschedule_count,
    )


@router.get("/{goal_id}", response_model=GoalResponse, summary="Get goal")
async def get_goal(
    goal_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoalResponse:
    """Get a goal by ID."""
    goal = await get_goal_or_404(db, goal_id, user.id)
    return goal_to_response(goal)


@router.get(
    "/{goal_id}/tree",
    response_model=GoalWithSubGoalsResponse,
    summary="Get goal with full tree",
)
async def get_goal_tree(
    goal_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoalWithSubGoalsResponse:
    """Get a goal with its full sub-goal tree."""
    goal = await get_goal_or_404(db, goal_id, user.id)
    return await build_goal_tree(db, goal)


@router.patch("/{goal_id}", response_model=GoalResponse, summary="Update goal")
async def update_goal(
    goal_id: str,
    request: UpdateGoalRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoalResponse:
    """Update a goal's fields."""
    goal = await get_goal_or_404(db, goal_id, user.id)

    if request.parent_goal_id is not None:
        await validate_parent_goal(db, goal_id, request.parent_goal_id, user.id)
        goal.parent_goal_id = request.parent_goal_id

    if request.title is not None:
        goal.title = request.title
    if request.description is not None:
        goal.description = request.description
    if request.target_date is not None:
        goal.target_date = request.target_date
    if request.status is not None:
        validate_goal_status(request.status)
        apply_goal_status(goal, request.status, utc_now())

    goal.updated_at = utc_now()
    await db.commit()
    goal = await reload_goal_with_eager_loading(db, goal.id)
    return goal_to_response(goal)


@router.patch(
    "/{goal_id}/status",
    response_model=GoalResponse,
    summary="Update goal status",
)
async def update_goal_status(
    goal_id: str,
    request: UpdateGoalStatusRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoalResponse:
    """Quick endpoint to update just the goal status."""
    goal = await get_goal_or_404(db, goal_id, user.id)
    apply_goal_status(goal, request.status, utc_now())
    goal.updated_at = utc_now()
    await db.commit()
    goal = await reload_goal_with_eager_loading(db, goal.id)
    return goal_to_response(goal)


@router.delete(
    "/{goal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete goal",
)
async def delete_goal(
    goal_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Delete a goal and all its sub-goals (cascade)."""
    goal = await get_goal_or_404(db, goal_id, user.id)
    await db.delete(goal)
    await db.commit()


@router.post(
    "/{goal_id}/priorities",
    response_model=GoalResponse,
    summary="Set goal's priority links",
)
async def set_goal_priorities(
    goal_id: str,
    request: SetPriorityLinksRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoalResponse:
    """Replace all priority links for a goal."""
    goal = await get_goal_or_404(db, goal_id, user.id)

    # Remove existing links
    for link in goal.priority_links:
        await db.delete(link)
    await db.flush()

    # Create new links
    await create_priority_links(db, goal.id, user.id, request.priority_ids)

    await db.commit()
    goal = await reload_goal_with_eager_loading(db, goal.id)
    return goal_to_response(goal)


@router.post(
    "/{goal_id}/priorities/{priority_id}",
    response_model=GoalResponse,
    summary="Add priority link",
)
async def add_goal_priority(
    goal_id: str,
    priority_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoalResponse:
    """Add a single priority link to a goal."""
    goal = await get_goal_or_404(db, goal_id, user.id)

    if await check_priority_link_exists(db, goal_id, priority_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Priority already linked to this goal",
        )

    await create_priority_links(db, goal.id, user.id, [priority_id])

    await db.commit()
    goal = await reload_goal_with_eager_loading(db, goal.id)
    return goal_to_response(goal)


@router.delete(
    "/{goal_id}/priorities/{priority_id}",
    response_model=GoalResponse,
    summary="Remove priority link",
)
async def remove_goal_priority(
    goal_id: str,
    priority_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoalResponse:
    """Remove a priority link from a goal."""
    await get_goal_or_404(db, goal_id, user.id)
    await delete_priority_link(db, goal_id, priority_id)
    await db.commit()

    goal = await reload_goal_with_eager_loading(db, goal_id)
    return goal_to_response(goal)


@router.post(
    "/reschedule",
    response_model=GoalListResponse,
    summary="Reschedule multiple goals",
)
async def reschedule_goals(
    request: RescheduleGoalsRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoalListResponse:
    """Reschedule multiple goals at once."""
    goal_updates = [(item.goal_id, item.new_target_date) for item in request.goal_updates]
    results = await reschedule_goals_bulk(db, user.id, goal_updates, utc_now())
    return GoalListResponse(goals=results, reschedule_count=0)
