"""
Helper functions for Dependencies API.
"""
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import Task
from app.models.dependency import DependencyRule
from app.schemas.dependency import DependencyRuleResponse, TaskInfo


async def get_rule_or_404(
    db: AsyncSession, rule_id: str, user_id: str
) -> DependencyRule:
    """Get a dependency rule by ID, ensuring it belongs to the user."""
    stmt = (
        select(DependencyRule)
        .options(
            selectinload(DependencyRule.upstream_task),
            selectinload(DependencyRule.downstream_task),
        )
        .where(DependencyRule.id == rule_id, DependencyRule.user_id == user_id)
    )
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail="Dependency rule not found")
    return rule


async def get_task_or_404_for_dep(
    db: AsyncSession, task_id: str, user_id: str
) -> Task:
    """Get a task by ID for dependency creation."""
    stmt = select(Task).where(Task.id == task_id, Task.user_id == user_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


async def check_rule_exists(
    db: AsyncSession, upstream_id: str, downstream_id: str
) -> bool:
    """Check if a dependency rule already exists for this task pair."""
    stmt = select(DependencyRule).where(
        DependencyRule.upstream_task_id == upstream_id,
        DependencyRule.downstream_task_id == downstream_id,
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def detect_cycle(
    db: AsyncSession, user_id: str, upstream_id: str, downstream_id: str
) -> tuple[bool, list[str] | None]:
    """
    Detect if adding upstream→downstream would create a cycle.
    Uses DFS from downstream to check if upstream is reachable.
    """
    stmt = select(DependencyRule).where(DependencyRule.user_id == user_id)
    result = await db.execute(stmt)
    rules = result.scalars().all()

    # Build adjacency list: downstream_id -> [upstream_ids]
    adjacency: dict[str, list[str]] = {}
    for rule in rules:
        if rule.downstream_task_id not in adjacency:
            adjacency[rule.downstream_task_id] = []
        adjacency[rule.downstream_task_id].append(rule.upstream_task_id)

    # Add the proposed edge
    if downstream_id not in adjacency:
        adjacency[downstream_id] = []
    adjacency[downstream_id].append(upstream_id)

    visited: set[str] = set()
    path: list[str] = []

    def dfs(node: str, target: str) -> bool:
        if node == target:
            path.append(node)
            return True
        if node in visited:
            return False
        visited.add(node)
        path.append(node)
        for upstream in adjacency.get(node, []):
            if dfs(upstream, target):
                return True
        path.pop()
        return False

    if dfs(upstream_id, downstream_id):
        path.reverse()
        return True, path

    return False, None


def rule_to_response(rule: DependencyRule) -> DependencyRuleResponse:
    """Convert DependencyRule model to response schema."""
    upstream_info = None
    if rule.upstream_task:
        upstream_info = TaskInfo(
            id=rule.upstream_task.id,
            title=rule.upstream_task.title,
            is_recurring=rule.upstream_task.is_recurring,
            recurrence_rule=rule.upstream_task.recurrence_rule,
        )

    downstream_info = None
    if rule.downstream_task:
        downstream_info = TaskInfo(
            id=rule.downstream_task.id,
            title=rule.downstream_task.title,
            is_recurring=rule.downstream_task.is_recurring,
            recurrence_rule=rule.downstream_task.recurrence_rule,
        )

    return DependencyRuleResponse(
        id=rule.id,
        user_id=rule.user_id,
        upstream_task_id=rule.upstream_task_id,
        downstream_task_id=rule.downstream_task_id,
        strength=rule.strength,
        scope=rule.scope,
        required_occurrence_count=rule.required_occurrence_count,
        validity_window_minutes=rule.validity_window_minutes,
        created_at=rule.created_at,
        updated_at=rule.updated_at,
        upstream_task=upstream_info,
        downstream_task=downstream_info,
    )
