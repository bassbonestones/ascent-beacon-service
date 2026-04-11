"""
Skip impact and cascade ordering for Phase 4i-4.

Evaluates whether skipping an upstream task requires confirmation due to hard
downstream rules, and produces topological order for cascade skip.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.time import utc_now
from app.models.dependency import DependencyRule
from app.models.task import Task
from app.models.task_completion import TaskCompletion
from app.services.dependency_service import (
    MAX_CHAIN_DEPTH,
    _count_qualifying_completions,
    get_upstream_recurrence_interval_minutes,
)


@dataclass(frozen=True)
class SkipImpactResult:
    """Whether skip needs confirmation and affected downstream rows."""

    needs_confirmation: bool
    affected: list[dict[str, Any]]


def _estimate_downstream_occurrences(task: Task) -> int:
    """Rough occurrence count for UI (recurring downstream)."""
    if not task.is_recurring:
        return 1
    rule = (task.recurrence_rule or "").upper()
    if "FREQ=DAILY" in rule:
        return 7
    if "FREQ=WEEKLY" in rule:
        return 1
    return 1


async def _within_window_bounds(
    db: AsyncSession,
    rule: DependencyRule,
    downstream_anchor: datetime,
) -> tuple[datetime, datetime]:
    """Window [start, end) for within_window scope (end = downstream occurrence)."""
    window_minutes = rule.validity_window_minutes
    if window_minutes is None:
        upstream_stmt = select(Task).where(Task.id == rule.upstream_task_id)
        upstream_result = await db.execute(upstream_stmt)
        upstream_task = upstream_result.scalar_one_or_none()
        if upstream_task:
            window_minutes = await get_upstream_recurrence_interval_minutes(upstream_task)
        else:
            window_minutes = 1440
    window_start = downstream_anchor - timedelta(minutes=window_minutes)
    return window_start, downstream_anchor


async def _count_upstream_actions_in_window(
    db: AsyncSession,
    upstream_task_id: str,
    window_start: datetime,
    window_end: datetime,
) -> int:
    """Completed + skipped upstream occurrences in [start, end)."""
    stmt = (
        select(func.count())
        .select_from(TaskCompletion)
        .where(
            TaskCompletion.task_id == upstream_task_id,
            TaskCompletion.scheduled_for >= window_start,
            TaskCompletion.scheduled_for < window_end,
            TaskCompletion.status.in_(["completed", "skipped"]),
        )
    )
    result = await db.execute(stmt)
    return int(result.scalar_one() or 0)


async def _max_slots_in_window(
    db: AsyncSession,
    rule: DependencyRule,
    window_start: datetime,
    window_end: datetime,
) -> int:
    """
    Upper bound on how many distinct completion opportunities exist in the window.

    Uses day buckets for daily-or-finer upstream recurrence (conservative for impossibility).
    """
    upstream_stmt = select(Task).where(Task.id == rule.upstream_task_id)
    upstream_result = await db.execute(upstream_stmt)
    upstream_task = upstream_result.scalar_one_or_none()
    if not upstream_task or not upstream_task.is_recurring:
        return max(1, (window_end - window_start).days + 1)

    interval_minutes = await get_upstream_recurrence_interval_minutes(upstream_task)
    span_minutes = max(1, int((window_end - window_start).total_seconds() // 60))
    return max(1, span_minutes // max(1, interval_minutes))


async def _task_eligible_for_hard_skip_cascade(
    db: AsyncSession,
    task: Task,
    scheduled_for: datetime | None,
    local_date: str | None,
) -> bool:
    """
    True if this task/occurrence may be cascade-skipped with the root skip anchor.

    Omits one-time tasks not in ``pending`` and recurring tasks that already have a
    completed or skipped ``TaskCompletion`` for the anchor calendar day (so reopen
    partial chains do not list still-finished downstream, e.g. C after only A,B reopen).
    """
    if not task.is_recurring:
        return task.status == "pending"

    anchor: datetime = scheduled_for if scheduled_for is not None else utc_now()
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    if local_date:
        date_key = local_date
    else:
        date_key = anchor.strftime("%Y-%m-%d")

    day = datetime.strptime(date_key, "%Y-%m-%d").date()
    day_start = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)
    day_end = day_start + timedelta(days=1)

    stmt = (
        select(func.count())
        .select_from(TaskCompletion)
        .where(
            TaskCompletion.task_id == task.id,
            TaskCompletion.status.in_(("completed", "skipped")),
            or_(
                TaskCompletion.local_date == date_key,
                and_(
                    TaskCompletion.scheduled_for.isnot(None),
                    TaskCompletion.scheduled_for >= day_start,
                    TaskCompletion.scheduled_for < day_end,
                ),
            ),
        )
    )
    result = await db.execute(stmt)
    return int(result.scalar_one() or 0) == 0


async def skip_makes_hard_rule_impossible(
    db: AsyncSession,
    rule: DependencyRule,
    scheduled_anchor: datetime,
) -> bool:
    """
    True if skipping one upstream occurrence makes required_count unattainable.

    Uses qualifying completion count + rough remaining slot capacity in window.
    """
    if rule.strength != "hard":
        return False
    if rule.required_occurrence_count <= 1:
        return False

    completed = await _count_qualifying_completions(
        db,
        rule,
        scheduled_anchor,
        completion_statuses=("completed", "skipped"),
    )
    still_needed = max(0, rule.required_occurrence_count - completed)
    if still_needed == 0:
        return False

    if rule.scope == "all_occurrences":
        # Long-horizon rule: do not block skip on impossibility heuristic here
        return False

    if rule.scope == "within_window":
        window_start, window_end = await _within_window_bounds(db, rule, scheduled_anchor)
    elif rule.scope == "next_occurrence":
        window_start = scheduled_anchor - timedelta(days=30)
        window_end = scheduled_anchor
    else:
        return False

    max_slots = await _max_slots_in_window(db, rule, window_start, window_end)
    used_actions = await _count_upstream_actions_in_window(
        db, rule.upstream_task_id, window_start, window_end
    )
    remaining_opp = max(0, max_slots - used_actions)
    return (remaining_opp - 1) < still_needed


async def evaluate_skip_hard_downstream_impact(
    db: AsyncSession,
    upstream_task_id: str,
    user_id: str,
    scheduled_for: datetime | None,
    local_date: str | None = None,
) -> SkipImpactResult:
    """
    Decide if skipping upstream_task_id requires confirmation.

    - Soft-only downstream: no confirmation.
    - Hard + required_count == 1: confirmation.
    - Hard + required_count > 1: confirmation only if skip makes rule impossible.
    """
    anchor = scheduled_for or utc_now()

    stmt = (
        select(DependencyRule)
        .options(
            selectinload(DependencyRule.downstream_task),
        )
        .where(
            DependencyRule.upstream_task_id == upstream_task_id,
            DependencyRule.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    rules = result.scalars().all()

    if not rules:
        return SkipImpactResult(needs_confirmation=False, affected=[])

    if all(r.strength == "soft" for r in rules):
        return SkipImpactResult(needs_confirmation=False, affected=[])

    affected: list[dict[str, Any]] = []
    needs_confirmation = False

    for rule in rules:
        if rule.strength != "hard":
            continue
        downstream = rule.downstream_task
        if not await _task_eligible_for_hard_skip_cascade(
            db, downstream, scheduled_for, local_date
        ):
            continue
        entry = {
            "task_id": downstream.id,
            "task_title": downstream.title,
            "rule_id": rule.id,
            "strength": rule.strength,
            "affected_occurrences": _estimate_downstream_occurrences(downstream),
        }
        if rule.required_occurrence_count == 1:
            needs_confirmation = True
            affected.append(entry)
            continue

        if await skip_makes_hard_rule_impossible(db, rule, anchor):
            needs_confirmation = True
            affected.append(entry)

    return SkipImpactResult(needs_confirmation=needs_confirmation, affected=affected)


async def build_transitive_hard_dependent_preview_rows(
    db: AsyncSession,
    start_task_id: str,
    user_id: str,
    scheduled_for: datetime | None = None,
    local_date: str | None = None,
) -> list[dict[str, Any]]:
    """
    Topo-ordered hard downstream tasks (excluding start) for skip cascade UI.

    Order matches :func:`get_transitive_hard_dependents_toposort` / skip-chain.
    """
    ids = await get_transitive_hard_dependents_toposort(
        db, start_task_id, user_id, scheduled_for, local_date
    )
    if not ids:
        return []
    stmt = select(Task).where(Task.id.in_(ids))
    result = await db.execute(stmt)
    by_id = {t.id: t for t in result.scalars().all()}
    out: list[dict[str, Any]] = []
    for tid in ids:
        t = by_id.get(tid)
        if t is None:
            continue
        out.append(
            {
                "task_id": tid,
                "task_title": t.title,
                "affected_occurrences": _estimate_downstream_occurrences(t),
            }
        )
    return out


async def get_transitive_hard_dependents_toposort(
    db: AsyncSession,
    start_task_id: str,
    user_id: str,
    scheduled_for: datetime | None = None,
    local_date: str | None = None,
) -> list[str]:
    """
    All tasks reachable via hard dependency edges downstream from start_task_id,
    in topological order (prerequisite before dependent).

    start_task_id itself is excluded from the list (caller skips it first).
    """
    # Load all hard rules for user
    stmt = select(DependencyRule).where(
        DependencyRule.user_id == user_id,
        DependencyRule.strength == "hard",
    )
    result = await db.execute(stmt)
    all_rules = result.scalars().all()

    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree: dict[str, int] = defaultdict(int)
    nodes: set[str] = set()

    for rule in all_rules:
        u, d = rule.upstream_task_id, rule.downstream_task_id
        adjacency[u].append(d)
        indegree[d] += 1
        if u not in indegree:
            indegree[u] = 0
        nodes.add(u)
        nodes.add(d)

    # BFS from start_task_id along adjacency
    reachable: set[str] = set()
    queue: deque[str] = deque([start_task_id])
    visited_bfs: set[str] = {start_task_id}
    while queue:
        cur = queue.popleft()
        for nxt in adjacency.get(cur, []):
            if nxt not in visited_bfs:
                visited_bfs.add(nxt)
                reachable.add(nxt)
                queue.append(nxt)
                if len(reachable) > MAX_CHAIN_DEPTH:
                    raise ValueError(
                        f"Hard dependent chain exceeds maximum depth of {MAX_CHAIN_DEPTH}"
                    )

    if not reachable:
        return []

    # Indegree among reachable nodes only (edges from start are excluded; start is skipped first)
    sub_indegree: dict[str, int] = {n: 0 for n in reachable}
    for u in reachable:
        for v in adjacency.get(u, []):
            if v in reachable:
                sub_indegree[v] += 1

    topo: list[str] = []
    dq: deque[str] = deque([n for n in reachable if sub_indegree[n] == 0])
    while dq:
        n = dq.popleft()
        topo.append(n)
        for v in adjacency.get(n, []):
            if v in reachable:
                sub_indegree[v] -= 1
                if sub_indegree[v] == 0:
                    dq.append(v)

    if len(topo) != len(reachable):
        raise ValueError("Cycle detected in hard dependency subgraph")

    if not topo:
        return []

    task_stmt = select(Task).where(Task.id.in_(topo))
    task_result = await db.execute(task_stmt)
    by_id = {t.id: t for t in task_result.scalars().all()}
    filtered: list[str] = []
    for tid in topo:
        t = by_id.get(tid)
        if t is None:
            continue
        if await _task_eligible_for_hard_skip_cascade(
            db, t, scheduled_for, local_date
        ):
            filtered.append(tid)
    return filtered
