"""
Recurrence period buckets for prerequisite alignment (next_occurrence Rule B).

A prerequisite completion counts for a dependent occurrence only when both map to
the same period key derived from the prerequisite task's RRULE.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.models.task import Task
from app.models.task_completion import TaskCompletion


def prerequisite_recurrence_period_key(
    task: Task,
    instant: datetime,
    *,
    local_date: str | None = None,
) -> str:
    """
    Stable period identifier for *task* at *instant*.

    Uses the prerequisite task's recurrence only (not the dependent's).
    For FREQ=DAILY and non-recurring tasks, prefers ``local_date`` (YYYY-MM-DD)
    when provided on a completion row so it matches the client's calendar day.
    """
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=timezone.utc)
    utc_instant = instant.astimezone(timezone.utc)
    utc_day = utc_instant.date().isoformat()

    if not task.is_recurring or not task.recurrence_rule:
        if local_date:
            return f"NDAY:{local_date}"
        return f"NDAY:{utc_day}"

    r = task.recurrence_rule.upper()
    if "FREQ=DAILY" in r:
        if local_date:
            return f"DAILY:{local_date}"
        return f"DAILY:{utc_day}"
    if "FREQ=WEEKLY" in r:
        y, w, _ = utc_instant.isocalendar()
        return f"WEEKLY:{y}-W{w:02d}"
    if "FREQ=MONTHLY" in r:
        return f"MONTHLY:{utc_instant.year}-{utc_instant.month:02d}"
    if "FREQ=YEARLY" in r:
        return f"YEARLY:{utc_instant.year}"
    if "FREQ=HOURLY" in r:
        return f"HOURLY:{utc_day}T{utc_instant.hour:02d}"
    return f"DEFAULT:{utc_day}"


def completion_matches_next_occurrence_period(
    upstream: Task,
    downstream_anchor: datetime,
    completion: TaskCompletion,
    *,
    downstream_local_date: str | None = None,
) -> bool:
    """True if prerequisite completion shares the same Rule B period as the anchor.

    The downstream occurrence may use ``local_date`` (client calendar day for the
    occurrence being completed). That must be used for the anchor key whenever
    provided, symmetrically with upstream completions that store ``local_date``;
    otherwise UTC-from-``scheduled_for`` alone can disagree after timezone or
    simulator (time machine) shifts.

    For **FREQ=DAILY** and **one-time (NDAY) upstream** tasks, when the client sends
    ``downstream_local_date``, we require a ``local_date`` on the upstream
    ``TaskCompletion``. Otherwise UTC fallback on the completion can match the wrong
    calendar day (e.g. late evening local time stored as the next UTC date), producing
    false "prerequisite met" results.
    """
    if downstream_local_date is not None and completion.local_date is None:
        r = (upstream.recurrence_rule or "").upper()
        if "FREQ=DAILY" in r:
            return False
        if not upstream.is_recurring or not upstream.recurrence_rule:
            return False

    anchor_key = prerequisite_recurrence_period_key(
        upstream, downstream_anchor, local_date=downstream_local_date
    )
    comp_time = completion.scheduled_for or completion.completed_at
    comp_key = prerequisite_recurrence_period_key(
        upstream, comp_time, local_date=completion.local_date
    )
    return anchor_key == comp_key


def filter_completions_next_occurrence_period(
    upstream: Task,
    downstream_anchor: datetime,
    completions: list[TaskCompletion],
    *,
    downstream_local_date: str | None = None,
) -> list[TaskCompletion]:
    """Keep completions whose Rule B period matches ``downstream_anchor``."""
    return [
        c
        for c in completions
        if completion_matches_next_occurrence_period(
            upstream, downstream_anchor, c, downstream_local_date=downstream_local_date
        )
    ]
