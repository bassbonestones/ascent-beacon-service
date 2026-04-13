"""Unit tests for goal archive helper branches."""

from datetime import timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.helpers.goal_archive_helpers import (
    apply_task_resolution,
    archive_goal_subtree,
    assert_target_goal_for_reassign,
)
from app.core.time import utc_now
from app.models import Goal, Task
from app.models.user import User
from app.record_state import ACTIVE, PAUSED


async def _create_user(db_session: AsyncSession) -> User:
    user = User(
        id=str(uuid4()),
        display_name="Helper User",
        primary_email=f"helper-{uuid4().hex[:8]}@example.com",
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_assert_target_goal_for_reassign_not_found(db_session: AsyncSession) -> None:
    user = await _create_user(db_session)
    with pytest.raises(HTTPException) as exc:
        await assert_target_goal_for_reassign(
            db_session,
            goal_id=str(uuid4()),
            user_id=user.id,
            forbidden_ids=frozenset(),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_assert_target_goal_for_reassign_rejects_forbidden_and_paused(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session)
    goal = Goal(user_id=user.id, title="Paused goal", record_state=PAUSED)
    db_session.add(goal)
    await db_session.flush()

    with pytest.raises(HTTPException) as forbidden_exc:
        await assert_target_goal_for_reassign(
            db_session,
            goal_id=goal.id,
            user_id=user.id,
            forbidden_ids=frozenset({goal.id}),
        )
    assert forbidden_exc.value.status_code == 400

    with pytest.raises(HTTPException) as paused_exc:
        await assert_target_goal_for_reassign(
            db_session,
            goal_id=goal.id,
            user_id=user.id,
            forbidden_ids=frozenset(),
        )
    assert paused_exc.value.status_code == 400
    assert "must be active" in paused_exc.value.detail


@pytest.mark.asyncio
async def test_apply_task_resolution_pause_archive_and_invalid(db_session: AsyncSession) -> None:
    user = await _create_user(db_session)
    now = utc_now()
    task = Task(user_id=user.id, title="Task A")
    db_session.add(task)
    await db_session.flush()

    apply_task_resolution(task, "pause_task", None, now)
    assert task.record_state == PAUSED
    assert task.updated_at.tzinfo == timezone.utc

    apply_task_resolution(task, "archive_task", None, now)
    assert task.record_state == "archived"

    with pytest.raises(HTTPException) as exc:
        apply_task_resolution(task, "nope", None, now)
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_archive_goal_subtree_sets_tracking_only_on_root(
    db_session: AsyncSession,
) -> None:
    user = await _create_user(db_session)
    root = Goal(user_id=user.id, title="Root", record_state=ACTIVE)
    child = Goal(user_id=user.id, title="Child", parent_goal_id=root.id, record_state=ACTIVE)
    db_session.add(root)
    await db_session.flush()
    child.parent_goal_id = root.id
    db_session.add(child)
    await db_session.flush()

    now = utc_now()
    await archive_goal_subtree(
        db_session,
        root_goal=root,
        subtree_ids=[root.id, child.id],
        tracking_mode="ignored",
        now=now,
    )

    assert root.record_state == "archived"
    assert root.archive_tracking_mode == "ignored"
    assert child.record_state == "archived"
    assert child.archive_tracking_mode is None
"""Unit tests for goal archive helper behaviors."""

from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from app.api.helpers.goal_archive_helpers import apply_task_resolution


def test_apply_task_resolution_invalid_action() -> None:
    task = Mock()
    with pytest.raises(HTTPException) as exc:
        apply_task_resolution(
            task,
            "not_a_valid_action",
            None,
            datetime.now(timezone.utc),
        )
    assert exc.value.status_code == 422


def test_apply_task_resolution_reassign_requires_goal_id() -> None:
    task = Mock()
    with pytest.raises(HTTPException) as exc:
        apply_task_resolution(
            task,
            "reassign",
            None,
            datetime.now(timezone.utc),
        )
    assert exc.value.status_code == 422


@pytest.mark.asyncio
async def test_affected_tasks_for_archive_returns_empty_for_empty_subtree() -> None:
    from unittest.mock import AsyncMock
    from app.api.helpers.goal_archive_helpers import affected_tasks_for_archive

    out = await affected_tasks_for_archive(AsyncMock(), [], "u1")
    assert out == []
