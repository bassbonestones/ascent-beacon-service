"""Tests for goal archive preview and commit endpoints."""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


async def _create_goal(
    client: AsyncClient,
    title: str,
    parent_goal_id: str | None = None,
) -> str:
    payload: dict[str, str] = {"title": title}
    if parent_goal_id:
        payload["parent_goal_id"] = parent_goal_id
    response = await client.post("/goals", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def _create_task(client: AsyncClient, goal_id: str, title: str) -> str:
    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": title,
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
            "duration_minutes": 15,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_archive_preview_lists_pending_tasks_in_subtree(client: AsyncClient) -> None:
    parent_id = await _create_goal(client, "Parent")
    child_id = await _create_goal(client, "Child", parent_goal_id=parent_id)
    parent_task_id = await _create_task(client, parent_id, "Parent task")
    child_task_id = await _create_task(client, child_id, "Child task")

    response = await client.get(f"/goals/{parent_id}/archive-preview")
    assert response.status_code == 200
    data = response.json()
    assert set(data["subtree_goal_ids"]) == {parent_id, child_id}

    affected_task_ids = {item["task_id"] for item in data["tasks_requiring_resolution"]}
    assert affected_task_ids == {parent_task_id, child_task_id}


@pytest.mark.asyncio
async def test_archive_commit_requires_exact_preview_match(client: AsyncClient) -> None:
    goal_id = await _create_goal(client, "Archive me")
    await _create_task(client, goal_id, "Task A")

    response = await client.post(
        f"/goals/{goal_id}/archive",
        json={"tracking_mode": "failed", "task_resolutions": []},
    )
    assert response.status_code == 422
    assert "must match the preview task set exactly" in response.json()["detail"]


@pytest.mark.asyncio
async def test_archive_commit_reassign_requires_goal_id(client: AsyncClient) -> None:
    goal_id = await _create_goal(client, "Archive me")
    task_id = await _create_task(client, goal_id, "Task A")

    response = await client.post(
        f"/goals/{goal_id}/archive",
        json={
            "tracking_mode": "ignored",
            "task_resolutions": [{"task_id": task_id, "action": "reassign"}],
        },
    )
    assert response.status_code == 422
    assert "reassign requires goal_id" in response.json()["detail"]


@pytest.mark.asyncio
async def test_archive_commit_can_keep_task_unaligned(client: AsyncClient) -> None:
    goal_id = await _create_goal(client, "Archive me")
    task_id = await _create_task(client, goal_id, "Task A")

    response = await client.post(
        f"/goals/{goal_id}/archive",
        json={
            "tracking_mode": "failed",
            "task_resolutions": [{"task_id": task_id, "action": "keep_unaligned"}],
        },
    )
    assert response.status_code == 200
    assert response.json()["record_state"] == "archived"
    assert response.json()["archive_tracking_mode"] == "failed"

    task_response = await client.get(f"/tasks/{task_id}")
    assert task_response.status_code == 200
    assert task_response.json()["goal_id"] is None
    assert task_response.json()["unaligned_execution_acknowledged_at"] is not None


@pytest.mark.asyncio
async def test_archive_commit_reassigns_task_to_active_goal(client: AsyncClient) -> None:
    archive_goal_id = await _create_goal(client, "Archive me")
    target_goal_id = await _create_goal(client, "Receive tasks")
    task_id = await _create_task(client, archive_goal_id, "Reassign me")

    response = await client.post(
        f"/goals/{archive_goal_id}/archive",
        json={
            "tracking_mode": "ignored",
            "task_resolutions": [
                {"task_id": task_id, "action": "reassign", "goal_id": target_goal_id}
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["record_state"] == "archived"

    task_response = await client.get(f"/tasks/{task_id}")
    assert task_response.status_code == 200
    assert task_response.json()["goal_id"] == target_goal_id


@pytest.mark.asyncio
async def test_archive_commit_rejects_resolution_task_outside_preview(client: AsyncClient) -> None:
    goal_id = await _create_goal(client, "Archive me")
    valid_task_id = await _create_task(client, goal_id, "Task in subtree")
    fake_task_id = "00000000-0000-0000-0000-000000000000"

    response = await client.post(
        f"/goals/{goal_id}/archive",
        json={
            "tracking_mode": "failed",
            "task_resolutions": [
                {"task_id": valid_task_id, "action": "archive_task"},
                {"task_id": fake_task_id, "action": "archive_task"},
            ],
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_pause_unpause_goal_and_conflict(client: AsyncClient) -> None:
    goal_id = await _create_goal(client, "Pause goal")

    conflict = await client.post(f"/goals/{goal_id}/unpause")
    assert conflict.status_code == 409

    pause = await client.post(f"/goals/{goal_id}/pause")
    assert pause.status_code == 200
    assert pause.json()["record_state"] == "paused"

    unpause = await client.post(f"/goals/{goal_id}/unpause")
    assert unpause.status_code == 200
    assert unpause.json()["record_state"] == "active"


@pytest.mark.asyncio
async def test_delete_subgoal_soft_deletes_subtree_and_tasks(client: AsyncClient) -> None:
    parent_id = await _create_goal(client, "Parent")
    child_id = await _create_goal(client, "Child", parent_goal_id=parent_id)
    grandchild_id = await _create_goal(client, "Grandchild", parent_goal_id=child_id)
    child_task_id = await _create_task(client, child_id, "Child task")

    delete_response = await client.delete(f"/goals/{child_id}")
    assert delete_response.status_code == 204

    # Deleted subtree nodes are no longer retrievable via active goal endpoints.
    child_after = await client.get(f"/goals/{child_id}")
    grandchild_after = await client.get(f"/goals/{grandchild_id}")
    assert child_after.status_code == 404
    assert grandchild_after.status_code == 404

    # Parent remains accessible, confirming we deleted a sub-tree branch.
    parent_after = await client.get(f"/goals/{parent_id}")
    assert parent_after.status_code == 200

    # Task attached to deleted child should no longer be returned as active.
    task_after = await client.get(f"/tasks/{child_task_id}")
    assert task_after.status_code == 404
