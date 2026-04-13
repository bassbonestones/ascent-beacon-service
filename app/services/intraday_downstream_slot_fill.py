"""
Intraday downstream slot fill order for dependency list badges.

When a hard ``next_occurrence`` / ``within_window`` prerequisite is shared across
same-calendar intraday slots, only the first *pending* slot should read as ready:
later slots stay ``has_unmet_hard`` until earlier slots are completed (upstream
consumption semantics).

Hard ``all_occurrences`` uses a period gate: once every prerequisite occurrence
in the period is satisfied, every downstream slot in that period is independently
ready, so this masking must **not** apply for all-occurrences-only hard rules.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from app.models.dependency import DependencyRule
from app.models.task_completion import TaskCompletion

if TYPE_CHECKING:
    pass


def _safe_zone(name: str | None) -> ZoneInfo | timezone:
    if not name:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def _normalize(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _anchors_share_identical_scheduled_for(
    anchors: list[tuple[str, datetime]],
) -> bool:
    if len(anchors) < 2:
        return False
    first = _normalize(anchors[0][1])
    return all(
        abs((_normalize(sf) - first).total_seconds()) < 2.0 for _, sf in anchors[1:]
    )


def _same_wall_minute(
    a: datetime,
    b: datetime,
    client_timezone: str | None,
) -> bool:
    zi = _safe_zone(client_timezone)
    if isinstance(zi, ZoneInfo):
        la = _normalize(a).astimezone(zi)
        lb = _normalize(b).astimezone(zi)
    else:
        la = _normalize(a).astimezone(timezone.utc)
        lb = _normalize(b).astimezone(timezone.utc)
    return (la.year, la.month, la.day, la.hour, la.minute) == (
        lb.year,
        lb.month,
        lb.day,
        lb.hour,
        lb.minute,
    )


async def downstream_has_hard_dependency(
    db: AsyncSession,
    user_id: str,
    downstream_task_id: str,
) -> bool:
    stmt = (
        select(DependencyRule.id)
        .where(
            DependencyRule.downstream_task_id == downstream_task_id,
            DependencyRule.user_id == user_id,
            DependencyRule.strength == "hard",
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def downstream_has_sequential_slot_hard_dependency(
    db: AsyncSession,
    user_id: str,
    downstream_task_id: str,
) -> bool:
    """
    True when intraday first-pending-slot masking should run.

    Masking matches upstream *consumption* across downstream slots (hard
    ``next_occurrence`` / ``within_window``). Hard ``all_occurrences`` does not
    consume prerequisite completions across downstream slots in the same period,
    so tasks with only all-occurrences hard rules must not get later slots forced
    to ``blocked`` in list summaries.
    """
    stmt = (
        select(DependencyRule.id)
        .where(
            DependencyRule.downstream_task_id == downstream_task_id,
            DependencyRule.user_id == user_id,
            DependencyRule.strength == "hard",
            DependencyRule.scope.in_(("next_occurrence", "within_window")),
        )
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def completions_for_task_local_date(
    db: AsyncSession,
    task_id: str,
    local_date_str: str,
) -> list[TaskCompletion]:
    """Completed/skipped rows for ``local_date_str``, oldest first."""
    day = date.fromisoformat(local_date_str)
    stmt = (
        select(TaskCompletion)
        .where(
            TaskCompletion.task_id == task_id,
            TaskCompletion.status.in_(["completed", "skipped"]),
            or_(
                TaskCompletion.local_date == local_date_str,
                and_(
                    TaskCompletion.local_date.is_(None),
                    func.date(TaskCompletion.scheduled_for) == day,
                ),
            ),
        )
        .order_by(TaskCompletion.completed_at.asc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


def first_pending_slot_index(
    anchors: list[tuple[str, datetime]],
    completions: list[TaskCompletion],
    client_timezone: str | None,
) -> int | None:
    """
    Index of the first intraday slot not filled for ``local_date_str``.

    Returns ``None`` if every slot is filled or there is only one anchor.
    """
    n = len(anchors)
    if n <= 1:
        return None
    filled = [False] * n
    same_time = _anchors_share_identical_scheduled_for(anchors)

    if same_time:
        for idx in range(min(len(completions), n)):
            filled[idx] = True
    else:
        used: set[int] = set()
        for c in completions:
            cdt = c.scheduled_for or c.completed_at
            if cdt is None:
                continue
            for i, (_, anchor_dt) in enumerate(anchors):
                if i in used or filled[i]:
                    continue
                if _same_wall_minute(cdt, anchor_dt, client_timezone):
                    used.add(i)
                    filled[i] = True
                    break

    for i in range(n):
        if not filled[i]:
            return i
    return None


def unfilled_anchor_indices(
    anchors: list[tuple[str, datetime]],
    completions: list[TaskCompletion],
    client_timezone: str | None,
) -> list[int]:
    """
    Slot indices (0..n-1) that do not yet have a matching completion for this day.

    Used by complete-chain to synthesize multiple upstream TaskCompletion rows for
    ``all_occurrences`` rules with ``required_occurrence_count`` > 1.
    """
    n = len(anchors)
    if n == 0:
        return []
    filled = [False] * n
    same_time = _anchors_share_identical_scheduled_for(anchors)
    if same_time:
        for idx in range(min(len(completions), n)):
            filled[idx] = True
    else:
        used: set[int] = set()
        for c in completions:
            cdt = c.scheduled_for or c.completed_at
            if cdt is None:
                continue
            for i, (_, anchor_dt) in enumerate(anchors):
                if i in used or filled[i]:
                    continue
                if _same_wall_minute(cdt, anchor_dt, client_timezone):
                    used.add(i)
                    filled[i] = True
                    break
    return [i for i in range(n) if not filled[i]]
