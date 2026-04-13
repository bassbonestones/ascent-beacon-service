"""
Build compact dependency summaries for task list/detail responses (Phase 4i-5).

Avoids N+1 mobile calls to GET /tasks/{id}/dependency-status for card badges.
Per calendar day, summaries are keyed by intraday slot (see intraday_occurrence_anchors).
"""
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DependencyRule, Task, TaskCompletion
from app.schemas.tasks import TaskDependencySummary
from app.services.dependency_service import check_dependencies
from app.services.intraday_downstream_slot_fill import (
    completions_for_task_local_date,
    downstream_has_sequential_slot_hard_dependency,
    first_pending_slot_index,
)
from app.services.intraday_occurrence_anchors import list_dependency_anchors_for_day
from app.record_state import ACTIVE

if TYPE_CHECKING:
    from app.models import Task


async def downstream_task_ids_with_rules(db: AsyncSession, user_id: str) -> set[str]:
    """Task IDs that appear as downstream on at least one dependency rule."""
    stmt = (
        select(DependencyRule.downstream_task_id)
        .join(Task, Task.id == DependencyRule.downstream_task_id)
        .where(DependencyRule.user_id == user_id)
        .where(Task.record_state == ACTIVE)
        .distinct()
    )
    result = await db.execute(stmt)
    return {row[0] for row in result.fetchall()}


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


async def _summary_for_anchor(
    db: AsyncSession,
    user_id: str,
    task: "Task",
    local_date_str: str,
    scheduled_for: datetime | None,
) -> TaskDependencySummary:
    status = await check_dependencies(
        db, task.id, user_id, scheduled_for, local_date_str
    )

    advisory_parts: list[str] = []
    for blocker in status.dependencies:
        if blocker.strength == "soft" and not blocker.is_met:
            skipped = await _upstream_skipped_on_local_date(
                db, blocker.upstream_task.id, local_date_str
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


async def build_task_dependency_summaries_for_day(
    db: AsyncSession,
    user_id: str,
    task: "Task",
    local_date_str: str,
    client_timezone: str | None,
) -> dict[str, TaskDependencySummary]:
    """
    Map slot_key -> summary for one local calendar day.

    slot_key matches mobile virtual row ("" for single-slot days, else "0730", "occ1", ...).
    """
    client_day = datetime.strptime(local_date_str, "%Y-%m-%d").date()
    anchors = list_dependency_anchors_for_day(task, client_day, client_timezone)
    if not anchors:
        return {"": await _summary_for_anchor(db, user_id, task, local_date_str, None)}

    out: dict[str, TaskDependencySummary] = {}
    for slot_key, scheduled_for in anchors:
        out[slot_key] = await _summary_for_anchor(
            db, user_id, task, local_date_str, scheduled_for
        )

    if len(anchors) > 1 and await downstream_has_sequential_slot_hard_dependency(
        db, user_id, task.id
    ):
        rows = await completions_for_task_local_date(db, task.id, local_date_str)
        fp = first_pending_slot_index(anchors, rows, client_timezone)
        if fp is not None:
            for i, (slot_key, _) in enumerate(anchors):
                if i <= fp:
                    continue
                s = out[slot_key]
                if not s.has_unmet_hard:
                    out[slot_key] = TaskDependencySummary(
                        readiness_state="blocked",
                        has_unmet_hard=True,
                        has_unmet_soft=s.has_unmet_soft,
                        advisory_text=s.advisory_text,
                    )
    return out


def first_slot_summary(per_slot: dict[str, TaskDependencySummary]) -> TaskDependencySummary | None:
    """Top-level dependency_summary: first slot in insertion order (matches list UI)."""
    if not per_slot:
        return None
    return next(iter(per_slot.values()))


async def build_task_dependency_summary(
    db: AsyncSession,
    user_id: str,
    task: "Task",
    client_today_str: str,
    client_timezone: str | None = None,
) -> TaskDependencySummary:
    """Single summary for one task on one day (first intraday slot). Tests / legacy."""
    per = await build_task_dependency_summaries_for_day(
        db, user_id, task, client_today_str, client_timezone
    )
    return first_slot_summary(per) or TaskDependencySummary(
        readiness_state="ready",
        has_unmet_hard=False,
        has_unmet_soft=False,
        advisory_text=None,
    )


async def build_summaries_by_task_and_dates(
    db: AsyncSession,
    user_id: str,
    tasks: list["Task"],
    client_today_str: str,
    days_ahead: int,
    days_back: int = 7,
    client_timezone: str | None = None,
) -> dict[str, dict[str, dict[str, TaskDependencySummary]]]:
    """
    For each downstream task, map local_date -> slot_key -> summary.

    Dates span ``client_today - days_back`` through ``client_today + days_ahead``
    inclusive (overdue + today + upcoming virtual rows).
    """
    downstream_ids = await downstream_task_ids_with_rules(db, user_id)
    start = datetime.strptime(client_today_str, "%Y-%m-%d").date()
    date_strings: list[str] = []
    for i in range(-max(0, days_back), max(0, days_ahead) + 1):
        date_strings.append((start + timedelta(days=i)).isoformat())

    out: dict[str, dict[str, dict[str, TaskDependencySummary]]] = {}
    for t in tasks:
        if t.id not in downstream_ids:
            continue
        per_date: dict[str, dict[str, TaskDependencySummary]] = {}
        for ds in date_strings:
            per_date[ds] = await build_task_dependency_summaries_for_day(
                db, user_id, t, ds, client_timezone
            )
        out[t.id] = per_date
    return out


async def build_summaries_for_tasks(
    db: AsyncSession,
    user_id: str,
    tasks: list["Task"],
    client_today_str: str,
    client_timezone: str | None = None,
) -> dict[str, TaskDependencySummary]:
    """Batch summaries for list responses; only tasks with downstream rules (today only)."""
    by_task = await build_summaries_by_task_and_dates(
        db, user_id, tasks, client_today_str, 0, days_back=0, client_timezone=client_timezone
    )
    fallback = TaskDependencySummary(
        readiness_state="ready",
        has_unmet_hard=False,
        has_unmet_soft=False,
        advisory_text=None,
    )
    out: dict[str, TaskDependencySummary] = {}
    for tid, per in by_task.items():
        inner = per.get(client_today_str, {})
        fs = first_slot_summary(inner)
        out[tid] = fs if fs is not None else fallback
    return out
