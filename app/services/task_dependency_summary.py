"""
Build compact dependency summaries for task list/detail responses (Phase 4i-5).

Avoids N+1 mobile calls to GET /tasks/{id}/dependency-status for card badges.
"""
from datetime import date, datetime, timedelta, time, timezone
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DependencyRule, TaskCompletion
from app.schemas.tasks import TaskDependencySummary
from app.services.dependency_service import check_dependencies

if TYPE_CHECKING:
    from app.models import Task

# Date-only / untimed tasks: anchor dependency windows to end of calendar day so
# same-day upstream completions satisfy completed_at < downstream_scheduled_for.
_END_OF_DAY = time(23, 59, 59, 999999)


def _dependency_scheduled_anchor(dt: datetime) -> datetime:
    """
    If the occurrence is exactly at midnight, treat like 'sometime that day' for
    within_window: otherwise completed_at < 00:00 excludes the whole day (0/N).
    """
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


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
            combined = datetime.combine(client_day, st.time(), tzinfo=st.tzinfo)
            return _dependency_scheduled_anchor(combined)
        return datetime.combine(client_day, _END_OF_DAY, tzinfo=timezone.utc)
    if task.scheduled_at:
        st = task.scheduled_at
        if st.tzinfo is None:
            st = st.replace(tzinfo=timezone.utc)
        if st.date() != client_day:
            return None
        return _dependency_scheduled_anchor(st)
    if task.scheduled_date:
        try:
            sd = datetime.strptime(task.scheduled_date, "%Y-%m-%d").date()
        except ValueError:
            return None
        if sd != client_day:
            return None
        return datetime.combine(client_day, _END_OF_DAY, tzinfo=timezone.utc)
    return datetime.combine(client_day, _END_OF_DAY, tzinfo=timezone.utc)


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
    status = await check_dependencies(
        db, task.id, user_id, scheduled_for, client_today_str
    )

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


async def build_summaries_by_task_and_dates(
    db: AsyncSession,
    user_id: str,
    tasks: list["Task"],
    client_today_str: str,
    days_ahead: int,
    days_back: int = 7,
) -> dict[str, dict[str, TaskDependencySummary]]:
    """
    For each downstream task, map local_date (YYYY-MM-DD) -> summary.

    Dates span ``client_today - days_back`` through ``client_today + days_ahead``
    inclusive (overdue + today + upcoming virtual rows).
    """
    downstream_ids = await downstream_task_ids_with_rules(db, user_id)
    start = datetime.strptime(client_today_str, "%Y-%m-%d").date()
    date_strings: list[str] = []
    for i in range(-max(0, days_back), max(0, days_ahead) + 1):
        date_strings.append((start + timedelta(days=i)).isoformat())

    out: dict[str, dict[str, TaskDependencySummary]] = {}
    for t in tasks:
        if t.id not in downstream_ids:
            continue
        per_date: dict[str, TaskDependencySummary] = {}
        for ds in date_strings:
            per_date[ds] = await build_task_dependency_summary(
                db, user_id, t, ds
            )
        out[t.id] = per_date
    return out


async def build_summaries_for_tasks(
    db: AsyncSession,
    user_id: str,
    tasks: list["Task"],
    client_today_str: str,
) -> dict[str, TaskDependencySummary]:
    """Batch summaries for list responses; only tasks with downstream rules (today only)."""
    by_task = await build_summaries_by_task_and_dates(
        db, user_id, tasks, client_today_str, 0, days_back=0
    )
    return {tid: per[client_today_str] for tid, per in by_task.items()}
