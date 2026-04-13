"""Tests for `app/api/tasks_completions.py`."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_completion import TaskCompletion


async def _create_goal(client: AsyncClient, title: str = "Goal") -> str:
    response = await client.post("/goals", json={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


async def _create_task(
    client: AsyncClient,
    goal_id: str,
    *,
    title: str = "Task",
    is_recurring: bool = True,
) -> str:
    payload: dict[str, object] = {
        "goal_id": goal_id,
        "title": title,
        "duration_minutes": 30,
    }
    if is_recurring:
        payload.update(
            {
                "scheduled_at": datetime.now(timezone.utc).isoformat(),
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
            }
        )
    response = await client.post("/tasks", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_count_future_completions_filters_by_cutoff(client: AsyncClient) -> None:
    goal_id = await _create_goal(client)
    task_id = await _create_task(client, goal_id)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": f"{today}T09:00:00+00:00"},
    )
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": f"{tomorrow}T09:00:00+00:00"},
    )

    response = await client.get(f"/tasks/completions/future/count?after_date={today}")
    assert response.status_code == 200
    assert response.json() == {"count": 1}


@pytest.mark.asyncio
async def test_count_future_completions_rejects_invalid_date(client: AsyncClient) -> None:
    response = await client.get("/tasks/completions/future/count?after_date=2026-13-99")
    assert response.status_code == 400
    assert "Invalid date format" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_future_completions_deletes_only_future(client: AsyncClient) -> None:
    goal_id = await _create_goal(client)
    task_id = await _create_task(client, goal_id)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")

    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": f"{today}T09:00:00+00:00"},
    )
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": f"{tomorrow}T09:00:00+00:00"},
    )

    delete_response = await client.delete(f"/tasks/completions/future?after_date={today}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted_count": 1}

    count_response = await client.get(f"/tasks/completions/future/count?after_date={today}")
    assert count_response.status_code == 200
    assert count_response.json() == {"count": 0}


@pytest.mark.asyncio
async def test_delete_future_completions_rejects_invalid_date(client: AsyncClient) -> None:
    response = await client.delete("/tasks/completions/future?after_date=not-a-date")
    assert response.status_code == 400
    assert "Invalid date format" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_bulk_completions_requires_recurring_task(client: AsyncClient) -> None:
    goal_id = await _create_goal(client)
    task_id = await _create_task(client, goal_id, is_recurring=False)

    response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={"entries": [{"date": "2026-01-01", "status": "completed"}]},
    )
    assert response.status_code == 400
    assert "only supported for recurring tasks" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_bulk_completions_creates_mock_records(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    goal_id = await _create_goal(client)
    task_id = await _create_task(client, goal_id)

    response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2026-02-01", "status": "completed", "occurrences": 2},
                {
                    "date": "2026-02-02",
                    "status": "skipped",
                    "skip_reason": "Busy",
                    "occurrences": 1,
                },
            ],
            "update_start_date": "2026-02-01",
        },
    )
    assert response.status_code == 200
    assert response.json()["created_count"] == 3
    assert response.json()["start_date_updated"] is True

    stmt = select(func.count()).select_from(TaskCompletion).where(
        TaskCompletion.task_id == task_id,
        TaskCompletion.source == "MOCK",
    )
    total = (await db_session.execute(stmt)).scalar_one()
    assert total == 3


@pytest.mark.asyncio
async def test_create_bulk_completions_replaces_existing_mocks(client: AsyncClient) -> None:
    goal_id = await _create_goal(client)
    task_id = await _create_task(client, goal_id)

    first = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={"entries": [{"date": "2026-03-01", "status": "completed", "occurrences": 3}]},
    )
    assert first.status_code == 200
    assert first.json()["created_count"] == 3

    second = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={"entries": [{"date": "2026-03-02", "status": "completed", "occurrences": 1}]},
    )
    assert second.status_code == 200
    assert second.json()["created_count"] == 1

    delete_response = await client.delete(f"/tasks/{task_id}/completions/mock")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_count"] == 1


@pytest.mark.asyncio
async def test_delete_mock_completions_leaves_real_completions(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    goal_id = await _create_goal(client)
    task_id = await _create_task(client, goal_id)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": f"{today}T08:00:00+00:00"},
    )
    await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={"entries": [{"date": "2026-04-01", "status": "completed", "occurrences": 2}]},
    )

    delete_response = await client.delete(f"/tasks/{task_id}/completions/mock")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_count"] == 2

    real_stmt = select(func.count()).select_from(TaskCompletion).where(
        TaskCompletion.task_id == task_id,
        TaskCompletion.source == "REAL",
    )
    real_count = (await db_session.execute(real_stmt)).scalar_one()
    assert real_count == 1


@pytest.mark.asyncio
async def test_create_bulk_completions_skips_invalid_entry_date(client: AsyncClient) -> None:
    goal_id = await _create_goal(client)
    task_id = await _create_task(client, goal_id)

    response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2026-05-01", "status": "completed", "occurrences": 2},
                {"date": "2026-02-30", "status": "completed", "occurrences": 2},
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["created_count"] == 2


@pytest.mark.asyncio
async def test_delete_mock_completions_returns_zero_without_mock_rows(
    client: AsyncClient,
) -> None:
    goal_id = await _create_goal(client)
    task_id = await _create_task(client, goal_id)

    response = await client.delete(f"/tasks/{task_id}/completions/mock")
    assert response.status_code == 200
    assert response.json()["deleted_count"] == 0
