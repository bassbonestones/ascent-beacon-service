"""Unit-style branch tests for `app/api/tasks_list.py` parsing logic."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.api import tasks_list


@pytest.mark.asyncio
async def test_list_tasks_parses_sparse_completion_rows_and_dependency_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exercise defensive completion-row branches that are hard via HTTP-only flows."""
    today = "2026-01-01"

    task = SimpleNamespace(
        id="task-1",
        is_recurring=True,
        status="pending",
        scheduled_at=None,
        created_at=datetime(2026, 1, 1, 8, 0, 0),
    )

    # Query #1: list tasks
    task_result = MagicMock()
    task_result.scalars.return_value.all.return_value = [task]

    # Query #2: completion rows
    completion_result = MagicMock()
    completion_result.fetchall.return_value = [
        ("task-1", None, "completed", None, None, None),  # fully sparse row -> continue
        (
            "task-1",
            datetime(2026, 1, 1, 9, 0, 0),  # naive scheduled_for
            "completed",
            None,
            None,
            None,
        ),
        (
            "task-1",
            None,
            "completed",
            None,
            today,  # local_date only; ts_iso fallback branch
            None,
        ),
        (
            "task-1",
            None,
            "skipped",
            "Skipped by test",
            None,
            datetime(2026, 1, 1, 10, 0, 0),  # completed_at fallback branch
        ),
    ]

    db = AsyncMock()
    db.execute.side_effect = [task_result, completion_result]
    user = SimpleNamespace(id="user-1")

    monkeypatch.setattr(tasks_list, "task_to_response", lambda t, **kw: {"id": t.id, **kw})
    monkeypatch.setattr(tasks_list, "TaskListResponse", lambda **kwargs: kwargs)
    monkeypatch.setattr(
        tasks_list,
        "build_summaries_by_task_and_dates",
        AsyncMock(return_value={"task-1": {today: {}}}),
    )

    response = await tasks_list.list_tasks(
        user=user,
        db=db,
        goal_id=None,
        status_filter=None,
        include_completed=False,
        scheduled_after=None,
        scheduled_before=None,
        client_today=today,
        days_ahead=14,
        include_dependency_summary=True,
        client_timezone=None,
        include_paused=False,
        include_archived=False,
    )

    assert response["total"] == 1
    assert response["tasks"][0]["completions_today"] >= 1
    assert response["tasks"][0]["skips_today"] >= 1


@pytest.mark.asyncio
async def test_list_tasks_parses_aware_timestamps_and_reuses_existing_maps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hit opposite branch directions for tz checks and map-init guards."""
    today = "2026-01-01"

    task = SimpleNamespace(
        id="task-2",
        is_recurring=True,
        status="pending",
        scheduled_at=None,
        created_at=datetime(2026, 1, 1, 8, 0, 0),
    )

    task_result = MagicMock()
    task_result.scalars.return_value.all.return_value = [task]

    aware_dt = datetime.fromisoformat("2026-01-01T09:00:00+00:00")
    completion_result = MagicMock()
    completion_result.fetchall.return_value = [
        ("task-2", aware_dt, "completed", None, None, None),
        ("task-2", aware_dt, "completed", None, None, None),  # reuse existing completion maps
        ("task-2", None, "skipped", "r1", None, aware_dt),
        ("task-2", None, "skipped", "r2", None, aware_dt),  # reuse existing skip maps
    ]

    db = AsyncMock()
    db.execute.side_effect = [task_result, completion_result]
    user = SimpleNamespace(id="user-1")

    monkeypatch.setattr(tasks_list, "task_to_response", lambda t, **kw: {"id": t.id, **kw})
    monkeypatch.setattr(tasks_list, "TaskListResponse", lambda **kwargs: kwargs)
    monkeypatch.setattr(
        tasks_list,
        "build_summaries_by_task_and_dates",
        AsyncMock(return_value={}),
    )

    response = await tasks_list.list_tasks(
        user=user,
        db=db,
        goal_id=None,
        status_filter=None,
        include_completed=False,
        scheduled_after=None,
        scheduled_before=None,
        client_today=today,
        days_ahead=14,
        include_dependency_summary=False,
        client_timezone=None,
        include_paused=False,
        include_archived=False,
    )

    assert response["total"] == 1
    assert response["tasks"][0]["completions_today"] == 2
    assert response["tasks"][0]["skips_today"] == 2
