"""Tests for `app/api/tasks_anytime.py`."""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


async def _create_goal(client: AsyncClient, title: str = "Goal") -> str:
    response = await client.post("/goals", json={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


async def _create_anytime_task(
    client: AsyncClient,
    goal_id: str,
    title: str,
) -> str:
    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": title,
            "duration_minutes": 15,
            "scheduling_mode": "anytime",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_list_anytime_tasks_returns_only_anytime_pending(client: AsyncClient) -> None:
    goal_id = await _create_goal(client)
    anytime_id = await _create_anytime_task(client, goal_id, "Anytime task")

    scheduled_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Scheduled task",
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert scheduled_response.status_code == 201

    response = await client.get("/tasks/view/anytime")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["tasks"][0]["id"] == anytime_id


@pytest.mark.asyncio
async def test_list_anytime_tasks_include_completed(client: AsyncClient) -> None:
    goal_id = await _create_goal(client)
    anytime_id = await _create_anytime_task(client, goal_id, "Complete me")
    await client.post(f"/tasks/{anytime_id}/complete", json={})

    pending_id = await _create_anytime_task(client, goal_id, "Still pending")

    default_response = await client.get("/tasks/view/anytime")
    assert default_response.status_code == 200
    assert default_response.json()["total"] == 1
    assert default_response.json()["tasks"][0]["id"] == pending_id

    include_response = await client.get("/tasks/view/anytime?include_completed=true")
    assert include_response.status_code == 200
    assert include_response.json()["total"] == 2


@pytest.mark.asyncio
async def test_reorder_anytime_task_moves_to_top(client: AsyncClient) -> None:
    goal_id = await _create_goal(client)
    first = await _create_anytime_task(client, goal_id, "First")
    second = await _create_anytime_task(client, goal_id, "Second")
    third = await _create_anytime_task(client, goal_id, "Third")

    response = await client.patch(f"/tasks/{third}/reorder", json={"new_position": 1})
    assert response.status_code == 200
    assert response.json()["task"]["sort_order"] == 1

    list_response = await client.get("/tasks/view/anytime")
    ids = [task["id"] for task in list_response.json()["tasks"]]
    assert ids == [third, first, second]


@pytest.mark.asyncio
async def test_reorder_anytime_task_rejects_scheduled_task(client: AsyncClient) -> None:
    goal_id = await _create_goal(client)
    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Timed task",
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert response.status_code == 201
    task_id = response.json()["id"]

    reorder_response = await client.patch(f"/tasks/{task_id}/reorder", json={"new_position": 1})
    assert reorder_response.status_code == 400
    assert "Only anytime tasks can be reordered" in reorder_response.json()["detail"]


@pytest.mark.asyncio
async def test_reorder_anytime_task_rejects_completed_anytime(client: AsyncClient) -> None:
    goal_id = await _create_goal(client)
    task_id = await _create_anytime_task(client, goal_id, "Anytime")
    await client.post(f"/tasks/{task_id}/complete", json={})

    response = await client.patch(f"/tasks/{task_id}/reorder", json={"new_position": 1})
    assert response.status_code == 400
    assert "Cannot reorder a completed anytime task" in response.json()["detail"]
