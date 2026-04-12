"""Targeted coverage for list_tasks branches (status filter, completion date keys)."""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_completion import TaskCompletion


@pytest.mark.asyncio
async def test_list_tasks_status_skipped_filters_one_time_skipped_task(
    client: AsyncClient,
) -> None:
    g = await client.post("/goals", json={"title": "Goal for skipped list"})
    assert g.status_code == 201, g.text
    goal_id = g.json()["id"]

    t = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "One-time to skip",
            "duration_minutes": 15,
        },
    )
    assert t.status_code == 201, t.text
    task_id = t.json()["id"]

    sk = await client.post(f"/tasks/{task_id}/skip", json={"reason": "cov"})
    assert sk.status_code == 200, sk.text

    r = await client.get("/tasks", params={"status": "skipped"})
    assert r.status_code == 200, r.text
    tasks = r.json()["tasks"]
    assert any(x["id"] == task_id and x["status"] == "skipped" for x in tasks)


@pytest.mark.asyncio
async def test_list_tasks_recurring_completion_naive_scheduled_for_date_key(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Covers naive scheduled_for normalization in completion row processing."""
    g = await client.post("/goals", json={"title": "Goal for naive SF"})
    assert g.status_code == 201, g.text
    goal_id = g.json()["id"]

    t = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring naive SF",
            "duration_minutes": 10,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_behavior": "essential",
        },
    )
    assert t.status_code == 201, t.text
    task_id = t.json()["id"]

    day = "2030-06-15"
    naive_sf = datetime(2030, 6, 15, 14, 30, 0)
    aware_done = datetime(2030, 6, 15, 14, 31, 0, tzinfo=timezone.utc)
    db_session.add(
        TaskCompletion(
            task_id=task_id,
            status="completed",
            scheduled_for=naive_sf,
            local_date=None,
            completed_at=aware_done,
        )
    )
    await db_session.commit()

    lst = await client.get(
        "/tasks",
        params={"client_today": day, "include_completed": "true", "days_ahead": "7"},
    )
    assert lst.status_code == 200, lst.text
    row = next(x for x in lst.json()["tasks"] if x["id"] == task_id)
    assert day in (row.get("completions_by_date") or {})
