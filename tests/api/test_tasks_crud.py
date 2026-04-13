"""Tests for `app/api/tasks_crud.py`."""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


async def _create_goal(client: AsyncClient, title: str = "Goal") -> str:
    response = await client.post("/goals", json={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


@pytest.mark.asyncio
async def test_create_task_requires_scheduling_mode_for_recurring_timed_task(
    client: AsyncClient,
) -> None:
    goal_id = await _create_goal(client)
    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring timed",
            "is_recurring": True,
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_behavior": "habitual",
        },
    )
    assert response.status_code == 400
    assert "scheduling_mode is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_task_rejects_anytime_recurring(client: AsyncClient) -> None:
    goal_id = await _create_goal(client)
    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Impossible combo",
            "scheduling_mode": "anytime",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_behavior": "habitual",
        },
    )
    assert response.status_code == 400
    assert "Anytime tasks cannot be recurring" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_task_rejects_recurrence_behavior_on_non_recurring(
    client: AsyncClient,
) -> None:
    goal_id = await _create_goal(client)
    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Bad non-recurring setup",
            "recurrence_behavior": "habitual",
        },
    )
    assert response.status_code == 400
    assert "only be set for recurring tasks" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_date_only_task_infers_scheduling_mode(client: AsyncClient) -> None:
    goal_id = await _create_goal(client)
    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Date-only",
            "scheduled_date": "2026-04-20",
        },
    )
    assert response.status_code == 201
    assert response.json()["scheduling_mode"] == "date_only"


@pytest.mark.asyncio
async def test_get_task_with_dependency_summary_flag(client: AsyncClient) -> None:
    goal_id = await _create_goal(client)
    create_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Simple task"},
    )
    task_id = create_response.json()["id"]

    response = await client.get(
        f"/tasks/{task_id}",
        params={"include_dependency_summary": "true", "client_today": "2026-04-13"},
    )
    assert response.status_code == 200
    assert response.json()["id"] == task_id


@pytest.mark.asyncio
async def test_update_task_clears_recurrence_behavior_when_switched_off(
    client: AsyncClient,
) -> None:
    goal_id = await _create_goal(client)
    create_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = create_response.json()["id"]

    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={"is_recurring": False},
    )
    assert update_response.status_code == 200
    assert update_response.json()["is_recurring"] is False
    assert update_response.json()["recurrence_behavior"] is None


@pytest.mark.asyncio
async def test_pause_and_unpause_task_conflict_when_not_paused(
    client: AsyncClient,
) -> None:
    goal_id = await _create_goal(client)
    create_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Pause me"},
    )
    task_id = create_response.json()["id"]

    conflict = await client.post(f"/tasks/{task_id}/unpause", json={})
    assert conflict.status_code == 409

    paused = await client.post(f"/tasks/{task_id}/pause", json={})
    assert paused.status_code == 200
    assert paused.json()["record_state"] == "paused"

    unpaused = await client.post(f"/tasks/{task_id}/unpause", json={})
    assert unpaused.status_code == 200
    assert unpaused.json()["record_state"] == "active"


@pytest.mark.asyncio
async def test_update_task_applies_nullable_fields_and_date_only_mode(
    client: AsyncClient,
) -> None:
    goal_id = await _create_goal(client)
    create_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Update me",
            "description": "desc",
            "duration_minutes": 20,
            "notify_before_minutes": 10,
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    task_id = create_response.json()["id"]

    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={
            "description": None,
            "duration_minutes": 45,
            "notify_before_minutes": None,
            "scheduled_date": "2026-05-10",
            "scheduled_at": None,
            "recurrence_rule": None,
            "is_recurring": False,
            "recurrence_behavior": None,
        },
    )
    assert update_response.status_code == 200
    body = update_response.json()
    assert body["description"] is None
    assert body["duration_minutes"] == 45
    assert body["notify_before_minutes"] is None
    assert body["scheduled_date"] == "2026-05-10"
    assert body["scheduled_at"] is None
    assert body["scheduling_mode"] == "date_only"


@pytest.mark.asyncio
async def test_update_task_timed_mode_clears_date_only_inferred_mode(
    client: AsyncClient,
) -> None:
    goal_id = await _create_goal(client)
    create_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Date-only first",
            "scheduled_date": "2026-05-20",
        },
    )
    task_id = create_response.json()["id"]
    assert create_response.json()["scheduling_mode"] == "date_only"

    timed_update = await client.patch(
        f"/tasks/{task_id}",
        json={
            "scheduled_date": None,
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "is_recurring": False,
            "recurrence_behavior": None,
        },
    )
    assert timed_update.status_code == 200
    assert timed_update.json()["scheduling_mode"] is None


@pytest.mark.asyncio
async def test_delete_unlinked_task_hard_deletes_row(client: AsyncClient) -> None:
    create_response = await client.post(
        "/tasks",
        json={
            "title": "Standalone",
            "duration_minutes": 5,
        },
    )
    assert create_response.status_code == 201
    task_id = create_response.json()["id"]
    assert create_response.json()["goal_id"] is None

    delete_response = await client.delete(f"/tasks/{task_id}")
    assert delete_response.status_code == 204

    get_response = await client.get(f"/tasks/{task_id}")
    assert get_response.status_code == 404
