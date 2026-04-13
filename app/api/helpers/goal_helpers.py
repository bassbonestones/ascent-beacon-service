"""
Helper functions for Goals API endpoints.
"""
from datetime import date, datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Goal, GoalPriorityLink, Priority
from app.schemas.goals import GoalResponse, GoalWithSubGoalsResponse, PriorityInfo
from app.record_state import DELETED, list_query_states


def _goal_str_field(goal: object, name: str, default: str | None) -> str | None:
    v = getattr(goal, name, default)
    if isinstance(v, str):
        return v
    return default


def _goal_dt_field(goal: object, name: str) -> datetime | None:
    if not hasattr(goal, name):
        return None
    v = getattr(goal, name)
    if v is None:
        return None
    if isinstance(v, datetime):
        return v
    return None


async def get_goal_or_404(
    db: AsyncSession, goal_id: str, user_id: str
) -> Goal:
    """Get a goal by ID, or raise 404 if not found or not owned by user."""
    result = await db.execute(
        select(Goal)
        .where(Goal.id == goal_id, Goal.user_id == user_id)
        .options(
            selectinload(Goal.priority_links)
            .selectinload(GoalPriorityLink.priority)
            .selectinload(Priority.active_revision)
        )
    )
    goal = result.scalar_one_or_none()
    if not goal:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found",
        )
    if (_goal_str_field(goal, "record_state", "active") or "active") == DELETED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Goal not found",
        )
    return goal


async def get_active_goal_or_404(
    db: AsyncSession, goal_id: str, user_id: str
) -> Goal:
    """Goal must exist, belong to user, and be ``record_state == active``."""
    from app.record_state import ACTIVE

    goal = await get_goal_or_404(db, goal_id, user_id)
    if (_goal_str_field(goal, "record_state", "active") or "active") != ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Goal is not active",
        )
    return goal


async def reload_goal_with_eager_loading(db: AsyncSession, goal_id: str) -> Goal:
    """Reload a goal with all relationships eagerly loaded."""
    result = await db.execute(
        select(Goal)
        .where(Goal.id == goal_id)
        .options(
            selectinload(Goal.priority_links)
            .selectinload(GoalPriorityLink.priority)
            .selectinload(Priority.active_revision)
        )
        .execution_options(populate_existing=True)
    )
    return result.scalar_one()


def _extract_priorities_from_goal(goal: Goal) -> list[PriorityInfo]:
    """Extract priority info list from goal's priority links."""
    priorities = []
    for link in goal.priority_links:
        if link.priority and link.priority.active_revision:
            priorities.append(
                PriorityInfo(
                    id=link.priority.id,
                    title=link.priority.active_revision.title,
                    score=link.priority.active_revision.score,
                )
            )
        elif link.priority:
            priorities.append(
                PriorityInfo(
                    id=link.priority.id,
                    title="(No active revision)",
                    score=None,
                )
            )
    return priorities


def goal_to_response(goal: Goal) -> GoalResponse:
    """Convert a Goal model to GoalResponse schema."""
    pr = _extract_priorities_from_goal(goal)
    return GoalResponse(
        id=goal.id,
        user_id=goal.user_id,
        parent_goal_id=goal.parent_goal_id,
        title=goal.title,
        description=goal.description,
        target_date=goal.target_date,
        status=goal.status,
        progress_cached=goal.progress_cached,
        total_time_minutes=goal.total_time_minutes,
        completed_time_minutes=goal.completed_time_minutes,
        has_incomplete_breakdown=goal.has_incomplete_breakdown,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
        completed_at=goal.completed_at,
        record_state=_goal_str_field(goal, "record_state", "active") or "active",
        archived_at=_goal_dt_field(goal, "archived_at"),
        archive_tracking_mode=_goal_str_field(goal, "archive_tracking_mode", None),
        is_aligned_with_priorities=len(pr) > 0,
        priorities=pr,
    )


def goal_to_tree_response(goal: Goal, sub_goals: list["GoalWithSubGoalsResponse"]) -> GoalWithSubGoalsResponse:
    """Convert a Goal model to GoalWithSubGoalsResponse schema."""
    pr = _extract_priorities_from_goal(goal)
    return GoalWithSubGoalsResponse(
        id=goal.id,
        user_id=goal.user_id,
        parent_goal_id=goal.parent_goal_id,
        title=goal.title,
        description=goal.description,
        target_date=goal.target_date,
        status=goal.status,
        progress_cached=goal.progress_cached,
        total_time_minutes=goal.total_time_minutes,
        completed_time_minutes=goal.completed_time_minutes,
        has_incomplete_breakdown=goal.has_incomplete_breakdown,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
        completed_at=goal.completed_at,
        record_state=_goal_str_field(goal, "record_state", "active") or "active",
        archived_at=_goal_dt_field(goal, "archived_at"),
        archive_tracking_mode=_goal_str_field(goal, "archive_tracking_mode", None),
        is_aligned_with_priorities=len(pr) > 0,
        priorities=pr,
        sub_goals=sub_goals,
    )


async def create_priority_links(
    db: AsyncSession, goal_id: str, user_id: str, priority_ids: list[str]
) -> None:
    """Create links between a goal and priorities."""
    for priority_id in priority_ids:
        result = await db.execute(
            select(Priority).where(
                Priority.id == priority_id, Priority.user_id == user_id
            )
        )
        priority = result.scalar_one_or_none()
        if not priority:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Priority {priority_id} not found",
            )
        link = GoalPriorityLink(goal_id=goal_id, priority_id=priority_id)
        db.add(link)


async def get_reschedule_count(db: AsyncSession, user_id: str) -> int:
    """Count goals past target date that need rescheduling."""
    from app.record_state import ACTIVE

    result = await db.execute(
        select(Goal).where(
            Goal.user_id == user_id,
            Goal.record_state == ACTIVE,
            Goal.target_date < date.today(),
            Goal.status.notin_(["completed", "abandoned"]),
        )
    )
    return len(result.scalars().all())


async def check_priority_link_exists(
    db: AsyncSession, goal_id: str, priority_id: str
) -> bool:
    """Check if a goal-priority link already exists."""
    result = await db.execute(
        select(GoalPriorityLink).where(
            GoalPriorityLink.goal_id == goal_id,
            GoalPriorityLink.priority_id == priority_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def delete_priority_link(
    db: AsyncSession, goal_id: str, priority_id: str
) -> None:
    """Delete a goal-priority link, raising 404 if not found."""
    result = await db.execute(
        select(GoalPriorityLink).where(
            GoalPriorityLink.goal_id == goal_id,
            GoalPriorityLink.priority_id == priority_id,
        )
    )
    link = result.scalar_one_or_none()
    if not link:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Priority link not found",
        )
    await db.delete(link)


VALID_GOAL_STATUSES = ["not_started", "in_progress", "completed", "abandoned"]


def validate_goal_status(status_value: str) -> None:
    """Validate that a status value is valid."""
    if status_value not in VALID_GOAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status. Must be one of: {VALID_GOAL_STATUSES}",
        )


def apply_goal_status(goal: Goal, new_status: str, now: "datetime") -> None:
    """Apply a status change to a goal, updating completed_at as needed."""
    goal.status = new_status
    if new_status == "completed" and not goal.completed_at:
        goal.completed_at = now
    elif new_status != "completed":
        goal.completed_at = None


async def validate_parent_goal(
    db: AsyncSession, goal_id: str, parent_goal_id: str | None, user_id: str
) -> None:
    """Validate that a parent goal change is valid."""
    if parent_goal_id:
        if parent_goal_id == goal_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Goal cannot be its own parent",
            )
        await get_active_goal_or_404(db, parent_goal_id, user_id)


async def reschedule_goals_bulk(
    db: AsyncSession,
    user_id: str,
    goal_updates: list[tuple[str, "date"]],
    now: "datetime",
) -> list[GoalResponse]:
    """Reschedule multiple goals and return their responses."""
    updated_goals = []
    for goal_id, new_date in goal_updates:
        goal = await get_active_goal_or_404(db, goal_id, user_id)
        goal.target_date = new_date
        goal.updated_at = now
        updated_goals.append(goal)

    await db.commit()

    results = []
    for goal in updated_goals:
        goal = await reload_goal_with_eager_loading(db, goal.id)
        results.append(goal_to_response(goal))
    return results


async def build_goal_tree(
    db: AsyncSession, goal: Goal
) -> GoalWithSubGoalsResponse:
    """Recursively build a goal tree with sub-goals."""
    result = await db.execute(
        select(Goal)
        .where(Goal.parent_goal_id == goal.id)
        .options(
            selectinload(Goal.priority_links)
            .selectinload(GoalPriorityLink.priority)
            .selectinload(Priority.active_revision)
        )
        .order_by(Goal.created_at)
    )
    sub_goals = result.scalars().all()
    children = [await build_goal_tree(db, sg) for sg in sub_goals]
    return goal_to_tree_response(goal, children)


async def list_goals_query(
    db: AsyncSession,
    user_id: str,
    priority_id: str | None = None,
    status_filter: str | None = None,
    include_completed: bool = False,
    parent_only: bool = False,
    past_target_date: bool = False,
    *,
    include_paused: bool = False,
    include_archived: bool = False,
) -> list[Goal]:
    """Build and execute goal list query with filters."""
    states = list_query_states(
        include_paused=include_paused, include_archived=include_archived
    )
    query = (
        select(Goal)
        .where(Goal.user_id == user_id, Goal.record_state.in_(states))
        .options(
            selectinload(Goal.priority_links)
            .selectinload(GoalPriorityLink.priority)
            .selectinload(Priority.active_revision)
        )
    )

    if not include_completed:
        query = query.where(Goal.status.notin_(["completed", "abandoned"]))

    if status_filter:
        query = query.where(Goal.status == status_filter)

    if parent_only:
        query = query.where(Goal.parent_goal_id.is_(None))

    if past_target_date:
        today = date.today()
        query = query.where(
            Goal.target_date < today,
            Goal.status.notin_(["completed", "abandoned"]),
        )

    if priority_id:
        query = query.join(GoalPriorityLink).where(
            GoalPriorityLink.priority_id == priority_id
        )

    query = query.order_by(Goal.created_at.desc())

    result = await db.execute(query)
    return list(result.scalars().unique().all())
