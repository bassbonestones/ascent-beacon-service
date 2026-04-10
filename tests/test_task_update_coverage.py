"""Task API branch coverage tests - targeting specific update/delete/complete paths.

Uses PATCH for updates and includes required request bodies.
"""

import pytest
from httpx import AsyncClient
from datetime import datetime, timezone
from uuid import uuid4


@pytest.mark.asyncio
async def test_update_task_title(client: AsyncClient):
    """Test updating task title only."""
    goal = await client.post("/goals", json={"title": "Update Goal"})
    goal_id = goal.json()["id"]
    
    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Original Title", "duration_minutes": 30},
    )
    task_id = task.json()["id"]
    
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"title": "Updated Title"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_update_task_description(client: AsyncClient):
    """Test updating task description."""
    goal = await client.post("/goals", json={"title": "Desc Goal"})
    goal_id = goal.json()["id"]
    
    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task", "duration_minutes": 30},
    )
    task_id = task.json()["id"]
    
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"description": "New description"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "New description"


@pytest.mark.asyncio
async def test_update_task_duration_minutes(client: AsyncClient):
    """Test updating task duration."""
    goal = await client.post("/goals", json={"title": "Duration Goal"})
    goal_id = goal.json()["id"]
    
    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task", "duration_minutes": 30},
    )
    task_id = task.json()["id"]
    
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"duration_minutes": 60},
    )
    assert response.status_code == 200
    assert response.json()["duration_minutes"] == 60


@pytest.mark.asyncio
async def test_update_task_notify_before_minutes(client: AsyncClient):
    """Test updating task notification time."""
    goal = await client.post("/goals", json={"title": "Notify Goal"})
    goal_id = goal.json()["id"]
    
    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task", "duration_minutes": 30},
    )
    task_id = task.json()["id"]
    
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"notify_before_minutes": 15},
    )
    assert response.status_code == 200
    assert response.json()["notify_before_minutes"] == 15


@pytest.mark.asyncio
async def test_update_task_goal_id(client: AsyncClient):
    """Test moving task to different goal."""
    goal1 = await client.post("/goals", json={"title": "Goal 1"})
    goal1_id = goal1.json()["id"]
    
    goal2 = await client.post("/goals", json={"title": "Goal 2"})
    goal2_id = goal2.json()["id"]
    
    task = await client.post(
        "/tasks",
        json={"goal_id": goal1_id, "title": "Task", "duration_minutes": 30},
    )
    task_id = task.json()["id"]
    
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"goal_id": goal2_id},
    )
    assert response.status_code == 200
    assert response.json()["goal_id"] == goal2_id


@pytest.mark.asyncio
async def test_update_task_scheduled_date_sets_date_only_mode(client: AsyncClient):
    """Test that setting scheduled_date auto-sets date_only mode."""
    goal = await client.post("/goals", json={"title": "Date Goal"})
    goal_id = goal.json()["id"]
    
    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task", "duration_minutes": 30},
    )
    task_id = task.json()["id"]
    
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"scheduled_date": "2026-04-15"},
    )
    assert response.status_code == 200
    assert response.json()["scheduled_date"] == "2026-04-15"
    assert response.json()["scheduling_mode"] == "date_only"


@pytest.mark.asyncio
async def test_update_task_make_recurring(client: AsyncClient):
    """Test updating a non-recurring task to be recurring."""
    goal = await client.post("/goals", json={"title": "Recur Goal"})
    goal_id = goal.json()["id"]
    
    now = datetime.now(timezone.utc)
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Task",
            "duration_minutes": 30,
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task.json()["id"]
    
    response = await client.patch(
        f"/tasks/{task_id}",
        json={
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    assert response.status_code == 200
    assert response.json()["is_recurring"] is True


@pytest.mark.asyncio
async def test_update_task_make_non_recurring_clears_behavior(client: AsyncClient):
    """Test that making a task non-recurring clears recurrence_behavior."""
    goal = await client.post("/goals", json={"title": "Unrecur Goal"})
    goal_id = goal.json()["id"]
    
    now = datetime.now(timezone.utc)
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring Task",
            "duration_minutes": 30,
            "scheduled_at": now.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task.json()["id"]
    
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"is_recurring": False},
    )
    assert response.status_code == 200
    assert response.json()["is_recurring"] is False
    assert response.json()["recurrence_behavior"] is None


@pytest.mark.asyncio
async def test_update_recurring_without_behavior_fails(client: AsyncClient):
    """Test that making recurring without behavior fails."""
    goal = await client.post("/goals", json={"title": "Fail Goal"})
    goal_id = goal.json()["id"]
    
    now = datetime.now(timezone.utc)
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Task",
            "duration_minutes": 30,
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task.json()["id"]
    
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"is_recurring": True, "recurrence_rule": "FREQ=DAILY"},
    )
    assert response.status_code == 400
    assert "recurrence_behavior is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_task_success(client: AsyncClient):
    """Test deleting a task."""
    goal = await client.post("/goals", json={"title": "Delete Goal"})
    goal_id = goal.json()["id"]
    
    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "To Delete", "duration_minutes": 30},
    )
    task_id = task.json()["id"]
    
    response = await client.delete(f"/tasks/{task_id}")
    assert response.status_code == 204
    
    # Verify it's gone
    get_response = await client.get(f"/tasks/{task_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_nonexistent_task_returns_404(client: AsyncClient):
    """Test deleting a nonexistent task returns 404."""
    response = await client.delete(f"/tasks/{uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_complete_task_success(client: AsyncClient):
    """Test completing a non-recurring task."""
    goal = await client.post("/goals", json={"title": "Complete Goal"})
    goal_id = goal.json()["id"]
    
    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task", "duration_minutes": 30},
    )
    task_id = task.json()["id"]
    
    response = await client.post(f"/tasks/{task_id}/complete", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_complete_recurring_task_creates_completion_record(client: AsyncClient):
    """Test completing a recurring task creates a completion record."""
    goal = await client.post("/goals", json={"title": "Recur Complete Goal"})
    goal_id = goal.json()["id"]
    
    now = datetime.now(timezone.utc)
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring",
            "duration_minutes": 30,
            "scheduled_at": now.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task.json()["id"]
    
    response = await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": now.isoformat()},
    )
    assert response.status_code == 200
    # Task stays pending (recurring tasks stay pending)
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_skip_task_success(client: AsyncClient):
    """Test skipping a non-recurring task."""
    goal = await client.post("/goals", json={"title": "Skip Goal"})
    goal_id = goal.json()["id"]
    
    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task", "duration_minutes": 30},
    )
    task_id = task.json()["id"]
    
    response = await client.post(
        f"/tasks/{task_id}/skip",
        json={"reason": "Not today"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "skipped"


@pytest.mark.asyncio
async def test_skip_recurring_task_creates_skip_record(client: AsyncClient):
    """Test skipping a recurring task creates a skip record."""
    goal = await client.post("/goals", json={"title": "Recur Skip Goal"})
    goal_id = goal.json()["id"]
    
    now = datetime.now(timezone.utc)
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring",
            "duration_minutes": 30,
            "scheduled_at": now.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task.json()["id"]
    
    response = await client.post(
        f"/tasks/{task_id}/skip",
        json={"scheduled_for": now.isoformat(), "reason": "Busy today"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "pending"  # Recurring tasks stay pending


@pytest.mark.asyncio
async def test_reopen_task_success(client: AsyncClient):
    """Test reopening a completed task."""
    goal = await client.post("/goals", json={"title": "Reopen Goal"})
    goal_id = goal.json()["id"]
    
    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task", "duration_minutes": 30},
    )
    task_id = task.json()["id"]
    
    # Complete then reopen
    await client.post(f"/tasks/{task_id}/complete", json={})
    response = await client.post(f"/tasks/{task_id}/reopen", json={})
    
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_list_tasks_with_recurring_completions(client: AsyncClient):
    """Test listing tasks includes recurring completion info."""
    goal = await client.post("/goals", json={"title": "List Goal"})
    goal_id = goal.json()["id"]
    
    now = datetime.now(timezone.utc)
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring Task",
            "duration_minutes": 30,
            "scheduled_at": now.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task.json()["id"]
    
    # Complete the recurring task
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": now.isoformat()},
    )
    
    # List tasks and verify completions_today is tracked
    list_response = await client.get(f"/tasks?goal_id={goal_id}")
    assert list_response.status_code == 200
    tasks = list_response.json()["tasks"]
    assert len(tasks) >= 1
    
    recurring_task = next((t for t in tasks if t["id"] == task_id), None)
    assert recurring_task is not None
    assert recurring_task["completions_today"] >= 1


@pytest.mark.asyncio
async def test_list_tasks_with_skips(client: AsyncClient):
    """Test listing tasks includes skip info."""
    goal = await client.post("/goals", json={"title": "Skip List Goal"})
    goal_id = goal.json()["id"]
    
    now = datetime.now(timezone.utc)
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring Skip Task",
            "duration_minutes": 30,
            "scheduled_at": now.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task.json()["id"]
    
    # Skip the recurring task
    await client.post(
        f"/tasks/{task_id}/skip",
        json={"scheduled_for": now.isoformat(), "reason": "Too busy"},
    )
    
    # List tasks and verify skips_today is tracked
    list_response = await client.get(f"/tasks?goal_id={goal_id}")
    assert list_response.status_code == 200
    tasks = list_response.json()["tasks"]
    
    recurring_task = next((t for t in tasks if t["id"] == task_id), None)
    assert recurring_task is not None
    assert recurring_task["skips_today"] >= 1
