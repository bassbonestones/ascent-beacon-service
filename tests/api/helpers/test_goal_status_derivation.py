"""Unit tests for derived goal status helpers (DB + edge branches)."""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.helpers.goal_status_derivation import (
    compute_derived_goal_status,
    persist_goal_derived_status,
    recompute_goal_status_ancestors,
    _goal_is_completed,
    _subtree_has_active_task,
)
from app.models import Goal, Task
from app.models.user import User
from app.record_state import ACTIVE, ARCHIVED, PAUSED


async def _user(db_session: AsyncSession) -> User:
    u = User(
        id=str(uuid4()),
        display_name="U",
        primary_email=f"u-{uuid4().hex[:8]}@example.com",
        is_email_verified=True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


@pytest.mark.asyncio
async def test_compute_derived_unknown_goal_returns_not_started(
    db_session: AsyncSession,
) -> None:
    assert await compute_derived_goal_status(db_session, str(uuid4())) == "not_started"


@pytest.mark.asyncio
async def test_recompute_ancestors_none_is_safe(db_session: AsyncSession) -> None:
    await recompute_goal_status_ancestors(db_session, None)


@pytest.mark.asyncio
async def test_persist_derived_status_missing_goal_noop(
    db_session: AsyncSession,
) -> None:
    await persist_goal_derived_status(db_session, str(uuid4()))


@pytest.mark.asyncio
async def test_compute_non_active_goal_returns_stored_status(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session)
    g = Goal(
        user_id=user.id,
        title="Archived",
        status="in_progress",
        record_state=ARCHIVED,
    )
    db_session.add(g)
    await db_session.flush()
    assert await compute_derived_goal_status(db_session, g.id) == "in_progress"


@pytest.mark.asyncio
async def test_compute_paused_goal_returns_stored_status(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session)
    g = Goal(
        user_id=user.id,
        title="Paused",
        status="not_started",
        record_state=PAUSED,
    )
    db_session.add(g)
    await db_session.flush()
    assert await compute_derived_goal_status(db_session, g.id) == "not_started"


@pytest.mark.asyncio
async def test_subtree_has_active_task_scans_multiple_subgoals(
    db_session: AsyncSession,
) -> None:
    """First subgoal empty, second has a task → inner loop continues then succeeds."""
    user = await _user(db_session)
    root = Goal(user_id=user.id, title="R", record_state=ACTIVE)
    empty = Goal(user_id=user.id, title="E", parent_goal_id=None, record_state=ACTIVE)
    with_task = Goal(
        user_id=user.id, title="W", parent_goal_id=None, record_state=ACTIVE
    )
    db_session.add(root)
    await db_session.flush()
    empty.parent_goal_id = root.id
    with_task.parent_goal_id = root.id
    db_session.add(empty)
    db_session.add(with_task)
    await db_session.flush()
    at = datetime.now(timezone.utc)
    t = Task(
        user_id=user.id,
        goal_id=with_task.id,
        title="t",
        duration_minutes=10,
        scheduled_at=at,
        record_state=ACTIVE,
    )
    db_session.add(t)
    await db_session.flush()
    assert await _subtree_has_active_task(db_session, root.id) is True


@pytest.mark.asyncio
async def test_subtree_has_active_task_false_when_empty(
    db_session: AsyncSession,
) -> None:
    user = await _user(db_session)
    root = Goal(user_id=user.id, title="R", record_state=ACTIVE)
    db_session.add(root)
    await db_session.flush()
    assert await _subtree_has_active_task(db_session, root.id) is False


@pytest.mark.asyncio
async def test_goal_is_completed_false_when_child_completed_but_no_active_tasks(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Guards parent completion when subtree check disagrees (defensive branch)."""
    user = await _user(db_session)
    parent = Goal(user_id=user.id, title="P", record_state=ACTIVE)
    child = Goal(
        user_id=user.id,
        title="C",
        parent_goal_id=parent.id,
        record_state=ACTIVE,
    )
    db_session.add(parent)
    await db_session.flush()
    child.parent_goal_id = parent.id
    db_session.add(child)
    await db_session.flush()

    async def _no_tasks(_db: AsyncSession, _gid: str) -> bool:
        return False

    monkeypatch.setattr(
        "app.api.helpers.goal_status_derivation._subtree_has_active_task",
        _no_tasks,
    )
    ok = await _goal_is_completed(
        db_session,
        [child],
        [],
        ["completed"],
    )
    assert ok is False


@pytest.mark.asyncio
async def test_persist_active_goal_no_status_change_skips_apply(
    db_session: AsyncSession,
) -> None:
    """Derived status matches stored → apply_goal_status not needed."""
    user = await _user(db_session)
    g = Goal(user_id=user.id, title="Leaf", status="not_started", record_state=ACTIVE)
    db_session.add(g)
    await db_session.flush()
    await persist_goal_derived_status(db_session, g.id)
    await db_session.refresh(g)
    assert g.status == "not_started"


@pytest.mark.asyncio
async def test_persist_skips_non_active_goal(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    g = Goal(
        user_id=user.id,
        title="Archived leaf",
        status="completed",
        record_state=ARCHIVED,
    )
    db_session.add(g)
    await db_session.flush()
    await persist_goal_derived_status(db_session, g.id)
    await db_session.refresh(g)
    assert g.status == "completed"


@pytest.mark.asyncio
async def test_recompute_ancestors_walks_to_root(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    root = Goal(user_id=user.id, title="Root", record_state=ACTIVE)
    mid = Goal(
        user_id=user.id,
        title="Mid",
        parent_goal_id=None,
        record_state=ACTIVE,
    )
    leaf = Goal(
        user_id=user.id,
        title="Leaf",
        parent_goal_id=None,
        record_state=ACTIVE,
    )
    db_session.add(root)
    await db_session.flush()
    mid.parent_goal_id = root.id
    leaf.parent_goal_id = mid.id
    db_session.add(mid)
    db_session.add(leaf)
    await db_session.flush()
    at = datetime.now(timezone.utc)
    t = Task(
        user_id=user.id,
        goal_id=leaf.id,
        title="job",
        duration_minutes=5,
        scheduled_at=at,
        record_state=ACTIVE,
    )
    db_session.add(t)
    await db_session.flush()
    await recompute_goal_status_ancestors(db_session, leaf.id)
    await db_session.refresh(root)
    await db_session.refresh(mid)
    await db_session.refresh(leaf)
    assert leaf.status == "not_started"
    assert mid.status == "not_started"
    assert root.status == "not_started"
