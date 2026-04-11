"""
Dependency resolution service for Phase 4i.

Implements occurrence-based dependency checking and resolution.
Core logic for determining if a task's dependencies are met.
"""
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
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
        # Count qualifying upstream completions based on scope
        completed_count = await _count_qualifying_completions(
            db, rule, scheduled_for
        )
        
        is_met = completed_count >= rule.required_occurrence_count
        
        upstream_info = TaskInfo(
            id=rule.upstream_task.id,
            title=rule.upstream_task.title,
            is_recurring=rule.upstream_task.is_recurring,
            recurrence_rule=rule.upstream_task.recurrence_rule,
        )
        
        blockers.append(DependencyBlocker(
            rule_id=rule.id,
            upstream_task=upstream_info,
            strength=rule.strength,
            scope=rule.scope,
            required_count=rule.required_occurrence_count,
            completed_count=completed_count,
            is_met=is_met,
        ))
    
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


async def _count_qualifying_completions(
    db: AsyncSession,
    rule: DependencyRule,
    downstream_scheduled_for: datetime | None,
) -> int:
    """
    Count upstream completions that qualify for this dependency rule.
    
    Uses scope-specific logic:
    - all_occurrences: any completion, not already consumed
    - next_occurrence: most recent unconsumed completion
    - within_window: completions within validity window
    """
    if rule.scope == "all_occurrences":
        return await _resolve_all_occurrences(db, rule)
    elif rule.scope == "next_occurrence":
        return await _resolve_next_occurrence(db, rule, downstream_scheduled_for)
    elif rule.scope == "within_window":
        return await _resolve_within_window(db, rule, downstream_scheduled_for)
    else:
        return 0


async def _resolve_all_occurrences(
    db: AsyncSession,
    rule: DependencyRule,
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
            TaskCompletion.status == "completed",
        )
    )
    result = await db.execute(completions_stmt)
    all_completions = result.scalars().all()
    
    # Find completions already consumed for this rule
    consumed_stmt = (
        select(DependencyResolution.upstream_completion_id)
        .where(
            DependencyResolution.dependency_rule_id == rule.id,
            DependencyResolution.upstream_completion_id.isnot(None),
        )
    )
    consumed_result = await db.execute(consumed_stmt)
    consumed_ids = set(consumed_result.scalars().all())
    
    # Count unconsumed completions
    return sum(1 for c in all_completions if c.id not in consumed_ids)


async def _resolve_next_occurrence(
    db: AsyncSession,
    rule: DependencyRule,
    downstream_scheduled_for: datetime | None,
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
            TaskCompletion.status == "completed",
            TaskCompletion.completed_at <= anchor_time,
        )
        .order_by(TaskCompletion.completed_at.desc())
    )
    result = await db.execute(completions_stmt)
    completions = result.scalars().all()
    
    # Find consumed completions for this rule
    consumed_stmt = (
        select(DependencyResolution.upstream_completion_id)
        .where(
            DependencyResolution.dependency_rule_id == rule.id,
            DependencyResolution.upstream_completion_id.isnot(None),
        )
    )
    consumed_result = await db.execute(consumed_stmt)
    consumed_ids = set(consumed_result.scalars().all())
    
    # Count unconsumed completions (up to required count)
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
) -> int:
    """
    Count upstream completions within the validity window.
    
    Window is anchored to downstream occurrence time, not wall-clock NOW().
    """
    if not downstream_scheduled_for:
        return 0
    
    # Get validity window (default to upstream recurrence interval)
    window_minutes = rule.validity_window_minutes
    if window_minutes is None:
        # Load upstream task to get recurrence interval
        upstream_stmt = select(Task).where(Task.id == rule.upstream_task_id)
        upstream_result = await db.execute(upstream_stmt)
        upstream_task = upstream_result.scalar_one_or_none()
        if upstream_task:
            window_minutes = await get_upstream_recurrence_interval_minutes(upstream_task)
        else:
            window_minutes = 1440  # Default 24 hours
    
    window_start = downstream_scheduled_for - timedelta(minutes=window_minutes)
    
    # Find completions within window
    completions_stmt = (
        select(TaskCompletion)
        .where(
            TaskCompletion.task_id == rule.upstream_task_id,
            TaskCompletion.status == "completed",
            TaskCompletion.completed_at >= window_start,
            TaskCompletion.completed_at < downstream_scheduled_for,
        )
        .order_by(TaskCompletion.completed_at.desc())
    )
    result = await db.execute(completions_stmt)
    completions = result.scalars().all()
    
    # Find consumed completions for this rule
    consumed_stmt = (
        select(DependencyResolution.upstream_completion_id)
        .where(
            DependencyResolution.dependency_rule_id == rule.id,
            DependencyResolution.upstream_completion_id.isnot(None),
        )
    )
    consumed_result = await db.execute(consumed_stmt)
    consumed_ids = set(consumed_result.scalars().all())
    
    # Count unconsumed completions
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
    if rule.scope == "all_occurrences":
        completions = await _get_unconsumed_completions(db, rule, None, None)
    elif rule.scope == "next_occurrence":
        completions = await _get_unconsumed_completions(
            db, rule, None, downstream_scheduled_for
        )
    elif rule.scope == "within_window":
        window_minutes = rule.validity_window_minutes or 1440
        if downstream_scheduled_for:
            window_start = downstream_scheduled_for - timedelta(minutes=window_minutes)
        else:
            window_start = None
        completions = await _get_unconsumed_completions(
            db, rule, window_start, downstream_scheduled_for
        )
    else:
        completions = []
    
    return [c.id for c in completions[:required_count]]


async def _get_unconsumed_completions(
    db: AsyncSession,
    rule: DependencyRule,
    window_start: datetime | None,
    window_end: datetime | None,
) -> list[TaskCompletion]:
    """
    Get unconsumed completions for a rule within optional time bounds.
    """
    conditions = [
        TaskCompletion.task_id == rule.upstream_task_id,
        TaskCompletion.status == "completed",
    ]
    
    if window_start:
        conditions.append(TaskCompletion.completed_at >= window_start)
    if window_end:
        conditions.append(TaskCompletion.completed_at < window_end)
    
    completions_stmt = (
        select(TaskCompletion)
        .where(and_(*conditions))
        .order_by(TaskCompletion.completed_at.desc())
    )
    result = await db.execute(completions_stmt)
    all_completions = result.scalars().all()
    
    # Find consumed completions for this rule
    consumed_stmt = (
        select(DependencyResolution.upstream_completion_id)
        .where(
            DependencyResolution.dependency_rule_id == rule.id,
            DependencyResolution.upstream_completion_id.isnot(None),
        )
    )
    consumed_result = await db.execute(consumed_stmt)
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
