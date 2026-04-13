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
from app.models import Goal, Task
from app.record_state import ACTIVE, DELETED, PAUSED
from app.schemas.goals import (
    ArchiveGoalRequest,
    ArchivePreviewResponse,
    ArchivePreviewTaskItem,
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
    get_active_goal_or_404,
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
from app.api.helpers.goal_archive_helpers import (
    affected_tasks_for_archive,
    apply_task_resolution,
    archive_goal_subtree,
    assert_target_goal_for_reassign,
    collect_subtree_goal_ids,
)
from app.api.helpers.task_helpers import update_goal_progress
from sqlalchemy import select

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
        await get_active_goal_or_404(db, request.parent_goal_id, user.id)

    # Create goal
    goal = Goal(
        user_id=user.id,
        parent_goal_id=request.parent_goal_id,
        title=request.title,
        description=request.description,
        target_date=request.target_date,
        status="not_started",
        record_state="active",
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
    include_paused: bool = Query(
        default=False, description="Include goals with record_state=paused"
    ),
    include_archived: bool = Query(
        default=False, description="Include goals with record_state=archived"
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
        include_paused=include_paused,
        include_archived=include_archived,
    )
    reschedule_count = await get_reschedule_count(db, user.id)

    return GoalListResponse(
        goals=[goal_to_response(g) for g in goals],
        reschedule_count=reschedule_count,
    )


@router.get(
    "/{goal_id}/archive-preview",
    response_model=ArchivePreviewResponse,
    summary="Preview goal archive (tasks requiring resolution)",
)
async def preview_goal_archive(
    goal_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ArchivePreviewResponse:
    """List tasks that must be resolved before archiving this goal subtree."""
    await get_active_goal_or_404(db, goal_id, user.id)
    subtree = await collect_subtree_goal_ids(db, goal_id, user.id)
    affected = await affected_tasks_for_archive(db, subtree, user.id)
    return ArchivePreviewResponse(
        goal_id=goal_id,
        subtree_goal_ids=subtree,
        tasks_requiring_resolution=[
            ArchivePreviewTaskItem(
                task_id=t.id,
                goal_id=t.goal_id,
                title=t.title,
            )
            for t in affected
        ],
    )


@router.post(
    "/{goal_id}/archive",
    response_model=GoalResponse,
    summary="Archive goal subtree (terminal)",
)
async def commit_goal_archive(
    goal_id: str,
    request: ArchiveGoalRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoalResponse:
    """Archive this goal and descendants; apply mandatory per-task resolutions first."""
    root = await get_active_goal_or_404(db, goal_id, user.id)
    subtree = await collect_subtree_goal_ids(db, goal_id, user.id)
    forbidden = frozenset(subtree)
    affected = await affected_tasks_for_archive(db, subtree, user.id)
    required = {t.id for t in affected}
    incoming = {r.task_id for r in request.task_resolutions}
    if required != incoming:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="task_resolutions must match the preview task set exactly",
        )

    now = utc_now()
    goals_to_refresh: set[str | None] = set()

    for res in request.task_resolutions:
        tr_result = await db.execute(
            select(Task).where(Task.id == res.task_id, Task.user_id == user.id)
        )
        task = tr_result.scalar_one_or_none()
        if not task or task.id not in required:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid task in resolutions: {res.task_id}",
            )
        old_gid = task.goal_id
        if res.action == "reassign":
            if not res.goal_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="reassign requires goal_id",
                )
            await assert_target_goal_for_reassign(
                db, res.goal_id, user.id, forbidden
            )
        apply_task_resolution(task, res.action, res.goal_id, now)
        goals_to_refresh.add(old_gid)
        goals_to_refresh.add(task.goal_id)

    await archive_goal_subtree(
        db,
        root_goal=root,
        subtree_ids=subtree,
        tracking_mode=request.tracking_mode,
        now=now,
    )
    await db.flush()

    for gid in goals_to_refresh:
        await update_goal_progress(db, gid)

    await db.commit()
    reloaded = await reload_goal_with_eager_loading(db, goal_id)
    return goal_to_response(reloaded)


@router.post(
    "/{goal_id}/pause",
    response_model=GoalResponse,
    summary="Pause goal",
)
async def pause_goal(
    goal_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoalResponse:
    """Pause an active goal (reversible with /unpause)."""
    goal = await get_active_goal_or_404(db, goal_id, user.id)
    goal.record_state = PAUSED
    goal.updated_at = utc_now()
    await db.commit()
    reloaded = await reload_goal_with_eager_loading(db, goal_id)
    return goal_to_response(reloaded)


@router.post(
    "/{goal_id}/unpause",
    response_model=GoalResponse,
    summary="Unpause goal",
)
async def unpause_goal(
    goal_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> GoalResponse:
    """Restore a paused goal to active (archived goals cannot be unpaused)."""
    goal = await get_goal_or_404(db, goal_id, user.id)
    if goal.record_state != PAUSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Goal is not paused",
        )
    goal.record_state = ACTIVE
    goal.updated_at = utc_now()
    await db.commit()
    reloaded = await reload_goal_with_eager_loading(db, goal_id)
    return goal_to_response(reloaded)


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
    goal = await get_active_goal_or_404(db, goal_id, user.id)

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
    goal = await get_active_goal_or_404(db, goal_id, user.id)
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
    """Delete goal with soft/hard lifecycle rules."""
    goal = await get_goal_or_404(db, goal_id, user.id)
    # Child goals are soft-deleted while parent structure still exists.
    # Root goals are hard-deleted (cascade) to physically purge no-longer-needed subtree data.
    if goal.parent_goal_id:
        subtree = await collect_subtree_goal_ids(db, goal_id, user.id)
        now = utc_now()
        for gid in subtree:
            g_result = await db.execute(
                select(Goal).where(Goal.id == gid, Goal.user_id == user.id)
            )
            sub_goal = g_result.scalar_one_or_none()
            if sub_goal:
                sub_goal.record_state = DELETED
                sub_goal.updated_at = now

            t_result = await db.execute(
                select(Task).where(Task.goal_id == gid, Task.user_id == user.id)
            )
            for task in t_result.scalars().all():
                task.record_state = DELETED
                task.updated_at = now
    else:
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
    goal = await get_active_goal_or_404(db, goal_id, user.id)

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
    goal = await get_active_goal_or_404(db, goal_id, user.id)

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
    await get_active_goal_or_404(db, goal_id, user.id)
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
