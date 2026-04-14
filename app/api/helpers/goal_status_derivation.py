"""
Derive goal workflow status from the active task / subgoal tree.

Status is persisted on ``Goal`` but only recomputed for ``record_state == active``.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utc_now
from app.models import Goal, Task, TaskCompletion
from app.record_state import ACTIVE
from app.api.helpers.goal_helpers import apply_goal_status


async def _load_active_subgoals(db: AsyncSession, parent_id: str) -> list[Goal]:
    result = await db.execute(
        select(Goal).where(
            Goal.parent_goal_id == parent_id,
            Goal.record_state == ACTIVE,
        )
    )
    return list(result.scalars().all())


async def _load_active_tasks(db: AsyncSession, goal_id: str) -> list[Task]:
    result = await db.execute(
        select(Task).where(
            Task.goal_id == goal_id,
            Task.record_state == ACTIVE,
        )
    )
    return list(result.scalars().all())


async def _subtree_has_active_task(db: AsyncSession, goal_id: str) -> bool:
    tasks = await _load_active_tasks(db, goal_id)
    if tasks:
        return True
    for sg in await _load_active_subgoals(db, goal_id):
        if await _subtree_has_active_task(db, sg.id):
            return True
    return False


async def _recurring_task_has_completed_occurrence(
    db: AsyncSession, task_id: str
) -> bool:
    stmt = (
        select(func.count())
        .select_from(TaskCompletion)
        .where(
            TaskCompletion.task_id == task_id,
            TaskCompletion.status == "completed",
        )
    )
    result = await db.execute(stmt)
    n = int(result.scalar_one() or 0)
    return n > 0


def _direct_tasks_satisfied_for_completion(tasks: list[Task]) -> bool:
    """Direct tasks on this goal satisfy the completion layer (strict)."""
    if not tasks:
        return True
    non_recurring = [t for t in tasks if not t.is_recurring]
    recurring = [t for t in tasks if t.is_recurring]
    if non_recurring:
        return all(t.status == "completed" for t in non_recurring)
    if recurring:
        return False
    return True


async def _work_started_on_direct_tasks(db: AsyncSession, tasks: list[Task]) -> bool:
    for t in tasks:
        if not t.is_recurring and t.status == "completed":
            return True
        if t.is_recurring and await _recurring_task_has_completed_occurrence(db, t.id):
            return True
    return False


async def compute_derived_goal_status(db: AsyncSession, goal_id: str) -> str:
    """Return ``not_started`` | ``in_progress`` | ``completed`` for a goal id."""
    g_row = await db.execute(select(Goal).where(Goal.id == goal_id))
    goal = g_row.scalar_one_or_none()
    if goal is None:
        return "not_started"
    if (goal.record_state or "active") != ACTIVE:
        return str(goal.status)

    subs = await _load_active_subgoals(db, goal_id)
    tasks = await _load_active_tasks(db, goal_id)
    child_statuses = [await compute_derived_goal_status(db, s.id) for s in subs]

    is_completed = await _goal_is_completed(
        db, subs, tasks, child_statuses
    )
    if is_completed:
        return "completed"

    if await _goal_is_in_progress(db, subs, tasks, child_statuses):
        return "in_progress"
    return "not_started"


async def _goal_is_completed(
    db: AsyncSession,
    subs: list[Goal],
    tasks: list[Task],
    child_statuses: list[str],
) -> bool:
    if subs:
        for sg, cst in zip(subs, child_statuses, strict=True):
            if cst != "completed":
                return False
            if not await _subtree_has_active_task(db, sg.id):
                return False
        return _direct_tasks_satisfied_for_completion(tasks)

    if not tasks:
        return False
    return _direct_tasks_satisfied_for_completion(tasks)


async def _goal_is_in_progress(
    db: AsyncSession,
    subs: list[Goal],
    tasks: list[Task],
    child_statuses: list[str],
) -> bool:
    if any(s in ("in_progress", "completed") for s in child_statuses):
        return True
    if await _work_started_on_direct_tasks(db, tasks):
        return True
    return False


async def persist_goal_derived_status(db: AsyncSession, goal_id: str) -> None:
    """Recompute and persist status for one goal (active goals only)."""
    g_row = await db.execute(select(Goal).where(Goal.id == goal_id))
    goal = g_row.scalar_one_or_none()
    if goal is None:
        return
    if (goal.record_state or "active") != ACTIVE:
        return
    new_status = await compute_derived_goal_status(db, goal_id)
    if new_status != goal.status:
        apply_goal_status(goal, new_status, utc_now())


async def recompute_goal_status_ancestors(
    db: AsyncSession, goal_id: str | None
) -> None:
    """Walk from ``goal_id`` up to the root, persisting derived status."""
    if goal_id is None:
        return
    cur: str | None = goal_id
    seen: set[str] = set()
    while cur is not None and cur not in seen:
        seen.add(cur)
        await persist_goal_derived_status(db, cur)
        prow = await db.execute(
            select(Goal.parent_goal_id).where(Goal.id == cur)
        )
        cur = prow.scalar_one_or_none()
