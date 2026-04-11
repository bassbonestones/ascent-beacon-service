"""
Build compact dependency summaries for task list/detail responses (Phase 4i-5).

Avoids N+1 mobile calls to GET /tasks/{id}/dependency-status for card badges.
"""
from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DependencyRule, TaskCompletion
from app.schemas.tasks import TaskDependencySummary
from app.services.dependency_service import check_dependencies

if TYPE_CHECKING:
    from app.models import Task


async def downstream_task_ids_with_rules(db: AsyncSession, user_id: str) -> set[str]:
    """Task IDs that appear as downstream on at least one dependency rule."""
    stmt = (
        select(DependencyRule.downstream_task_id)
        .where(DependencyRule.user_id == user_id)
        .distinct()
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.fetchall()}


def _occurrence_scheduled_for(task: "Task", client_day: date) -> datetime | None:
    """Best-effort scheduled_for for dependency checks on client_day."""
    if task.is_recurring:
        if task.scheduled_at:
            st = task.scheduled_at
            if st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
            return datetime.combine(client_day, st.time(), tzinfo=st.tzinfo)
        return datetime.combine(client_day, time.min, tzinfo=timezone.utc)
    if task.scheduled_at:
        st = task.scheduled_at
        if st.tzinfo is None:
            st = st.replace(tzinfo=timezone.utc)
        if st.date() != client_day:
            return None
        return st
    if task.scheduled_date:
        try:
            sd = datetime.strptime(task.scheduled_date, "%Y-%m-%d").date()
        except ValueError:
            return None
        if sd != client_day:
            return None
        return datetime.combine(client_day, time.min, tzinfo=timezone.utc)
    return datetime.combine(client_day, time.min, tzinfo=timezone.utc)


async def _upstream_skipped_on_local_date(
    db: AsyncSession,
    upstream_task_id: str,
    local_date_str: str,
) -> bool:
    day = datetime.strptime(local_date_str, "%Y-%m-%d").date()
    stmt = (
        select(TaskCompletion.id)
        .where(
            TaskCompletion.task_id == upstream_task_id,
            TaskCompletion.status == "skipped",
            or_(
                TaskCompletion.local_date == local_date_str,
                and_(
                    TaskCompletion.local_date.is_(None),
                    func.date(TaskCompletion.scheduled_for) == day,
                ),
            ),
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def build_task_dependency_summary(
    db: AsyncSession,
    user_id: str,
    task: "Task",
    client_today_str: str,
) -> TaskDependencySummary:
    """Compute summary for one task on the client's local calendar day."""
    scheduled_for = _occurrence_scheduled_for(
        task, datetime.strptime(client_today_str, "%Y-%m-%d").date()
    )
    status = await check_dependencies(db, task.id, user_id, scheduled_for)

    advisory_parts: list[str] = []
    for blocker in status.dependencies:
        if blocker.strength == "soft" and not blocker.is_met:
            skipped = await _upstream_skipped_on_local_date(
                db, blocker.upstream_task.id, client_today_str
            )
            suffix = "Skipped today" if skipped else "Not completed yet"
            advisory_parts.append(f"{blocker.upstream_task.title} · {suffix}")

    advisory_text: str | None = None
    if advisory_parts:
        advisory_text = "Usually follows: " + "; ".join(advisory_parts)

    return TaskDependencySummary(
        readiness_state=status.readiness_state,
        has_unmet_hard=status.has_unmet_hard,
        has_unmet_soft=status.has_unmet_soft,
        advisory_text=advisory_text,
    )


async def build_summaries_for_tasks(
    db: AsyncSession,
    user_id: str,
    tasks: list["Task"],
    client_today_str: str,
) -> dict[str, TaskDependencySummary]:
    """Batch summaries for list responses; only tasks with downstream rules."""
    downstream_ids = await downstream_task_ids_with_rules(db, user_id)
    out: dict[str, TaskDependencySummary] = {}
    for t in tasks:
        if t.id not in downstream_ids:
            continue
        out[t.id] = await build_task_dependency_summary(db, user_id, t, client_today_str)
    return out
