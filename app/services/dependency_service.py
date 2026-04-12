"""
Dependency resolution service for Phase 4i.

Implements occurrence-based dependency checking and resolution.
Core logic for determining if a task's dependencies are met.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, and_, delete, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement, Select
from sqlalchemy.orm import selectinload

from app.core.time import utc_now
from app.models.dependency import DependencyRule, DependencyResolution
from app.models.task import Task
from app.models.task_completion import TaskCompletion
from app.schemas.dependency import (
    DependencyBlocker,
    DependencyDependent,
    DependencyStatusResponse,
    TaskInfo,
)


# Maximum chain depth for transitive resolution (prevents pathological DAGs)
MAX_CHAIN_DEPTH = 50

# Upstream TaskCompletion statuses counted toward ``is_met`` / resolution consumption.
_COMPLETED_ONLY: tuple[str, ...] = ("completed",)
_HARD_INCLUDING_SKIPPED: tuple[str, ...] = ("completed", "skipped")


def _select_consumed_upstream_completion_ids(rule_id: str) -> Select[Any]:
    """
    Upstream completion IDs that are still ``consumed`` for this rule.

    Joins to ``TaskCompletion`` so rows whose downstream completion was removed
    (e.g. one-time reopen bulk-delete) no longer suppress upstream skips.
    """
    return (
        select(DependencyResolution.upstream_completion_id)
        .join(
            TaskCompletion,
            TaskCompletion.id == DependencyResolution.downstream_completion_id,
        )
        .where(
            DependencyResolution.dependency_rule_id == rule_id,
            DependencyResolution.upstream_completion_id.isnot(None),
        )
    )


def within_window_anchor_end(downstream_scheduled_for: datetime) -> datetime:
    """
    Right edge of the within_window interval [start, end).

    Uses ``min(downstream occurrence, now)`` so a far-future anchor (e.g. mobile
    passes end-of-day for an untimed daily task) does not force a short window to
    sit only before midnight — the last W minutes are relative to wall time when
    completing earlier the same day.
    """
    anchor = downstream_scheduled_for
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    return min(anchor, utc_now())


def _upstream_occurrence_on_or_before_anchor(
    anchor_time: datetime,
) -> ColumnElement[bool]:
    """
    Occurrence identity for next_occurrence deps: prefer scheduled slot vs wall time.

    Without this, a skip logged later the same day (completed_at after the downstream
    occurrence anchor) is wrongly ignored when scheduled_for is on/before that anchor.
    """
    return or_(
        (TaskCompletion.scheduled_for.is_not(None))
        & (TaskCompletion.scheduled_for <= anchor_time),
        TaskCompletion.scheduled_for.is_(None)
        & (TaskCompletion.completed_at <= anchor_time),
    )


async def resolve_stated_validity_window_minutes(
    db: AsyncSession,
    rule: DependencyRule,
) -> int:
    """Configured validity window: explicit minutes, else upstream recurrence default, else 1440."""
    window_minutes = rule.validity_window_minutes
    if window_minutes is None:
        upstream_stmt = select(Task).where(Task.id == rule.upstream_task_id)
        upstream_result = await db.execute(upstream_stmt)
        upstream_task = upstream_result.scalar_one_or_none()
        if upstream_task:
            window_minutes = await get_upstream_recurrence_interval_minutes(upstream_task)
        else:
            window_minutes = 1440
    return window_minutes


async def resolve_rule_validity_window_minutes(
    db: AsyncSession,
    rule: DependencyRule,
) -> int:
    """Validity window in minutes for counting (same as configured / stated resolution)."""
    return await resolve_stated_validity_window_minutes(db, rule)


async def get_upstream_recurrence_interval_minutes(task: Task) -> int:
    """
    Get the recurrence interval of a task in minutes.
    
    Used as default validity_window for WITHIN_WINDOW scope.
    """
    if not task.is_recurring or not task.recurrence_rule:
        return 1440  # Default 24 hours for non-recurring
    
    rule = task.recurrence_rule.upper()
    
    # Parse FREQ from RRULE
    if "FREQ=YEARLY" in rule:
        return 525600  # 365 days
    elif "FREQ=MONTHLY" in rule:
        return 43200  # 30 days
    elif "FREQ=WEEKLY" in rule:
        return 10080  # 7 days
    elif "FREQ=DAILY" in rule:
        return 1440  # 1 day
    elif "FREQ=HOURLY" in rule:
        return 60  # 1 hour
    else:
        return 1440  # Default to daily


async def check_dependencies(
    db: AsyncSession,
    task_id: str,
    user_id: str,
    scheduled_for: datetime | None = None,
) -> DependencyStatusResponse:
    """
    Check all dependencies for a task occurrence.
    
    Returns DependencyStatusResponse with blockers and readiness state.
    """
    # Get all rules where this task is downstream
    stmt = (
        select(DependencyRule)
        .options(selectinload(DependencyRule.upstream_task))
        .where(
            DependencyRule.downstream_task_id == task_id,
            DependencyRule.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    rules = result.scalars().all()
    
    blockers: list[DependencyBlocker] = []
    
    for rule in rules:
        statuses = (
            _HARD_INCLUDING_SKIPPED
            if rule.strength == "hard"
            else _COMPLETED_ONLY
        )
        # Count qualifying upstream completions (hard: skip counts; soft: complete only)
        completed_count = await _count_qualifying_completions(
            db, rule, scheduled_for, completion_statuses=statuses
        )

        is_met = completed_count >= rule.required_occurrence_count

        validity_window_minutes: int | None = None
        if rule.scope == "within_window":
            validity_window_minutes = await resolve_stated_validity_window_minutes(
                db, rule
            )

        upstream_info = TaskInfo(
            id=rule.upstream_task.id,
            title=rule.upstream_task.title,
            is_recurring=rule.upstream_task.is_recurring,
            recurrence_rule=rule.upstream_task.recurrence_rule,
        )

        blockers.append(
            DependencyBlocker(
                rule_id=rule.id,
                upstream_task=upstream_info,
                strength=rule.strength,
                scope=rule.scope,
                required_count=rule.required_occurrence_count,
                completed_count=completed_count,
                is_met=is_met,
                validity_window_minutes=validity_window_minutes,
            )
        )
    
    # Get dependents (what relies on this task)
    dependents_stmt = (
        select(DependencyRule)
        .options(selectinload(DependencyRule.downstream_task))
        .where(
            DependencyRule.upstream_task_id == task_id,
            DependencyRule.user_id == user_id,
        )
    )
    dep_result = await db.execute(dependents_stmt)
    dependent_rules = dep_result.scalars().all()
    
    dependents: list[DependencyDependent] = []
    for rule in dependent_rules:
        downstream_info = TaskInfo(
            id=rule.downstream_task.id,
            title=rule.downstream_task.title,
            is_recurring=rule.downstream_task.is_recurring,
            recurrence_rule=rule.downstream_task.recurrence_rule,
        )
        dependents.append(DependencyDependent(
            rule_id=rule.id,
            downstream_task=downstream_info,
            strength=rule.strength,
        ))
    
    return DependencyStatusResponse(
        task_id=task_id,
        scheduled_for=scheduled_for,
        dependencies=blockers,
        dependents=dependents,
    )


async def get_transitive_unmet_hard_prerequisites(
    db: AsyncSession,
    task_id: str,
    user_id: str,
    scheduled_for: datetime | None = None,
    depth: int = 0,
    visited: set[str] | None = None,
) -> list[DependencyBlocker]:
    """
    Unmet hard dependency chain in topological order (deepest prerequisite first).

    Matches completion-chain ordering so the UI can list the full prerequisite chain,
    not only direct edges on the target task.
    """
    if depth >= MAX_CHAIN_DEPTH:
        raise ValueError(f"Dependency chain exceeds maximum depth of {MAX_CHAIN_DEPTH}")
    if visited is None:
        visited = set()
    if task_id in visited:
        return []
    visited.add(task_id)

    status = await check_dependencies(db, task_id, user_id, scheduled_for)
    result: list[DependencyBlocker] = []

    for blocker in status.dependencies:
        if blocker.strength != "hard" or blocker.is_met:
            continue
        upstream_blockers = await get_transitive_unmet_hard_prerequisites(
            db,
            blocker.upstream_task.id,
            user_id,
            scheduled_for,
            depth + 1,
            visited,
        )
        result.extend(upstream_blockers)
        result.append(blocker)

    return result


async def _count_qualifying_completions(
    db: AsyncSession,
    rule: DependencyRule,
    downstream_scheduled_for: datetime | None,
    *,
    completion_statuses: tuple[str, ...],
) -> int:
    """
    Count upstream TaskCompletion rows that qualify for this dependency rule.

    For **hard** rules, ``completion_statuses`` includes ``skipped`` so downstream
    can complete after skipping upstream with keep-pending. **Soft** rules use
    completed-only so list advisories still reflect a skipped upstream.

    Uses scope-specific logic:
    - all_occurrences: any completion, not already consumed
    - next_occurrence: most recent unconsumed completion
    - within_window: completions within validity window
    """
    if rule.scope == "all_occurrences":
        return await _resolve_all_occurrences(db, rule, completion_statuses)
    elif rule.scope == "next_occurrence":
        return await _resolve_next_occurrence(
            db, rule, downstream_scheduled_for, completion_statuses
        )
    elif rule.scope == "within_window":
        return await _resolve_within_window(
            db, rule, downstream_scheduled_for, completion_statuses
        )
    else:
        return 0


async def _resolve_all_occurrences(
    db: AsyncSession,
    rule: DependencyRule,
    completion_statuses: tuple[str, ...],
) -> int:
    """
    Count all completed upstream occurrences (not consumed for this rule).
    
    For ALL_OCCURRENCES scope, we count all completions that haven't
    been consumed by a previous downstream completion for this same rule.
    """
    # Find all completions for upstream task
    completions_stmt = (
        select(TaskCompletion)
        .where(
            TaskCompletion.task_id == rule.upstream_task_id,
            TaskCompletion.status.in_(completion_statuses),
        )
    )
    result = await db.execute(completions_stmt)
    all_completions = result.scalars().all()

    consumed_result = await db.execute(_select_consumed_upstream_completion_ids(rule.id))
    consumed_ids = set(consumed_result.scalars().all())

    # Count unconsumed completions/skips
    return sum(1 for c in all_completions if c.id not in consumed_ids)


async def _resolve_next_occurrence(
    db: AsyncSession,
    rule: DependencyRule,
    downstream_scheduled_for: datetime | None,
    completion_statuses: tuple[str, ...],
) -> int:
    """
    Check if there's an unconsumed upstream completion for NEXT_OCCURRENCE scope.
    
    Returns 1 if there's a qualifying completion, 0 otherwise.
    For count-based dependencies, returns count of recent unconsumed completions.
    
    If downstream_scheduled_for is not provided, uses current time as anchor.
    """
    # Use provided time or current time as the anchor
    anchor_time = downstream_scheduled_for or utc_now()
    
    # Find completions that:
    # 1. Are for the upstream task
    # 2. Were completed before anchor time (or at anchor time for "now" case)
    # 3. Are not already consumed for this rule
    completions_stmt = (
        select(TaskCompletion)
        .where(
            TaskCompletion.task_id == rule.upstream_task_id,
            TaskCompletion.status.in_(completion_statuses),
            _upstream_occurrence_on_or_before_anchor(anchor_time),
        )
        .order_by(
            TaskCompletion.scheduled_for.desc().nulls_last(),
            TaskCompletion.completed_at.desc(),
        )
    )
    result = await db.execute(completions_stmt)
    completions = result.scalars().all()
    
    consumed_result = await db.execute(_select_consumed_upstream_completion_ids(rule.id))
    consumed_ids = set(consumed_result.scalars().all())

    # Count unconsumed completions/skips (up to required count)
    count = 0
    for completion in completions:
        if completion.id not in consumed_ids:
            count += 1
            if count >= rule.required_occurrence_count:
                break

    return count


async def _resolve_within_window(
    db: AsyncSession,
    rule: DependencyRule,
    downstream_scheduled_for: datetime | None,
    completion_statuses: tuple[str, ...],
) -> int:
    """
    Count upstream completions within the validity window.

    Window is [anchor_end - W, anchor_end) where anchor_end is
    ``min(downstream_scheduled_for, utc_now())`` so short windows stay meaningful
    when the client passes a far-future occurrence (e.g. end-of-day for an
    untimed daily task).
    """
    if not downstream_scheduled_for:
        return 0

    window_minutes = await resolve_rule_validity_window_minutes(db, rule)

    anchor_end = within_window_anchor_end(downstream_scheduled_for)
    window_start = anchor_end - timedelta(minutes=window_minutes)

    # Find completions within window
    completions_stmt = (
        select(TaskCompletion)
        .where(
            TaskCompletion.task_id == rule.upstream_task_id,
            TaskCompletion.status.in_(completion_statuses),
            TaskCompletion.completed_at >= window_start,
            TaskCompletion.completed_at < anchor_end,
        )
        .order_by(TaskCompletion.completed_at.desc())
    )
    result = await db.execute(completions_stmt)
    completions = result.scalars().all()
    
    consumed_result = await db.execute(_select_consumed_upstream_completion_ids(rule.id))
    consumed_ids = set(consumed_result.scalars().all())

    # Count unconsumed completions/skips
    return sum(1 for c in completions if c.id not in consumed_ids)


async def record_resolutions(
    db: AsyncSession,
    downstream_completion_id: str,
    blockers: list[DependencyBlocker],
    upstream_completion_ids: dict[str, list[str]],
    resolution_source: str = "manual",
    override_reason: str | None = None,
) -> list[DependencyResolution]:
    """
    Record resolution records for a completed task.
    
    Args:
        downstream_completion_id: ID of the downstream completion
        blockers: List of dependency blockers
        upstream_completion_ids: Dict mapping rule_id -> list of upstream completion IDs
        resolution_source: How this was resolved (manual, chain, override, system)
        override_reason: Optional reason for override
    
    Returns:
        List of created DependencyResolution records
    """
    # Re-open can delete downstream TaskCompletion rows without removing dependency_resolutions
    # (e.g. SQLite without FK enforcement). Stale rows still hit the partial unique index on
    # (dependency_rule_id, upstream_completion_id) and block re-inserting the same consumption.
    for blocker in blockers:
        for uid in upstream_completion_ids.get(blocker.rule_id, []):
            await db.execute(
                delete(DependencyResolution).where(
                    and_(
                        DependencyResolution.dependency_rule_id == blocker.rule_id,
                        DependencyResolution.upstream_completion_id == uid,
                    )
                )
            )

    resolutions: list[DependencyResolution] = []

    for blocker in blockers:
        upstream_ids = upstream_completion_ids.get(blocker.rule_id, [])
        
        if resolution_source == "override" or not upstream_ids:
            # Override case: create one resolution with no upstream
            resolution = DependencyResolution(
                dependency_rule_id=blocker.rule_id,
                downstream_completion_id=downstream_completion_id,
                upstream_completion_id=None,
                resolution_source=resolution_source,
                override_reason=override_reason if resolution_source == "override" else None,
                occurrence_index=1,
            )
            db.add(resolution)
            resolutions.append(resolution)
        else:
            # Normal case: create one resolution per consumed upstream
            for i, upstream_id in enumerate(upstream_ids, start=1):
                resolution = DependencyResolution(
                    dependency_rule_id=blocker.rule_id,
                    downstream_completion_id=downstream_completion_id,
                    upstream_completion_id=upstream_id,
                    resolution_source=resolution_source,
                    occurrence_index=i,
                )
                db.add(resolution)
                resolutions.append(resolution)
    
    return resolutions


async def get_transitive_blockers(
    db: AsyncSession,
    task_id: str,
    user_id: str,
    scheduled_for: datetime | None = None,
    depth: int = 0,
    visited: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Get full transitive prerequisite graph in topological order.
    
    Returns list of dicts with task info and blockers, ordered so that
    completing them in sequence will satisfy all dependencies.
    
    Implements max depth protection (MAX_CHAIN_DEPTH).
    """
    if depth >= MAX_CHAIN_DEPTH:
        raise ValueError(f"Dependency chain exceeds maximum depth of {MAX_CHAIN_DEPTH}")
    
    if visited is None:
        visited = set()
    
    if task_id in visited:
        return []  # Already processed (handles diamond dependencies)
    
    visited.add(task_id)
    
    # Get this task's direct blockers
    status = await check_dependencies(db, task_id, user_id, scheduled_for)
    
    result: list[dict[str, Any]] = []
    
    # Recursively get blockers for each unmet upstream
    for blocker in status.dependencies:
        if not blocker.is_met:
            upstream_blockers = await get_transitive_blockers(
                db,
                blocker.upstream_task.id,
                user_id,
                scheduled_for,
                depth + 1,
                visited,
            )
            result.extend(upstream_blockers)
            
            # Add this blocker's upstream task
            result.append({
                "task_id": blocker.upstream_task.id,
                "task_title": blocker.upstream_task.title,
                "rule_id": blocker.rule_id,
                "required_count": blocker.required_count,
                "completed_count": blocker.completed_count,
                "strength": blocker.strength,
            })
    
    return result


async def get_qualifying_upstream_ids(
    db: AsyncSession,
    rule: DependencyRule,
    downstream_scheduled_for: datetime | None,
    required_count: int,
) -> list[str]:
    """
    Get IDs of upstream completions that will be consumed for a resolution.
    
    Returns up to required_count IDs, ordered by most recent first.
    """
    statuses = (
        _HARD_INCLUDING_SKIPPED
        if rule.strength == "hard"
        else _COMPLETED_ONLY
    )
    if rule.scope == "all_occurrences":
        completions = await _get_unconsumed_completions(
            db, rule, None, None, statuses
        )
    elif rule.scope == "next_occurrence":
        completions = await _get_unconsumed_completions(
            db, rule, None, downstream_scheduled_for, statuses
        )
    elif rule.scope == "within_window":
        window_minutes = await resolve_rule_validity_window_minutes(db, rule)
        if downstream_scheduled_for:
            anchor_end = within_window_anchor_end(downstream_scheduled_for)
            window_start = anchor_end - timedelta(minutes=window_minutes)
        else:
            window_start = None
            anchor_end = None
        completions = await _get_unconsumed_completions(
            db, rule, window_start, anchor_end, statuses
        )
    else:
        completions = []

    return [c.id for c in completions[:required_count]]


async def _get_unconsumed_completions(
    db: AsyncSession,
    rule: DependencyRule,
    window_start: datetime | None,
    window_end: datetime | None,
    completion_statuses: tuple[str, ...],
) -> list[TaskCompletion]:
    """
    Get unconsumed completions/skips for a rule within optional time bounds.
    """
    conditions = [
        TaskCompletion.task_id == rule.upstream_task_id,
        TaskCompletion.status.in_(completion_statuses),
    ]

    if window_start is None and window_end is not None:
        conditions.append(_upstream_occurrence_on_or_before_anchor(window_end))
    else:
        if window_start:
            conditions.append(TaskCompletion.completed_at >= window_start)
        if window_end:
            conditions.append(TaskCompletion.completed_at < window_end)

    completions_stmt = (
        select(TaskCompletion)
        .where(and_(*conditions))
        .order_by(
            TaskCompletion.scheduled_for.desc().nulls_last(),
            TaskCompletion.completed_at.desc(),
        )
    )
    result = await db.execute(completions_stmt)
    all_completions = result.scalars().all()
    
    consumed_result = await db.execute(_select_consumed_upstream_completion_ids(rule.id))
    consumed_ids = set(consumed_result.scalars().all())

    return [c for c in all_completions if c.id not in consumed_ids]


async def check_hard_dependents(
    db: AsyncSession,
    task_id: str,
    user_id: str,
) -> list[dict[str, Any]]:
    """
    Check if skipping this task would affect hard downstream dependents.
    
    Returns list of affected downstream tasks for the skip cascade modal.
    """
    # Find rules where this task is upstream with hard strength
    stmt = (
        select(DependencyRule)
        .options(selectinload(DependencyRule.downstream_task))
        .where(
            DependencyRule.upstream_task_id == task_id,
            DependencyRule.user_id == user_id,
            DependencyRule.strength == "hard",
        )
    )
    result = await db.execute(stmt)
    rules = result.scalars().all()
    
    affected: list[dict[str, Any]] = []
    for rule in rules:
        affected.append({
            "task_id": rule.downstream_task.id,
            "task_title": rule.downstream_task.title,
            "is_recurring": rule.downstream_task.is_recurring,
            "rule_id": rule.id,
            "strength": rule.strength,
        })
    
    return affected
