"""Goal archive preview and commit (Phase 4j)."""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.models import Goal, Task
from app.record_state import ACTIVE, ARCHIVED, PAUSED


async def collect_subtree_goal_ids(
    db: AsyncSession, root_goal_id: str, user_id: str
) -> list[str]:
    """BFS: root and all descendant goals owned by user."""
    collected: list[str] = []
    frontier: list[str] = [root_goal_id]
    while frontier:
        collected.extend(frontier)
        result = await db.execute(
            select(Goal.id).where(
                Goal.parent_goal_id.in_(frontier),
                Goal.user_id == user_id,
            )
        )
        frontier = [row[0] for row in result.all()]
    return collected


async def affected_tasks_for_archive(
    db: AsyncSession, subtree_goal_ids: list[str], user_id: str
) -> list[Task]:
    """Tasks that need resolution before archiving the goal subtree."""
    if not subtree_goal_ids:
        return []
    result = await db.execute(
        select(Task)
        .where(
            Task.user_id == user_id,
            Task.goal_id.in_(subtree_goal_ids),
            Task.record_state == ACTIVE,
            Task.status == "pending",
        )
        .order_by(Task.created_at)
    )
    return list(result.scalars().all())


async def assert_target_goal_for_reassign(
    db: AsyncSession,
    goal_id: str,
    user_id: str,
    forbidden_ids: frozenset[str],
) -> Goal:
    result = await db.execute(
        select(Goal).where(Goal.id == goal_id, Goal.user_id == user_id)
    )
    g = result.scalar_one_or_none()
    if not g:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reassign target goal not found",
        )
    if g.id in forbidden_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot reassign into the subtree being archived",
        )
    if g.record_state != ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reassign target goal must be active",
        )
    return g


def apply_task_resolution(
    task: Task,
    action: str,
    reassign_goal_id: str | None,
    now: datetime,
) -> None:
    if action == "reassign":
        if not reassign_goal_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="reassign requires goal_id",
            )
        task.goal_id = reassign_goal_id
        task.unaligned_execution_acknowledged_at = None
    elif action == "keep_unaligned":
        task.goal_id = None
        task.unaligned_execution_acknowledged_at = now
    elif action == "pause_task":
        task.record_state = PAUSED
    elif action == "archive_task":
        task.record_state = ARCHIVED
    else:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Invalid task resolution action: {action}",
        )
    task.updated_at = now


async def archive_goal_subtree(
    db: AsyncSession,
    *,
    root_goal: Goal,
    subtree_ids: list[str],
    tracking_mode: str,
    now: datetime,
) -> None:
    """Set archived on root (with tracking) and descendants."""
    for gid in subtree_ids:
        result = await db.execute(select(Goal).where(Goal.id == gid))
        g = result.scalar_one()
        g.record_state = ARCHIVED
        g.archived_at = now
        g.updated_at = now
        if gid == root_goal.id:
            g.archive_tracking_mode = tracking_mode
        else:
            g.archive_tracking_mode = None
