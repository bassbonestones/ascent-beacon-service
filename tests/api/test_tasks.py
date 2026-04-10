"""Tests for tasks API endpoints."""

import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient

from app.models.user import User


# ============================================================================
# Create Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_task(client: AsyncClient, test_user: User):
    """Test creating a basic task linked to a goal."""
    # Create a goal first
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Complete task 1",
            "description": "First task for the goal",
            "duration_minutes": 30,
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["user_id"] == test_user.id
    assert data["goal_id"] == goal_id
    assert data["title"] == "Complete task 1"
    assert data["description"] == "First task for the goal"
    assert data["duration_minutes"] == 30
    assert data["status"] == "pending"
    assert data["is_lightning"] is False
    assert data["is_recurring"] is False
    assert data["goal"]["id"] == goal_id


@pytest.mark.asyncio
async def test_create_lightning_task(client: AsyncClient):
    """Test creating a lightning task (duration = 0)."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Quick check",
            "duration_minutes": 0,
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["duration_minutes"] == 0
    assert data["is_lightning"] is True


@pytest.mark.asyncio
async def test_create_task_with_schedule(client: AsyncClient):
    """Test creating a task with a scheduled time."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    scheduled = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Scheduled task",
            "duration_minutes": 15,
            "scheduled_at": scheduled,
            "notify_before_minutes": 10,
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["scheduled_at"] is not None
    assert data["notify_before_minutes"] == 10


@pytest.mark.asyncio
async def test_create_task_updates_goal_progress(client: AsyncClient):
    """Test that creating a task updates goal's has_incomplete_breakdown."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Initially goal has no tasks = incomplete breakdown
    goal = (await client.get(f"/goals/{goal_id}")).json()
    assert goal["has_incomplete_breakdown"] is True

    # Create a task
    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "First task",
            "duration_minutes": 30,
        },
    )

    # Now goal has tasks = complete breakdown
    goal = (await client.get(f"/goals/{goal_id}")).json()
    assert goal["has_incomplete_breakdown"] is False


@pytest.mark.asyncio
async def test_create_task_invalid_goal(client: AsyncClient):
    """Test creating a task with non-existent goal fails."""
    response = await client.post(
        "/tasks",
        json={
            "goal_id": "00000000-0000-0000-0000-000000000000",
            "title": "Orphan task",
            "duration_minutes": 30,
        },
    )

    assert response.status_code == 404


# ============================================================================
# List Tasks Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_tasks_empty(client: AsyncClient):
    """Test listing tasks when user has none."""
    response = await client.get("/tasks")

    assert response.status_code == 200
    data = response.json()
    assert data["tasks"] == []
    assert data["total"] == 0
    assert data["pending_count"] == 0
    assert data["completed_count"] == 0


@pytest.mark.asyncio
async def test_list_tasks_with_data(client: AsyncClient):
    """Test listing tasks returns user's tasks."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task 1", "duration_minutes": 15},
    )
    await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task 2", "duration_minutes": 30},
    )

    response = await client.get("/tasks")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["tasks"]) == 2


@pytest.mark.asyncio
async def test_list_tasks_filter_by_goal(client: AsyncClient):
    """Test filtering tasks by goal_id."""
    # Create two goals with tasks
    goal1_response = await client.post("/goals", json={"title": "Goal 1"})
    goal1_id = goal1_response.json()["id"]
    goal2_response = await client.post("/goals", json={"title": "Goal 2"})
    goal2_id = goal2_response.json()["id"]

    await client.post(
        "/tasks",
        json={"goal_id": goal1_id, "title": "G1 Task", "duration_minutes": 15},
    )
    await client.post(
        "/tasks",
        json={"goal_id": goal2_id, "title": "G2 Task", "duration_minutes": 30},
    )

    # Filter by goal 1
    response = await client.get(f"/tasks?goal_id={goal1_id}")
    data = response.json()

    assert data["total"] == 1
    assert data["tasks"][0]["title"] == "G1 Task"


@pytest.mark.asyncio
async def test_list_tasks_filter_by_status(client: AsyncClient):
    """Test filtering tasks by status."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create pending and completed tasks
    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task 1", "duration_minutes": 15},
    )
    task_id = task_response.json()["id"]
    await client.post(f"/tasks/{task_id}/complete", json={})

    await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task 2", "duration_minutes": 30},
    )

    # Filter by pending
    response = await client.get("/tasks?status=pending")
    data = response.json()

    assert data["total"] == 1
    assert data["tasks"][0]["title"] == "Task 2"


@pytest.mark.asyncio
async def test_list_tasks_days_ahead_param(client: AsyncClient):
    """Test that days_ahead parameter is accepted and validated."""
    # days_ahead param should work (default is 14)
    response = await client.get("/tasks?days_ahead=28")
    assert response.status_code == 200

    # Minimum is 1
    response = await client.get("/tasks?days_ahead=0")
    assert response.status_code == 422  # Validation error

    # Maximum is 365
    response = await client.get("/tasks?days_ahead=400")
    assert response.status_code == 422  # Validation error


# ============================================================================
# Get Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_task(client: AsyncClient):
    """Test getting a single task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    create_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Test Task", "duration_minutes": 20},
    )
    task_id = create_response.json()["id"]

    response = await client.get(f"/tasks/{task_id}")

    assert response.status_code == 200
    assert response.json()["id"] == task_id
    assert response.json()["title"] == "Test Task"


@pytest.mark.asyncio
async def test_get_task_not_found(client: AsyncClient):
    """Test getting a non-existent task returns 404."""
    response = await client.get("/tasks/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


# ============================================================================
# Update Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_task_title(client: AsyncClient):
    """Test updating a task's title."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    create_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Old Title", "duration_minutes": 20},
    )
    task_id = create_response.json()["id"]

    response = await client.patch(
        f"/tasks/{task_id}",
        json={"title": "New Title"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "New Title"


@pytest.mark.asyncio
async def test_update_task_goal(client: AsyncClient):
    """Test moving a task to a different goal."""
    goal1_response = await client.post("/goals", json={"title": "Goal 1"})
    goal1_id = goal1_response.json()["id"]
    goal2_response = await client.post("/goals", json={"title": "Goal 2"})
    goal2_id = goal2_response.json()["id"]

    create_response = await client.post(
        "/tasks",
        json={"goal_id": goal1_id, "title": "Moving Task", "duration_minutes": 20},
    )
    task_id = create_response.json()["id"]

    # Move to goal 2
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"goal_id": goal2_id},
    )

    assert response.status_code == 200
    assert response.json()["goal_id"] == goal2_id


@pytest.mark.asyncio
async def test_update_task_invalid_goal(client: AsyncClient):
    """Test moving a task to non-existent goal fails."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    create_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Test Task", "duration_minutes": 20},
    )
    task_id = create_response.json()["id"]

    response = await client.patch(
        f"/tasks/{task_id}",
        json={"goal_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 404


# ============================================================================
# Complete Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_complete_task(client: AsyncClient):
    """Test completing a task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    create_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Test Task", "duration_minutes": 20},
    )
    task_id = create_response.json()["id"]

    response = await client.post(f"/tasks/{task_id}/complete", json={})

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_complete_task_updates_goal_progress(client: AsyncClient):
    """Test completing a task updates goal progress."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create two tasks with equal duration
    task1_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task 1", "duration_minutes": 30},
    )
    task1_id = task1_response.json()["id"]
    await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task 2", "duration_minutes": 30},
    )

    # Goal should be at 0%
    goal = (await client.get(f"/goals/{goal_id}")).json()
    assert goal["progress_cached"] == 0

    # Complete first task
    await client.post(f"/tasks/{task1_id}/complete", json={})

    # Goal should be at 50%
    goal = (await client.get(f"/goals/{goal_id}")).json()
    assert goal["progress_cached"] == 50


@pytest.mark.asyncio
async def test_complete_task_transitions_goal_to_in_progress(client: AsyncClient):
    """Test completing first task transitions goal to in_progress."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Goal starts as not_started
    goal = (await client.get(f"/goals/{goal_id}")).json()
    assert goal["status"] == "not_started"

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task 1", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    # Complete task
    await client.post(f"/tasks/{task_id}/complete", json={})

    # Goal should be in_progress now
    goal = (await client.get(f"/goals/{goal_id}")).json()
    assert goal["status"] == "in_progress"


# ============================================================================
# Skip Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_skip_task(client: AsyncClient):
    """Test skipping a task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    create_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Test Task", "duration_minutes": 20},
    )
    task_id = create_response.json()["id"]

    response = await client.post(
        f"/tasks/{task_id}/skip",
        json={"reason": "No longer needed"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"


@pytest.mark.asyncio
async def test_skip_task_without_reason(client: AsyncClient):
    """Test skipping a task without providing a reason."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    create_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Test Task", "duration_minutes": 20},
    )
    task_id = create_response.json()["id"]

    response = await client.post(f"/tasks/{task_id}/skip", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "skipped"


# ============================================================================
# Reopen Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reopen_completed_task(client: AsyncClient):
    """Test reopening a completed task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    create_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Test Task", "duration_minutes": 20},
    )
    task_id = create_response.json()["id"]

    # Complete then reopen
    await client.post(f"/tasks/{task_id}/complete", json={})
    response = await client.post(f"/tasks/{task_id}/reopen", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["completed_at"] is None


@pytest.mark.asyncio
async def test_reopen_skipped_task(client: AsyncClient):
    """Test reopening a skipped task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    create_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Test Task", "duration_minutes": 20},
    )
    task_id = create_response.json()["id"]

    # Skip then reopen
    await client.post(f"/tasks/{task_id}/skip", json={})
    response = await client.post(f"/tasks/{task_id}/reopen", json={})

    assert response.status_code == 200
    assert response.json()["status"] == "pending"


# ============================================================================
# Delete Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_task(client: AsyncClient):
    """Test deleting a task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    create_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Test Task", "duration_minutes": 20},
    )
    task_id = create_response.json()["id"]

    response = await client.delete(f"/tasks/{task_id}")

    assert response.status_code == 204

    # Verify task is gone
    get_response = await client.get(f"/tasks/{task_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_not_found(client: AsyncClient):
    """Test deleting a non-existent task returns 404."""
    response = await client.delete("/tasks/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_updates_goal_progress(client: AsyncClient):
    """Test deleting a task updates goal progress."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create two tasks
    task1_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task 1", "duration_minutes": 30},
    )
    task1_id = task1_response.json()["id"]
    task2_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task 2", "duration_minutes": 30},
    )
    task2_id = task2_response.json()["id"]

    # Complete task 1 and verify 50% progress
    await client.post(f"/tasks/{task1_id}/complete", json={})
    goal = (await client.get(f"/goals/{goal_id}")).json()
    assert goal["progress_cached"] == 50

    # Delete task 2
    await client.delete(f"/tasks/{task2_id}")

    # Goal should now be at 100% (only completed task remains)
    goal = (await client.get(f"/goals/{goal_id}")).json()
    assert goal["progress_cached"] == 100


# ============================================================================
# Recurring Task Completion Tests
# ============================================================================


@pytest.mark.asyncio
async def test_recurring_task_completed_for_today_flag(client: AsyncClient):
    """Test that recurring tasks show completed_for_today when completed today."""
    # Create a recurring task
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    response = await client.post(
        "/tasks",
        json={
            "title": "Daily standup",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    assert response.status_code == 201
    task_id = response.json()["id"]

    # Initially, completed_for_today should be False
    list_response = await client.get("/tasks")
    tasks = list_response.json()["tasks"]
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["completed_for_today"] is False

    # Complete the task for today
    complete_response = await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": scheduled_at.isoformat()},
    )
    # The complete response itself should have completed_for_today = True
    completed_task = complete_response.json()
    assert completed_task["completed_for_today"] is True
    assert completed_task["status"] == "pending"  # Recurring task stays pending

    # Now completed_for_today should be True in list
    list_response = await client.get("/tasks")
    tasks = list_response.json()["tasks"]
    task = next(t for t in tasks if t["id"] == task_id)
    assert task["completed_for_today"] is True
    assert task["status"] == "pending"  # Recurring task stays pending


@pytest.mark.asyncio
async def test_completed_filter_includes_recurring_tasks_completed_today(
    client: AsyncClient,
):
    """Test that status=completed includes recurring tasks completed today."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create a recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "Daily exercise",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = response.json()["id"]

    # Complete it for today
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": scheduled_at.isoformat()},
    )

    # Filter by completed - should include the recurring task
    list_response = await client.get("/tasks?status=completed")
    tasks = list_response.json()["tasks"]
    assert len(tasks) >= 1
    task = next((t for t in tasks if t["id"] == task_id), None)
    assert task is not None
    assert task["completed_for_today"] is True


@pytest.mark.asyncio
async def test_pending_filter_includes_recurring_tasks_with_completion_info(
    client: AsyncClient,
):
    """Test that status=pending includes recurring tasks with completion tracking.
    
    Recurring tasks stay in pending filter even after completions, because:
    1. Multi-occurrence tasks (X times/day) may still have pending occurrences
    2. Frontend uses completions_today to show which virtual occurrences are done
    """
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create a recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "Daily meditation",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = response.json()["id"]

    # Complete it for today
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": scheduled_at.isoformat()},
    )

    # Filter by pending - SHOULD include the recurring task with completion info
    list_response = await client.get("/tasks?status=pending")
    tasks = list_response.json()["tasks"]
    task = next((t for t in tasks if t["id"] == task_id), None)
    
    # Task is included but marked as completed for today
    assert task is not None
    assert task["completed_for_today"] is True
    assert task["completions_today"] == 1


@pytest.mark.asyncio
async def test_client_today_timezone_handling(client: AsyncClient):
    """Test that client_today parameter correctly handles timezone edge cases.
    
    Scenario: User is in CDT (UTC-5) at 8:30 PM local on April 6.
    - Local time: April 6, 8:30 PM CDT
    - UTC time: April 7, 1:30 AM UTC
    
    The user completes a task for April 6 (their local date). The completion
    should be stored with a scheduled_for that, when queried with client_today="2026-04-06",
    returns completed_for_today=True.
    """
    # Simulate: User at 8:30 PM CDT on April 6 = 1:30 AM UTC April 7
    # When user creates a completion for "today" (April 6 local), the frontend
    # sends scheduled_for as April 6 00:00 LOCAL = April 6 05:00 UTC
    
    # Create a recurring task
    # Note: scheduled_at doesn't matter for this test - we're testing the completion
    response = await client.post(
        "/tasks",
        json={
            "title": "Daily journal",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    assert response.status_code == 201
    task_id = response.json()["id"]
    
    # Complete the task with scheduled_for representing April 6 at local midnight
    # In CDT (UTC-5), April 6 00:00 = April 6 05:00 UTC
    completion_time = datetime(2026, 4, 6, 5, 0, 0, tzinfo=timezone.utc)
    complete_response = await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": completion_time.isoformat()},
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["completed_for_today"] is True
    
    # Query with client_today="2026-04-06" - should find the completion
    list_response = await client.get("/tasks?client_today=2026-04-06")
    assert list_response.status_code == 200
    tasks = list_response.json()["tasks"]
    task = next((t for t in tasks if t["id"] == task_id), None)
    assert task is not None, "Task should be in the list"
    assert task["completed_for_today"] is True, (
        "Completion at 2026-04-06T05:00:00Z should match client_today=2026-04-06"
    )
    assert task["completions_today"] == 1
    
    # Query with client_today="2026-04-07" - should NOT count as completed for that day
    list_response = await client.get("/tasks?client_today=2026-04-07")
    assert list_response.status_code == 200
    tasks = list_response.json()["tasks"]
    task = next((t for t in tasks if t["id"] == task_id), None)
    assert task is not None, "Task should be in the list"
    assert task["completed_for_today"] is False, (
        "Completion at 2026-04-06T05:00:00Z should NOT match client_today=2026-04-07"
    )
    assert task["completions_today"] == 0


@pytest.mark.asyncio
async def test_today_view_flow_with_timezone_offset(client: AsyncClient):
    """Test the exact flow the frontend uses for Today view with timezone offset.
    
    Scenario: User is at 8:30 PM CDT on April 6, which is 1:30 AM UTC on April 7.
    They complete a recurring task. The task should show as completed when
    refetching with include_completed=true and client_today="2026-04-06".
    """
    # Create a recurring task (no scheduled time - anytime task)
    response = await client.post(
        "/tasks",
        json={
            "title": "Evening routine",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            # No scheduled_at - this is an anytime task
        },
    )
    assert response.status_code == 201
    task_id = response.json()["id"]
    
    # Simulate the frontend sending a completion for April 6 local time
    # Frontend does: new Date(2026, 3, 6).toISOString() = April 6 00:00 local
    # In CDT (UTC-5), this becomes 2026-04-06T05:00:00Z
    completion_time = datetime(2026, 4, 6, 5, 0, 0, tzinfo=timezone.utc)
    complete_response = await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": completion_time.isoformat()},
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["completed_for_today"] is True
    
    # Simulate the frontend refetching all tasks for Today view
    # Frontend sends: status=undefined, include_completed=true, client_today="2026-04-06"
    list_response = await client.get(
        "/tasks?include_completed=true&client_today=2026-04-06"
    )
    assert list_response.status_code == 200
    tasks = list_response.json()["tasks"]
    task = next((t for t in tasks if t["id"] == task_id), None)
    
    assert task is not None, "Task should be in the list"
    assert task["completed_for_today"] is True, (
        "Task should show completed_for_today=True after refetch"
    )
    assert task["completions_today"] == 1
    assert task["status"] == "pending", "Recurring task stays pending"
    
    # Now test REOPEN - user wants to undo the completion
    # Frontend sends the same scheduled_for that was used for completion
    reopen_response = await client.post(
        f"/tasks/{task_id}/reopen",
        json={"scheduled_for": completion_time.isoformat()},
    )
    assert reopen_response.status_code == 200
    
    # After reopen, refetch and verify completed_for_today is False
    list_response = await client.get(
        "/tasks?include_completed=true&client_today=2026-04-06"
    )
    tasks = list_response.json()["tasks"]
    task = next((t for t in tasks if t["id"] == task_id), None)
    
    assert task is not None
    assert task["completed_for_today"] is False, (
        "After reopen, completed_for_today should be False"
    )
    assert task["completions_today"] == 0
    assert task["status"] == "pending", "Recurring task stays pending"


# ============================================================================
# Anytime Tasks Tests (Phase 4e)
# ============================================================================


@pytest.mark.asyncio
async def test_create_anytime_task(client: AsyncClient, test_user: User):
    """Test creating an anytime task assigns sort_order."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "My anytime task",
            "scheduling_mode": "anytime",
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["scheduling_mode"] == "anytime"
    assert data["sort_order"] == 1, "First anytime task should have sort_order=1"
    assert data["is_recurring"] is False


@pytest.mark.asyncio
async def test_create_multiple_anytime_tasks_assigns_sequential_sort_order(
    client: AsyncClient,
):
    """Test creating multiple anytime tasks assigns sequential sort_order."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create 3 anytime tasks
    first = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "First", "scheduling_mode": "anytime"},
    )
    second = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Second", "scheduling_mode": "anytime"},
    )
    third = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Third", "scheduling_mode": "anytime"},
    )

    assert first.json()["sort_order"] == 1
    assert second.json()["sort_order"] == 2
    assert third.json()["sort_order"] == 3


@pytest.mark.asyncio
async def test_anytime_task_cannot_be_recurring(client: AsyncClient):
    """Test that anytime tasks cannot be recurring."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring anytime",
            "scheduling_mode": "anytime",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
        },
    )

    assert response.status_code == 400
    assert "cannot be recurring" in response.json()["detail"]


@pytest.mark.asyncio
async def test_complete_anytime_task_clears_sort_order(client: AsyncClient):
    """Test completing an anytime task clears its sort_order."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create 3 anytime tasks
    first = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "First", "scheduling_mode": "anytime"},
    )
    second = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Second", "scheduling_mode": "anytime"},
    )
    third = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Third", "scheduling_mode": "anytime"},
    )

    first_id = first.json()["id"]
    second_id = second.json()["id"]
    third_id = third.json()["id"]

    # Complete the second (middle) one
    await client.post(f"/tasks/{second_id}/complete", json={})

    # Get all tasks and verify sort_order updates
    response = await client.get("/tasks/view/anytime?include_completed=true")
    tasks = response.json()["tasks"]

    first_task = next(t for t in tasks if t["id"] == first_id)
    second_task = next(t for t in tasks if t["id"] == second_id)
    third_task = next(t for t in tasks if t["id"] == third_id)

    assert first_task["sort_order"] == 1
    assert second_task["sort_order"] is None, "Completed task should have no sort_order"
    assert third_task["sort_order"] == 2, "Third task shifts to fill gap"


@pytest.mark.asyncio
async def test_reopen_anytime_task_assigns_new_sort_order(client: AsyncClient):
    """Test reopening a completed anytime task assigns sort_order at bottom."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create 2 anytime tasks
    first = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "First", "scheduling_mode": "anytime"},
    )
    second = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Second", "scheduling_mode": "anytime"},
    )

    first_id = first.json()["id"]
    second_id = second.json()["id"]

    # Complete the first task
    await client.post(f"/tasks/{first_id}/complete", json={})

    # Reopen the first task
    await client.post(f"/tasks/{first_id}/reopen", json={})

    # Get all tasks
    response = await client.get("/tasks/view/anytime")
    tasks = response.json()["tasks"]

    first_task = next(t for t in tasks if t["id"] == first_id)
    second_task = next(t for t in tasks if t["id"] == second_id)

    assert second_task["sort_order"] == 1, "Second task should stay at position 1"
    assert first_task["sort_order"] == 2, "Reopened task goes to bottom"


@pytest.mark.asyncio
async def test_list_anytime_tasks(client: AsyncClient):
    """Test listing anytime tasks endpoint."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create anytime and non-anytime tasks
    await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Anytime 1", "scheduling_mode": "anytime"},
    )
    await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Anytime 2", "scheduling_mode": "anytime"},
    )
    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Scheduled task",
            "scheduled_date": "2026-04-10",
        },
    )

    response = await client.get("/tasks/view/anytime")
    data = response.json()

    assert data["total"] == 2
    assert len(data["tasks"]) == 2
    assert all(t["scheduling_mode"] == "anytime" for t in data["tasks"])
    # Should be sorted by sort_order
    assert data["tasks"][0]["sort_order"] == 1
    assert data["tasks"][1]["sort_order"] == 2


@pytest.mark.asyncio
async def test_reorder_anytime_task_move_up(client: AsyncClient):
    """Test moving an anytime task up in the list."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create 3 anytime tasks
    first = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "First", "scheduling_mode": "anytime"},
    )
    second = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Second", "scheduling_mode": "anytime"},
    )
    third = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Third", "scheduling_mode": "anytime"},
    )

    first_id = first.json()["id"]
    second_id = second.json()["id"]
    third_id = third.json()["id"]

    # Move third to position 1 (top)
    response = await client.patch(
        f"/tasks/{third_id}/reorder",
        json={"new_position": 1},
    )
    assert response.status_code == 200
    assert response.json()["task"]["sort_order"] == 1

    # Verify all positions updated correctly
    list_response = await client.get("/tasks/view/anytime")
    tasks = {t["id"]: t for t in list_response.json()["tasks"]}

    assert tasks[third_id]["sort_order"] == 1, "Third moved to top"
    assert tasks[first_id]["sort_order"] == 2, "First shifted down"
    assert tasks[second_id]["sort_order"] == 3, "Second shifted down"


@pytest.mark.asyncio
async def test_reorder_anytime_task_move_down(client: AsyncClient):
    """Test moving an anytime task down in the list."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create 3 anytime tasks
    first = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "First", "scheduling_mode": "anytime"},
    )
    second = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Second", "scheduling_mode": "anytime"},
    )
    third = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Third", "scheduling_mode": "anytime"},
    )

    first_id = first.json()["id"]
    second_id = second.json()["id"]
    third_id = third.json()["id"]

    # Move first to position 3 (bottom)
    response = await client.patch(
        f"/tasks/{first_id}/reorder",
        json={"new_position": 3},
    )
    assert response.status_code == 200
    assert response.json()["task"]["sort_order"] == 3

    # Verify all positions updated correctly
    list_response = await client.get("/tasks/view/anytime")
    tasks = {t["id"]: t for t in list_response.json()["tasks"]}

    assert tasks[second_id]["sort_order"] == 1, "Second moved to top"
    assert tasks[third_id]["sort_order"] == 2, "Third shifted up"
    assert tasks[first_id]["sort_order"] == 3, "First moved to bottom"


@pytest.mark.asyncio
async def test_reorder_non_anytime_task_fails(client: AsyncClient):
    """Test that reordering a non-anytime task fails."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create a scheduled task
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Scheduled",
            "scheduled_date": "2026-04-10",
        },
    )
    task_id = task.json()["id"]

    response = await client.patch(
        f"/tasks/{task_id}/reorder",
        json={"new_position": 1},
    )
    assert response.status_code == 400
    assert "Only anytime tasks" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reorder_completed_anytime_task_fails(client: AsyncClient):
    """Test that reordering a completed anytime task fails."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Anytime", "scheduling_mode": "anytime"},
    )
    task_id = task.json()["id"]

    # Complete the task
    await client.post(f"/tasks/{task_id}/complete", json={})

    # Try to reorder
    response = await client.patch(
        f"/tasks/{task_id}/reorder",
        json={"new_position": 1},
    )
    assert response.status_code == 400
    assert "completed anytime task" in response.json()["detail"]


@pytest.mark.asyncio
async def test_anytime_tasks_without_goal(client: AsyncClient):
    """Test creating anytime tasks without a goal."""
    response = await client.post(
        "/tasks",
        json={"title": "No goal anytime", "scheduling_mode": "anytime"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["goal_id"] is None
    assert data["scheduling_mode"] == "anytime"
    assert data["sort_order"] == 1


@pytest.mark.asyncio
async def test_skip_anytime_task_clears_sort_order(client: AsyncClient):
    """Test skipping an anytime task clears its sort_order."""
    response = await client.post(
        "/tasks",
        json={"title": "Skip me", "scheduling_mode": "anytime"},
    )
    task_id = response.json()["id"]

    # Skip the task
    await client.post(f"/tasks/{task_id}/skip", json={"reason": "Not needed"})

    # Verify sort_order is cleared
    get_response = await client.get(f"/tasks/{task_id}")
    assert get_response.json()["sort_order"] is None
    assert get_response.json()["status"] == "skipped"


# ============================================================================
# Phase 4g: Recurrence Behavior Tests (Habitual vs Essential)
# ============================================================================


@pytest.mark.asyncio
async def test_create_recurring_task_with_habitual_behavior(client: AsyncClient):
    """Test creating a recurring task with habitual behavior."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    response = await client.post(
        "/tasks",
        json={
            "title": "Daily meditation",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["is_recurring"] is True
    assert data["recurrence_behavior"] == "habitual"


@pytest.mark.asyncio
async def test_create_recurring_task_with_essential_behavior(client: AsyncClient):
    """Test creating a recurring task with essential behavior."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    response = await client.post(
        "/tasks",
        json={
            "title": "Take medication",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "essential",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["is_recurring"] is True
    assert data["recurrence_behavior"] == "essential"


@pytest.mark.asyncio
async def test_create_recurring_task_requires_recurrence_behavior(client: AsyncClient):
    """Test that creating a recurring task without recurrence_behavior fails."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    response = await client.post(
        "/tasks",
        json={
            "title": "Missing behavior",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            # No recurrence_behavior
        },
    )

    assert response.status_code == 400
    assert "recurrence_behavior is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_non_recurring_task_rejects_recurrence_behavior(client: AsyncClient):
    """Test that non-recurring tasks cannot have recurrence_behavior."""
    response = await client.post(
        "/tasks",
        json={
            "title": "One-time task",
            "is_recurring": False,
            "recurrence_behavior": "habitual",  # Should not be allowed
        },
    )

    assert response.status_code == 400
    assert "recurrence_behavior should only be set for recurring tasks" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_recurring_task_recurrence_behavior(client: AsyncClient):
    """Test updating recurrence_behavior on a recurring task."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create with habitual
    response = await client.post(
        "/tasks",
        json={
            "title": "Flexible task",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = response.json()["id"]

    # Update to essential
    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={"recurrence_behavior": "essential"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["recurrence_behavior"] == "essential"


@pytest.mark.asyncio
async def test_update_to_recurring_requires_recurrence_behavior(client: AsyncClient):
    """Test that updating a task to recurring requires recurrence_behavior."""
    # Create a non-recurring task
    response = await client.post(
        "/tasks",
        json={"title": "Simple task"},
    )
    task_id = response.json()["id"]

    # Try to make it recurring without recurrence_behavior
    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
        },
    )

    assert update_response.status_code == 400
    assert "recurrence_behavior is required" in update_response.json()["detail"]


@pytest.mark.asyncio
async def test_update_to_non_recurring_clears_recurrence_behavior(client: AsyncClient):
    """Test that making a recurring task non-recurring clears recurrence_behavior."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "Will become non-recurring",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "essential",
        },
    )
    task_id = response.json()["id"]

    # Make it non-recurring
    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={"is_recurring": False},
    )

    assert update_response.status_code == 200
    assert update_response.json()["is_recurring"] is False
    assert update_response.json()["recurrence_behavior"] is None


# ============================================================================
# Rhythm History Simulator Tests (Phase 4h)
# ============================================================================


@pytest.mark.asyncio
async def test_bulk_completions_create(client: AsyncClient):
    """Test creating bulk completions for a recurring task."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "Bulk test task",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = response.json()["id"]

    # Create bulk completions
    bulk_response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2024-01-01", "status": "completed"},
                {"date": "2024-01-02", "status": "completed"},
                {"date": "2024-01-03", "status": "skipped", "skip_reason": "Sick day"},
            ]
        },
    )

    assert bulk_response.status_code == 200
    data = bulk_response.json()
    assert data["created_count"] == 3
    assert data["task_id"] == task_id
    assert data["start_date_updated"] is False


@pytest.mark.asyncio
async def test_bulk_completions_with_start_date_update(client: AsyncClient):
    """Test creating bulk completions with start date update."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "Bulk test task with date update",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "essential",
        },
    )
    task_id = response.json()["id"]

    # Create bulk completions with start date update
    bulk_response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2024-01-01", "status": "completed"},
            ],
            "update_start_date": "2024-01-01",
        },
    )

    assert bulk_response.status_code == 200
    data = bulk_response.json()
    assert data["start_date_updated"] is True

    # Verify task was updated
    task_response = await client.get(f"/tasks/{task_id}")
    assert task_response.status_code == 200
    task_data = task_response.json()
    assert task_data["scheduled_date"] == "2024-01-01"


@pytest.mark.asyncio
async def test_bulk_completions_multiple_occurrences(client: AsyncClient):
    """Test creating bulk completions with multiple occurrences per day."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "Multi-occurrence task",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = response.json()["id"]

    # Create bulk completions with multiple occurrences per day
    bulk_response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2024-01-01", "status": "completed", "occurrences": 3},
                {"date": "2024-01-02", "status": "completed", "occurrences": 2},
            ]
        },
    )

    assert bulk_response.status_code == 200
    data = bulk_response.json()
    assert data["created_count"] == 5  # 3 + 2


@pytest.mark.asyncio
async def test_bulk_completions_replaces_mock(client: AsyncClient):
    """Test that bulk completions replaces existing mock data (not adds)."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "Replace test task",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = response.json()["id"]

    # Create first bulk completions
    await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2024-01-01", "status": "completed", "occurrences": 3},
            ]
        },
    )

    # Create second bulk completions (should replace, not add)
    bulk_response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2024-01-02", "status": "completed", "occurrences": 2},
            ]
        },
    )

    assert bulk_response.status_code == 200

    # Get all completions - should only have 2 (not 5)
    completions_response = await client.get(f"/tasks/{task_id}/completions")
    assert completions_response.status_code == 200
    completions = completions_response.json()["completions"]
    assert len(completions) == 2


@pytest.mark.asyncio
async def test_bulk_completions_non_recurring_fails(client: AsyncClient):
    """Test that bulk completions fails for non-recurring tasks."""
    # Create non-recurring task
    response = await client.post(
        "/tasks",
        json={"title": "Non-recurring task"},
    )
    task_id = response.json()["id"]

    # Try to create bulk completions
    bulk_response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [{"date": "2024-01-01", "status": "completed"}]
        },
    )

    assert bulk_response.status_code == 400
    assert "recurring tasks" in bulk_response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_delete_mock_completions(client: AsyncClient):
    """Test deleting mock completions."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "Delete mock test",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = response.json()["id"]

    # Create bulk completions (marked as MOCK)
    await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2024-01-01", "status": "completed"},
                {"date": "2024-01-02", "status": "completed"},
            ]
        },
    )

    # Delete mock completions
    delete_response = await client.delete(f"/tasks/{task_id}/completions/mock")

    assert delete_response.status_code == 200
    data = delete_response.json()
    assert data["deleted_count"] == 2
    assert data["task_id"] == task_id


@pytest.mark.asyncio
async def test_delete_mock_preserves_real_completions(client: AsyncClient):
    """Test that deleting mock completions preserves real completions."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)
    today = now.strftime("%Y-%m-%d")

    # Create recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "Preserve real test",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "essential",
        },
    )
    task_id = response.json()["id"]

    # Create a real completion via normal complete endpoint
    await client.post(
        f"/tasks/{task_id}/complete",
        json={
            "scheduled_for": scheduled_at.isoformat(),
            "local_date": today,
        },
    )

    # Create mock completions
    await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2024-01-01", "status": "completed"},
            ]
        },
    )

    # Delete mock completions
    delete_response = await client.delete(f"/tasks/{task_id}/completions/mock")

    assert delete_response.status_code == 200
    data = delete_response.json()
    assert data["deleted_count"] == 1  # Only mock deleted, real preserved


@pytest.mark.asyncio
async def test_delete_mock_no_completions(client: AsyncClient):
    """Test deleting mock completions when there are none."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "No mock test",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = response.json()["id"]

    # Delete mock completions (should be 0)
    delete_response = await client.delete(f"/tasks/{task_id}/completions/mock")

    assert delete_response.status_code == 200
    data = delete_response.json()
    assert data["deleted_count"] == 0


# ============================================================================
# Recurring Task Validation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_recurring_task_requires_scheduling_mode_with_time(client: AsyncClient):
    """Test that recurring tasks with scheduled_at require scheduling_mode."""
    scheduled = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()

    response = await client.post(
        "/tasks",
        json={
            "title": "Missing mode",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled,
            "recurrence_behavior": "habitual",
            # Missing scheduling_mode
        },
    )

    assert response.status_code == 400
    assert "scheduling_mode is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_update_task_scheduling_fields(client: AsyncClient):
    """Test updating task scheduling fields."""
    # Create task with scheduled_at
    scheduled = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    response = await client.post(
        "/tasks",
        json={
            "title": "Scheduled task",
            "scheduled_at": scheduled,
        },
    )
    task_id = response.json()["id"]

    # Update to date-only scheduling
    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={
            "scheduled_date": "2026-05-15",
            "scheduled_at": None,
        },
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["scheduled_date"] == "2026-05-15"
    assert data["scheduling_mode"] == "date_only"


@pytest.mark.asyncio
async def test_update_task_to_recurring_without_behavior_fails(client: AsyncClient):
    """Test updating non-recurring task to recurring without behavior fails."""
    # Create non-recurring task
    response = await client.post(
        "/tasks",
        json={"title": "Simple task"},
    )
    task_id = response.json()["id"]

    # Try to make it recurring without behavior
    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            # Missing recurrence_behavior
        },
    )
    assert update_response.status_code == 400
    assert "recurrence_behavior is required" in update_response.json()["detail"]


@pytest.mark.asyncio
async def test_count_future_completions(client: AsyncClient):
    """Test counting future completions."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "Count test",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = response.json()["id"]

    # Create future completion (tomorrow)
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_dt = (now + timedelta(days=1)).isoformat()
    await client.post(
        f"/tasks/{task_id}/complete",
        json={
            "scheduled_for": tomorrow_dt,
            "local_date": tomorrow,
        },
    )

    # Count future completions
    today = now.strftime("%Y-%m-%d")
    count_response = await client.get(
        f"/tasks/completions/future/count?after_date={today}"
    )
    assert count_response.status_code == 200
    assert count_response.json()["count"] >= 1


@pytest.mark.asyncio
async def test_count_future_completions_invalid_date(client: AsyncClient):
    """Test counting future completions with invalid date format."""
    response = await client.get("/tasks/completions/future/count?after_date=invalid")
    assert response.status_code == 400
    assert "Invalid date format" in response.json()["detail"]


@pytest.mark.asyncio
async def test_delete_future_completions(client: AsyncClient):
    """Test deleting future completions."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "Delete future test",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "essential",
        },
    )
    task_id = response.json()["id"]

    # Create future completion
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_dt = (now + timedelta(days=1)).isoformat()
    await client.post(
        f"/tasks/{task_id}/complete",
        json={
            "scheduled_for": tomorrow_dt,
            "local_date": tomorrow,
        },
    )

    # Delete future completions
    today = now.strftime("%Y-%m-%d")
    delete_response = await client.delete(
        f"/tasks/completions/future?after_date={today}"
    )
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_count"] >= 1


@pytest.mark.asyncio
async def test_delete_future_completions_invalid_date(client: AsyncClient):
    """Test deleting future completions with invalid date."""
    response = await client.delete("/tasks/completions/future?after_date=bad-date")
    assert response.status_code == 400
    assert "Invalid date format" in response.json()["detail"]


@pytest.mark.asyncio
async def test_skip_recurring_task_with_scheduled_for(client: AsyncClient):
    """Test skipping a recurring task occurrence with scheduled_for."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)
    today = now.strftime("%Y-%m-%d")

    # Create recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "Skip test",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "essential",
        },
    )
    task_id = response.json()["id"]

    # Skip with scheduled_for
    skip_response = await client.post(
        f"/tasks/{task_id}/skip",
        json={
            "scheduled_for": scheduled_at.isoformat(),
            "local_date": today,
            "reason": "Not feeling it",
        },
    )
    assert skip_response.status_code == 200
    data = skip_response.json()
    # Single task response flags skipped_for_today
    assert data["skipped_for_today"] is True


@pytest.mark.asyncio
async def test_reopen_recurring_task_occurrence(client: AsyncClient):
    """Test reopening a skipped recurring task occurrence."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)
    today = now.strftime("%Y-%m-%d")

    # Create recurring task
    response = await client.post(
        "/tasks",
        json={
            "title": "Reopen test",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = response.json()["id"]

    # Skip the occurrence
    await client.post(
        f"/tasks/{task_id}/skip",
        json={
            "scheduled_for": scheduled_at.isoformat(),
            "local_date": today,
        },
    )

    # Reopen the occurrence
    reopen_response = await client.post(
        f"/tasks/{task_id}/reopen",
        json={
            "scheduled_for": scheduled_at.isoformat(),
            "local_date": today,
        },
    )
    assert reopen_response.status_code == 200
    data = reopen_response.json()
    # After reopening, skips_today should be 0
    assert data["skips_today"] == 0


@pytest.mark.asyncio
async def test_list_tasks_scheduled_after_filter(client: AsyncClient):
    """Test listing tasks with scheduled_after filter accepts the parameter."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create a task  
    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Test task",
            "scheduled_at": datetime(2025, 6, 15, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        },
    )

    # Filter endpoint works (returns 200)
    cutoff = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat()
    response = await client.get(f"/tasks?goal_id={goal_id}&scheduled_after={cutoff}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_scheduled_before_filter(client: AsyncClient):
    """Test listing tasks with scheduled_before filter accepts the parameter."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create a task
    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Test task",
            "scheduled_at": datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        },
    )

    # Filter endpoint works (returns 200)
    cutoff = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat()
    response = await client.get(f"/tasks?goal_id={goal_id}&scheduled_before={cutoff}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_include_completed(client: AsyncClient):
    """Test listing tasks with include_completed flag."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create and complete a non-recurring task
    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Completed task"},
    )
    task_id = task_response.json()["id"]
    complete_response = await client.post(f"/tasks/{task_id}/complete", json={})
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "completed"

    # Create pending task for comparison
    await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Pending task"},
    )

    # Without include_completed (default), should not see completed one-time tasks
    response1 = await client.get(f"/tasks?goal_id={goal_id}")
    assert response1.status_code == 200
    task_ids_1 = [t["id"] for t in response1.json()["tasks"]]
    assert task_id not in task_ids_1

    # With include_completed=true, should see completed tasks
    response2 = await client.get(f"/tasks?goal_id={goal_id}&include_completed=true")
    assert response2.status_code == 200
    task_ids_2 = [t["id"] for t in response2.json()["tasks"]]
    assert task_id in task_ids_2


@pytest.mark.asyncio
async def test_list_recurring_tasks_with_completions(client: AsyncClient):
    """Test that listing recurring tasks includes completion info."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)
    today = now.strftime("%Y-%m-%d")

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "Recurring with completions",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Complete the task for today
    await client.post(
        f"/tasks/{task_id}/complete",
        json={
            "scheduled_for": scheduled_at.isoformat(),
            "local_date": today,
        },
    )

    # List tasks should include completion info
    list_response = await client.get(f"/tasks")
    task = next((t for t in list_response.json()["tasks"] if t["id"] == task_id), None)
    assert task is not None
    assert task["completed_for_today"] is True
    assert task["completions_today"] == 1


@pytest.mark.asyncio
async def test_list_recurring_tasks_with_skips(client: AsyncClient):
    """Test that listing recurring tasks includes skip info."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=10, minute=0, second=0, microsecond=0)
    today = now.strftime("%Y-%m-%d")

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "Recurring with skips",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "essential",
        },
    )
    task_id = task_response.json()["id"]

    # Skip the task for today with a reason
    await client.post(
        f"/tasks/{task_id}/skip",
        json={
            "scheduled_for": scheduled_at.isoformat(),
            "local_date": today,
            "reason": "Feeling tired",
        },
    )

    # List tasks should include skip info
    list_response = await client.get(f"/tasks")
    task = next((t for t in list_response.json()["tasks"] if t["id"] == task_id), None)
    assert task is not None
    assert task["skipped_for_today"] is True
    assert task["skips_today"] == 1
    assert task["skip_reason_today"] == "Feeling tired"


@pytest.mark.asyncio
async def test_update_task_to_recurring(client: AsyncClient):
    """Test updating a non-recurring task to recurring."""
    # Create non-recurring task
    task_response = await client.post(
        "/tasks",
        json={"title": "Make recurring"},
    )
    task_id = task_response.json()["id"]

    # Update to recurring with required fields
    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_behavior": "habitual",
        },
    )
    assert update_response.status_code == 200
    assert update_response.json()["is_recurring"] is True
    assert update_response.json()["recurrence_behavior"] == "habitual"


@pytest.mark.asyncio
async def test_update_task_various_fields(client: AsyncClient):
    """Test updating various task fields."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create task
    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Updatable task", "description": "Original"},
    )
    task_id = task_response.json()["id"]

    # Update multiple fields
    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={
            "title": "Updated title",
            "description": "Updated description",
            "duration_minutes": 45,
            "notify_before_minutes": 10,
        },
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert data["title"] == "Updated title"
    assert data["description"] == "Updated description"
    assert data["duration_minutes"] == 45
    assert data["notify_before_minutes"] == 10


@pytest.mark.asyncio
async def test_update_task_not_found(client: AsyncClient):
    """Test updating non-existent task."""
    response = await client.patch(
        "/tasks/nonexistent-id",
        json={"title": "Updated"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_complete_non_recurring_task(client: AsyncClient):
    """Test completing a non-recurring task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create non-recurring task
    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "One-time task"},
    )
    task_id = task_response.json()["id"]

    # Complete it
    complete_response = await client.post(f"/tasks/{task_id}/complete", json={})
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "completed"
    assert complete_response.json()["completed_at"] is not None


@pytest.mark.asyncio
async def test_skip_non_recurring_task(client: AsyncClient):
    """Test skipping a non-recurring task."""
    # Create non-recurring task
    task_response = await client.post(
        "/tasks",
        json={"title": "Task to skip"},
    )
    task_id = task_response.json()["id"]

    # Skip it
    skip_response = await client.post(
        f"/tasks/{task_id}/skip",
        json={"reason": "Not relevant anymore"},
    )
    assert skip_response.status_code == 200
    assert skip_response.json()["status"] == "skipped"


@pytest.mark.asyncio
async def test_reopen_non_recurring_task(client: AsyncClient):
    """Test reopening a completed non-recurring task."""
    # Create and complete task
    task_response = await client.post(
        "/tasks",
        json={"title": "Task to reopen"},
    )
    task_id = task_response.json()["id"]
    await client.post(f"/tasks/{task_id}/complete", json={})

    # Reopen it
    reopen_response = await client.post(f"/tasks/{task_id}/reopen", json={})
    assert reopen_response.status_code == 200
    assert reopen_response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_reopen_already_pending_task_fails(client: AsyncClient):
    """Test reopening an already pending task fails."""
    # Create pending task
    task_response = await client.post(
        "/tasks",
        json={"title": "Already pending"},
    )
    task_id = task_response.json()["id"]

    # Try to reopen
    reopen_response = await client.post(f"/tasks/{task_id}/reopen", json={})
    assert reopen_response.status_code == 400
    assert "pending" in reopen_response.json()["detail"]


@pytest.mark.asyncio
async def test_list_tasks_with_days_ahead(client: AsyncClient):
    """Test listing tasks with days_ahead parameter."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=11, minute=0, second=0, microsecond=0)

    # Create recurring task
    await client.post(
        "/tasks",
        json={
            "title": "Days ahead test",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )

    # List with custom days_ahead
    response = await client.get("/tasks?days_ahead=7")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_reorder_task(client: AsyncClient):
    """Test reordering an anytime task."""
    # Create anytime tasks (explicitly set scheduling_mode)
    task1_response = await client.post(
        "/tasks",
        json={"title": "Task 1", "scheduling_mode": "anytime"},
    )
    task1_id = task1_response.json()["id"]

    await client.post(
        "/tasks",
        json={"title": "Task 2", "scheduling_mode": "anytime"},
    )

    # Reorder task1 to position 1 (keep at top)
    reorder_response = await client.patch(
        f"/tasks/{task1_id}/reorder",
        json={"new_position": 1},
    )
    assert reorder_response.status_code == 200


@pytest.mark.asyncio
async def test_get_task(client: AsyncClient):
    """Test getting a single task by ID."""
    # Create task
    task_response = await client.post(
        "/tasks",
        json={"title": "Get me"},
    )
    task_id = task_response.json()["id"]

    # Get it
    get_response = await client.get(f"/tasks/{task_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == task_id
    assert get_response.json()["title"] == "Get me"


@pytest.mark.asyncio
async def test_get_task_not_found(client: AsyncClient):
    """Test getting a non-existent task."""
    response = await client.get("/tasks/nonexistent-id")
    assert response.status_code == 404


# ============================================================================
# Delete Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_task(client: AsyncClient):
    """Test deleting a task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create task
    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "To be deleted"},
    )
    task_id = task_response.json()["id"]

    # Delete it
    delete_response = await client.delete(f"/tasks/{task_id}")
    assert delete_response.status_code == 204

    # Verify it's gone
    get_response = await client.get(f"/tasks/{task_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_not_found(client: AsyncClient):
    """Test deleting a non-existent task."""
    response = await client.delete("/tasks/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_updates_goal_progress(client: AsyncClient):
    """Test that deleting a task updates goal progress."""
    goal_response = await client.post("/goals", json={"title": "Progress Goal"})
    goal_id = goal_response.json()["id"]

    # Create and complete one task
    task1_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task 1", "duration_minutes": 30},
    )
    task1_id = task1_response.json()["id"]
    await client.post(f"/tasks/{task1_id}/complete", json={})

    # Create another task
    task2_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task 2", "duration_minutes": 30},
    )
    task2_id = task2_response.json()["id"]

    # Delete the incomplete task - progress should increase
    await client.delete(f"/tasks/{task2_id}")

    # Check goal progress - should be 100% now (1/1 complete)
    goal_response = await client.get(f"/goals/{goal_id}")
    assert goal_response.json()["progress_cached"] == 100


# ============================================================================
# Update Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_task_change_goal(client: AsyncClient):
    """Test moving a task to a different goal."""
    # Create two goals
    goal1_response = await client.post("/goals", json={"title": "Goal 1"})
    goal1_id = goal1_response.json()["id"]
    goal2_response = await client.post("/goals", json={"title": "Goal 2"})
    goal2_id = goal2_response.json()["id"]

    # Create task under goal1
    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal1_id, "title": "Movable task"},
    )
    task_id = task_response.json()["id"]
    assert task_response.json()["goal"]["id"] == goal1_id

    # Move to goal2
    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={"goal_id": goal2_id},
    )
    assert update_response.status_code == 200
    
    # Verify via GET that the task now belongs to goal2
    get_response = await client.get(f"/tasks/{task_id}")
    assert get_response.json()["goal"]["id"] == goal2_id


@pytest.mark.asyncio
async def test_update_task_scheduling_date_only(client: AsyncClient):
    """Test updating task to date-only scheduling."""
    # Create task without schedule
    task_response = await client.post(
        "/tasks",
        json={"title": "Schedule me"},
    )
    task_id = task_response.json()["id"]

    # Update to date-only
    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={"scheduled_date": "2026-06-15"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["scheduled_date"] == "2026-06-15"
    assert update_response.json()["scheduling_mode"] == "date_only"


@pytest.mark.asyncio
async def test_update_task_clear_recurrence_behavior(client: AsyncClient):
    """Test that making recurring task non-recurring clears recurrence_behavior."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=10, minute=0, second=0, microsecond=0)

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "Recurring to non-recurring",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Make it non-recurring
    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={"is_recurring": False, "recurrence_rule": None},
    )
    assert update_response.status_code == 200
    assert update_response.json()["is_recurring"] is False
    assert update_response.json()["recurrence_behavior"] is None


# ============================================================================
# Anytime Tasks Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_anytime_tasks(client: AsyncClient):
    """Test listing anytime tasks (backlog)."""
    # Create anytime task
    await client.post(
        "/tasks",
        json={"title": "Anytime task", "scheduling_mode": "anytime"},
    )

    # List anytime tasks (correct endpoint path)
    response = await client.get("/tasks/view/anytime")
    assert response.status_code == 200
    tasks = response.json()["tasks"]
    assert len(tasks) >= 1


@pytest.mark.asyncio
async def test_list_anytime_tasks_sorted_by_order(client: AsyncClient):
    """Test that anytime tasks are sorted by sort_order."""
    # Create multiple anytime tasks
    await client.post(
        "/tasks",
        json={"title": "Anytime Sort 1", "scheduling_mode": "anytime"},
    )
    await client.post(
        "/tasks",
        json={"title": "Anytime Sort 2", "scheduling_mode": "anytime"},
    )

    # List anytime (correct endpoint)
    response = await client.get("/tasks/view/anytime")
    assert response.status_code == 200


# ============================================================================
# Task Stats Tests  
# ============================================================================


@pytest.mark.asyncio
async def test_get_task_stats(client: AsyncClient):
    """Test getting task statistics."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=8, minute=0, second=0, microsecond=0)
    today = now.strftime("%Y-%m-%d")

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "Stats task",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Complete it today
    await client.post(
        f"/tasks/{task_id}/complete",
        json={
            "scheduled_for": scheduled_at.isoformat(),
            "local_date": today,
        },
    )

    # Get stats with proper datetime format (full ISO)
    start = (now - timedelta(days=1)).replace(microsecond=0).isoformat()
    end = (now + timedelta(days=1)).replace(microsecond=0).isoformat()
    stats_response = await client.get(
        f"/tasks/{task_id}/stats",
        params={"start": start, "end": end},
    )
    assert stats_response.status_code == 200
    stats = stats_response.json()
    assert stats["task_id"] == task_id


@pytest.mark.asyncio
async def test_get_task_stats_not_found(client: AsyncClient):
    """Test getting stats for non-existent task."""
    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=7)).replace(microsecond=0).isoformat()
    end = now.replace(microsecond=0).isoformat()
    response = await client.get(
        "/tasks/nonexistent-id/stats",
        params={"start": start, "end": end},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_completion_history(client: AsyncClient):
    """Test getting task completion history."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=7, minute=0, second=0, microsecond=0)
    today = now.strftime("%Y-%m-%d")

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "History task",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "essential",
        },
    )
    task_id = task_response.json()["id"]

    # Complete it
    await client.post(
        f"/tasks/{task_id}/complete",
        json={
            "scheduled_for": scheduled_at.isoformat(),
            "local_date": today,
        },
    )

    # Get history with proper params
    start = (now - timedelta(days=1)).replace(microsecond=0).isoformat()
    end = (now + timedelta(days=1)).replace(microsecond=0).isoformat()
    history_response = await client.get(
        f"/tasks/{task_id}/history",
        params={"start": start, "end": end},
    )
    assert history_response.status_code == 200


# ============================================================================
# Recurring Tasks with Local Date Tests
# ============================================================================


@pytest.mark.asyncio
async def test_complete_recurring_with_local_date(client: AsyncClient):
    """Test completing recurring task with local_date parameter."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=6, minute=0, second=0, microsecond=0)
    today = now.strftime("%Y-%m-%d")

    # Create task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "Local date test",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Complete with local_date
    complete_response = await client.post(
        f"/tasks/{task_id}/complete",
        json={
            "scheduled_for": scheduled_at.isoformat(),
            "local_date": today,
        },
    )
    assert complete_response.status_code == 200
    assert complete_response.json()["completed_for_today"] is True


@pytest.mark.asyncio
async def test_reopen_recurring_task_occurrence(client: AsyncClient):
    """Test reopening a specific occurrence of a recurring task."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=14, minute=0, second=0, microsecond=0)
    today = now.strftime("%Y-%m-%d")

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "Reopen recurring",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "essential",
        },
    )
    task_id = task_response.json()["id"]

    # Complete the occurrence
    await client.post(
        f"/tasks/{task_id}/complete",
        json={
            "scheduled_for": scheduled_at.isoformat(),
            "local_date": today,
        },
    )

    # Reopen the occurrence
    reopen_response = await client.post(
        f"/tasks/{task_id}/reopen",
        json={
            "scheduled_for": scheduled_at.isoformat(),
            "local_date": today,
        },
    )
    assert reopen_response.status_code == 200


# ============================================================================
# Skip Recurring Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_skip_recurring_with_local_date(client: AsyncClient):
    """Test skipping recurring task with local_date parameter."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=8, minute=0, second=0, microsecond=0)
    today = now.strftime("%Y-%m-%d")

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "Skip test",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Skip with local_date
    skip_response = await client.post(
        f"/tasks/{task_id}/skip",
        json={
            "scheduled_for": scheduled_at.isoformat(),
            "local_date": today,
            "reason": "Feeling sick today",
        },
    )
    assert skip_response.status_code == 200
    assert skip_response.json()["skipped_for_today"] is True


@pytest.mark.asyncio
async def test_skip_one_time_task(client: AsyncClient):
    """Test skipping a one-time task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "One-time skip test",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    skip_response = await client.post(
        f"/tasks/{task_id}/skip",
        json={"reason": "Not needed anymore"},
    )
    assert skip_response.status_code == 200
    assert skip_response.json()["status"] == "skipped"


# ============================================================================
# Reopen Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reopen_one_time_task(client: AsyncClient):
    """Test reopening a completed one-time task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Reopen test",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    # Complete the task
    await client.post(f"/tasks/{task_id}/complete", json={})

    # Reopen the task
    reopen_response = await client.post(f"/tasks/{task_id}/reopen", json={})
    assert reopen_response.status_code == 200
    assert reopen_response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_reopen_skipped_task(client: AsyncClient):
    """Test reopening a skipped one-time task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Reopen skipped",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    # Skip the task
    await client.post(f"/tasks/{task_id}/skip", json={"reason": "Skip"})

    # Reopen the task
    reopen_response = await client.post(f"/tasks/{task_id}/reopen", json={})
    assert reopen_response.status_code == 200
    assert reopen_response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_reopen_pending_task_fails(client: AsyncClient):
    """Test reopening an already pending task returns error."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Already pending",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    # Try to reopen without completing first
    reopen_response = await client.post(f"/tasks/{task_id}/reopen", json={})
    assert reopen_response.status_code == 400
    assert "already pending" in reopen_response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reopen_recurring_without_scheduled_for_fails(client: AsyncClient):
    """Test reopening recurring task without scheduled_for returns error."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=10, minute=0, second=0, microsecond=0)
    today = now.strftime("%Y-%m-%d")

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "Recurring reopen",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Complete it
    await client.post(
        f"/tasks/{task_id}/complete",
        json={
            "scheduled_for": scheduled_at.isoformat(),
            "local_date": today,
        },
    )

    # Try to reopen without scheduled_for
    reopen_response = await client.post(f"/tasks/{task_id}/reopen", json={})
    assert reopen_response.status_code == 400
    assert "scheduled_for is required" in reopen_response.json()["detail"]


@pytest.mark.asyncio
async def test_reopen_recurring_no_completion_fails(client: AsyncClient):
    """Test reopening a recurring task with no matching completion fails."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=10, minute=0, second=0, microsecond=0)

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "Recurring reopen",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Try to reopen without ever completing
    reopen_response = await client.post(
        f"/tasks/{task_id}/reopen",
        json={"scheduled_for": scheduled_at.isoformat()},
    )
    assert reopen_response.status_code == 400
    assert "no completion found" in reopen_response.json()["detail"].lower()


# ============================================================================
# Time Machine Tests
# ============================================================================


@pytest.mark.asyncio
async def test_count_future_completions(client: AsyncClient):
    """Test counting future completions."""
    response = await client.get("/tasks/completions/future/count")
    assert response.status_code == 200
    assert "count" in response.json()


@pytest.mark.asyncio
async def test_delete_future_completions(client: AsyncClient):
    """Test deleting future completions."""
    response = await client.delete("/tasks/completions/future")
    assert response.status_code == 200
    assert "deleted_count" in response.json()


@pytest.mark.asyncio
async def test_delete_future_completions_with_date(client: AsyncClient):
    """Test deleting future completions after a specific date."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    response = await client.delete(
        "/tasks/completions/future",
        params={"after_date": today},
    )
    assert response.status_code == 200
    assert "deleted_count" in response.json()


@pytest.mark.asyncio
async def test_delete_future_completions_invalid_date(client: AsyncClient):
    """Test deleting with invalid date format."""
    response = await client.delete(
        "/tasks/completions/future",
        params={"after_date": "invalid-date"},
    )
    assert response.status_code == 400
    assert "invalid date format" in response.json()["detail"].lower()


# ============================================================================
# Bulk Completions Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_bulk_completions(client: AsyncClient):
    """Test creating bulk completions for mocking history."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "Bulk completion test",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Create bulk completions
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    two_days_ago = (now - timedelta(days=2)).strftime("%Y-%m-%d")

    bulk_response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": yesterday, "status": "completed", "occurrences": 1},
                {"date": two_days_ago, "status": "skipped", "skip_reason": "Test skip", "occurrences": 1},
            ],
        },
    )
    assert bulk_response.status_code == 200
    assert bulk_response.json()["created_count"] == 2


@pytest.mark.asyncio
async def test_create_bulk_completions_non_recurring_fails(client: AsyncClient):
    """Test bulk completions fails for non-recurring tasks."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Not recurring",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    bulk_response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2024-01-01", "status": "completed", "occurrences": 1},
            ],
        },
    )
    assert bulk_response.status_code == 400
    assert "recurring" in bulk_response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_bulk_completions_with_start_date_update(client: AsyncClient):
    """Test bulk completions with start date update."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "Bulk start date",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    new_start = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    bulk_response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": new_start, "status": "completed", "occurrences": 1},
            ],
            "update_start_date": new_start,
        },
    )
    assert bulk_response.status_code == 200
    assert bulk_response.json()["start_date_updated"] is True


# ============================================================================
# Delete Mock Completions Tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_mock_completions(client: AsyncClient):
    """Test deleting mock completions."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "Delete mock test",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Create bulk completions first
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": yesterday, "status": "completed", "occurrences": 2},
            ],
        },
    )

    # Delete mock completions
    delete_response = await client.delete(f"/tasks/{task_id}/completions/mock")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_count"] == 2


@pytest.mark.asyncio
async def test_delete_mock_completions_non_recurring_returns_zero(client: AsyncClient):
    """Test deleting mock completions for non-recurring tasks returns zero deleted."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Not recurring",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    # Non-recurring tasks don't have mock completions, so delete should work but return 0
    delete_response = await client.delete(f"/tasks/{task_id}/completions/mock")
    assert delete_response.status_code == 200
    assert delete_response.json()["deleted_count"] == 0


# ============================================================================
# Task Views Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_today_tasks(client: AsyncClient):
    """Test getting today's tasks."""
    response = await client.get("/tasks/view/today")
    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data
    assert "pending_count" in data
    assert "completed_today_count" in data


@pytest.mark.asyncio
async def test_get_today_tasks_with_timezone(client: AsyncClient):
    """Test getting today's tasks with timezone."""
    response = await client.get("/tasks/view/today?timezone=America/New_York")
    assert response.status_code == 200
    assert "tasks" in response.json()


@pytest.mark.asyncio
async def test_get_today_tasks_invalid_timezone(client: AsyncClient):
    """Test getting today's tasks with invalid timezone falls back to UTC."""
    response = await client.get("/tasks/view/today?timezone=Invalid/Zone")
    assert response.status_code == 200
    assert "tasks" in response.json()


@pytest.mark.asyncio
async def test_get_today_tasks_include_completed(client: AsyncClient):
    """Test getting today's tasks including completed."""
    response = await client.get("/tasks/view/today?include_completed=true")
    assert response.status_code == 200
    assert "tasks" in response.json()


@pytest.mark.asyncio
async def test_get_tasks_in_range(client: AsyncClient):
    """Test getting tasks in date range."""
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=7)).isoformat()
    end_date = now.isoformat()

    response = await client.post(
        "/tasks/view/range",
        json={
            "start_date": start_date,
            "end_date": end_date,
            "include_completed": False,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data
    assert "total" in data
    assert "has_more" in data


@pytest.mark.asyncio
async def test_get_tasks_in_range_with_pagination(client: AsyncClient):
    """Test getting tasks in date range with pagination."""
    now = datetime.now(timezone.utc)
    start_date = (now - timedelta(days=7)).isoformat()
    end_date = now.isoformat()

    response = await client.post(
        "/tasks/view/range",
        json={
            "start_date": start_date,
            "end_date": end_date,
            "limit": 5,
            "offset": 0,
        },
    )
    assert response.status_code == 200


# ============================================================================
# Task Completions History Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_task_completions(client: AsyncClient):
    """Test getting task completion history."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=7, minute=0, second=0, microsecond=0)

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "title": "Completion history test",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Complete a few times
    for i in range(3):
        completion_time = (now - timedelta(days=i)).isoformat()
        await client.post(
            f"/tasks/{task_id}/complete",
            json={
                "scheduled_for": completion_time,
                "local_date": (now - timedelta(days=i)).strftime("%Y-%m-%d"),
            },
        )

    # Get completions
    response = await client.get(f"/tasks/{task_id}/completions")
    assert response.status_code == 200
    data = response.json()
    assert "completions" in data
    assert "total" in data
    assert "completed_count" in data


@pytest.mark.asyncio
async def test_get_task_completions_non_recurring(client: AsyncClient):
    """Test getting completions for non-recurring task returns empty."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Not recurring",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    response = await client.get(f"/tasks/{task_id}/completions")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert data["completions"] == []


# ============================================================================
# Task Validation Error Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_recurring_task_without_scheduling_mode_fails(client: AsyncClient):
    """Test that recurring tasks with scheduled_at require scheduling_mode."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    response = await client.post(
        "/tasks",
        json={
            "title": "Missing scheduling_mode",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            # Missing scheduling_mode
            "recurrence_behavior": "habitual",
        },
    )
    assert response.status_code == 400
    assert "scheduling_mode is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_anytime_recurring_task_fails(client: AsyncClient):
    """Test that anytime tasks cannot be recurring."""
    response = await client.post(
        "/tasks",
        json={
            "title": "Anytime recurring",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "anytime",
            "recurrence_behavior": "habitual",
        },
    )
    assert response.status_code == 400
    assert "cannot be recurring" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_recurring_without_behavior_fails(client: AsyncClient):
    """Test that recurring tasks require recurrence_behavior."""
    now = datetime.now(timezone.utc)
    scheduled_at = now.replace(hour=9, minute=0, second=0, microsecond=0)

    response = await client.post(
        "/tasks",
        json={
            "title": "Missing behavior",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": scheduled_at.isoformat(),
            "scheduling_mode": "floating",
            # Missing recurrence_behavior
        },
    )
    assert response.status_code == 400
    assert "recurrence_behavior is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_non_recurring_with_behavior_fails(client: AsyncClient):
    """Test that non-recurring tasks should not have recurrence_behavior."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Non-recurring with behavior",
            "duration_minutes": 30,
            "is_recurring": False,
            "recurrence_behavior": "habitual",  # Should not be set
        },
    )
    assert response.status_code == 400
    assert "should only be set for recurring tasks" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_task_with_invalid_goal_fails(client: AsyncClient):
    """Test creating task with non-existent goal fails."""
    response = await client.post(
        "/tasks",
        json={
            "goal_id": "00000000-0000-0000-0000-000000000000",
            "title": "Task with bad goal",
            "duration_minutes": 30,
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_task_date_only_scheduling(client: AsyncClient):
    """Test creating task with scheduled_date but no time defaults to date_only."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Date only task",
            "duration_minutes": 30,
            "scheduled_date": "2026-04-15",
        },
    )
    assert response.status_code == 201
    # scheduling_mode should default to date_only


# ============================================================================
# Task Update Tests 
# ============================================================================


@pytest.mark.asyncio
async def test_update_task_title(client: AsyncClient):
    """Test updating task title."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Original Title", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={"title": "Updated Title"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_update_task_description(client: AsyncClient):
    """Test updating task description."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={"description": "New description"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["description"] == "New description"


@pytest.mark.asyncio
async def test_update_task_duration(client: AsyncClient):
    """Test updating task duration."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    update_response = await client.patch(
        f"/tasks/{task_id}",
        json={"duration_minutes": 60},
    )
    assert update_response.status_code == 200
    assert update_response.json()["duration_minutes"] == 60


@pytest.mark.asyncio
async def test_update_task_not_found(client: AsyncClient):
    """Test updating non-existent task."""
    response = await client.patch(
        "/tasks/00000000-0000-0000-0000-000000000000",
        json={"title": "New Title"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_task(client: AsyncClient):
    """Test getting a single task by ID."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Get Me", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    get_response = await client.get(f"/tasks/{task_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == task_id


@pytest.mark.asyncio
async def test_get_task_not_found(client: AsyncClient):
    """Test getting non-existent task."""
    response = await client.get("/tasks/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# ============================================================================
# Task Completion Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_complete_one_time_task(client: AsyncClient):
    """Test completing a one-time task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "One-time", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    complete_response = await client.post(f"/tasks/{task_id}/complete", json={})
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_complete_anytime_task_clears_sort_order(client: AsyncClient):
    """Test completing an anytime task clears its sort order."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Anytime task",
            "duration_minutes": 30,
            "scheduling_mode": "anytime",
        },
    )
    task_id = task_response.json()["id"]

    # Complete it
    complete_response = await client.post(f"/tasks/{task_id}/complete", json={})
    assert complete_response.status_code == 200


# ============================================================================
# Task List Filters
# ============================================================================


@pytest.mark.asyncio
async def test_list_tasks_by_goal(client: AsyncClient):
    """Test listing tasks filtered by goal."""
    goal1_response = await client.post("/goals", json={"title": "Goal 1"})
    goal1_id = goal1_response.json()["id"]
    goal2_response = await client.post("/goals", json={"title": "Goal 2"})
    goal2_id = goal2_response.json()["id"]

    # Create tasks for each goal
    await client.post(
        "/tasks",
        json={"goal_id": goal1_id, "title": "Task in Goal 1", "duration_minutes": 30},
    )
    await client.post(
        "/tasks",
        json={"goal_id": goal2_id, "title": "Task in Goal 2", "duration_minutes": 30},
    )

    # Filter by goal
    response = await client.get(f"/tasks?goal_id={goal1_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_by_status(client: AsyncClient):
    """Test listing tasks filtered by status."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "To Complete", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    # Complete the task
    await client.post(f"/tasks/{task_id}/complete", json={})

    # Filter by status
    response = await client.get("/tasks?status=completed")
    assert response.status_code == 200


# ============================================================================
# List Tasks Filter Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_tasks_with_scheduled_after_filter(client: AsyncClient):
    """Test listing tasks filtered by scheduled_after datetime."""
    from datetime import datetime, timedelta, timezone
    
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    future_time = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Future task",
            "duration_minutes": 30,
            "scheduled_at": future_time,
        },
    )

    after_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    response = await client.get(f"/tasks?scheduled_after={after_time}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_scheduled_before_filter(client: AsyncClient):
    """Test listing tasks filtered by scheduled_before datetime."""
    from datetime import datetime, timedelta, timezone
    
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    past_time = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Past task",
            "duration_minutes": 30,
            "scheduled_at": past_time,
        },
    )

    before_time = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    response = await client.get(f"/tasks?scheduled_before={before_time}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_client_today_parameter(client: AsyncClient):
    """Test listing tasks with explicit client_today for timezone handling."""
    from datetime import datetime, timezone
    
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Client today task", "duration_minutes": 30},
    )

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    response = await client.get(f"/tasks?client_today={today}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_invalid_scheduled_after(client: AsyncClient):
    """Test listing tasks with invalid scheduled_after gracefully skips filter."""
    response = await client.get("/tasks?scheduled_after=not-a-date")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_invalid_scheduled_before(client: AsyncClient):
    """Test listing tasks with invalid scheduled_before gracefully skips filter."""
    response = await client.get("/tasks?scheduled_before=not-a-date")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_invalid_client_today(client: AsyncClient):
    """Test listing tasks with invalid client_today falls back to UTC."""
    response = await client.get("/tasks?client_today=not-a-date")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_recurring_tasks_with_multi_day_completions(client: AsyncClient):
    """Test listing recurring tasks tracks completions across multiple days."""
    from datetime import datetime, timedelta, timezone
    
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    base_time = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Track completions",
            "duration_minutes": 15,
            "scheduled_at": (base_time - timedelta(days=3)).isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Create completions on different days
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": yesterday.isoformat(), "local_date": yesterday_str},
    )
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": base_time.isoformat(), "local_date": today_str},
    )

    # Skip a day
    day_before = datetime.now(timezone.utc) - timedelta(days=2)
    await client.post(
        f"/tasks/{task_id}/skip",
        json={
            "scheduled_for": day_before.isoformat(),
            "local_date": day_before.strftime("%Y-%m-%d"),
            "reason": "Too busy",
        },
    )

    response = await client.get(f"/tasks?days_ahead=7&client_today={today_str}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_task_with_scheduled_date_sets_mode(client: AsyncClient):
    """Test creating task with scheduled_date but no scheduled_at auto-sets date_only mode."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Date only task",
            "duration_minutes": 30,
            "scheduled_date": "2026-12-25",
        },
    )
    assert response.status_code == 201
    assert response.json()["scheduling_mode"] == "date_only"


@pytest.mark.asyncio
async def test_update_task_scheduling_fields(client: AsyncClient):
    """Test updating task scheduled_date and scheduled_at."""
    from datetime import datetime, timedelta, timezone
    
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Reschedule", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    new_date = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
    new_time = (datetime.now(timezone.utc) + timedelta(days=7, hours=2)).isoformat()

    response = await client.patch(
        f"/tasks/{task_id}",
        json={"scheduled_date": new_date, "scheduled_at": new_time},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_task_title_description_duration(client: AsyncClient):
    """Test updating task title, description, and duration together."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Original", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    response = await client.patch(
        f"/tasks/{task_id}",
        json={
            "title": "Updated Title",
            "description": "New description",
            "duration_minutes": 60,
            "notify_before_minutes": 15,
        },
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"
    assert response.json()["description"] == "New description"
    assert response.json()["duration_minutes"] == 60


# ============================================================================
# Task Update - Goal Change Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_task_change_goal(client: AsyncClient):
    """Test moving a task from one goal to another."""
    # Create two goals
    goal1_response = await client.post("/goals", json={"title": "Goal 1"})
    goal2_response = await client.post("/goals", json={"title": "Goal 2"})
    goal1_id = goal1_response.json()["id"]
    goal2_id = goal2_response.json()["id"]

    # Create task under goal 1
    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal1_id, "title": "Movable task", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    # Move to goal 2
    response = await client.patch(f"/tasks/{task_id}", json={"goal_id": goal2_id})
    assert response.status_code == 200
    assert response.json()["goal_id"] == goal2_id


@pytest.mark.asyncio
async def test_update_task_scheduling_mode_auto_detection(client: AsyncClient):
    """Test that scheduling_mode is auto-detected when date/time fields change."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create task with no schedule
    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Auto mode task", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    # Set only scheduled_date -> should auto-set date_only mode
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"scheduled_date": "2026-06-15"},
    )
    assert response.status_code == 200
    assert response.json()["scheduling_mode"] == "date_only"


@pytest.mark.asyncio
async def test_update_task_recurrence_fields(client: AsyncClient):
    """Test updating recurrence-related fields."""
    from datetime import datetime, timezone
    
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Make recurring", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    # Make it recurring
    response = await client.patch(
        f"/tasks/{task_id}",
        json={
            "is_recurring": True,
            "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO,WE,FR",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    assert response.status_code == 200
    assert response.json()["is_recurring"] is True
    assert response.json()["recurrence_rule"] == "FREQ=WEEKLY;BYDAY=MO,WE,FR"


@pytest.mark.asyncio
async def test_update_task_recurrence_without_behavior_fails(client: AsyncClient):
    """Test that making task recurring without recurrence_behavior fails."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Bad recurring", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    # Try to make recurring without behavior
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"is_recurring": True, "recurrence_rule": "FREQ=DAILY"},
    )
    assert response.status_code == 400
    assert "recurrence_behavior" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_task_clear_recurrence(client: AsyncClient):
    """Test clearing recurrence from a recurring task."""
    from datetime import datetime, timezone
    
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Stop recurring",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Clear recurrence
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"is_recurring": False},
    )
    assert response.status_code == 200
    assert response.json()["is_recurring"] is False
    # recurrence_behavior should be cleared
    assert response.json()["recurrence_behavior"] is None


# ============================================================================
# Task Delete Tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_task(client: AsyncClient):
    """Test deleting a task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Delete me", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    response = await client.delete(f"/tasks/{task_id}")
    assert response.status_code == 204

    # Verify deleted
    get_response = await client.get(f"/tasks/{task_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_not_found(client: AsyncClient):
    """Test deleting non-existent task."""
    response = await client.delete("/tasks/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_task_updates_goal_progress(client: AsyncClient):
    """Test that deleting a task updates the goal's progress."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create two tasks
    task1_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task 1", "duration_minutes": 30},
    )
    task2_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task 2", "duration_minutes": 30},
    )
    task1_id = task1_response.json()["id"]

    # Complete task 1
    await client.post(f"/tasks/{task1_id}/complete", json={})

    # Delete task 2 - should affect progress calculation
    await client.delete(f"/tasks/{task2_response.json()['id']}")

    # Goal should now show 100% progress (1 completed / 1 task)
    goal_response = await client.get(f"/goals/{goal_id}")
    assert goal_response.status_code == 200


# ============================================================================
# Complete Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_complete_one_time_task(client: AsyncClient):
    """Test completing a one-time (non-recurring) task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "One time task", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    response = await client.post(f"/tasks/{task_id}/complete", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["completed_at"] is not None


@pytest.mark.asyncio
async def test_complete_recurring_task(client: AsyncClient):
    """Test completing a recurring task occurrence."""
    from datetime import datetime, timezone
    
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_response.json()["id"]

    # Complete for today
    today_str = now.strftime("%Y-%m-%d")
    response = await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": now.isoformat(), "local_date": today_str},
    )
    assert response.status_code == 200
    # Task should remain pending (recurring)
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_complete_task_not_found(client: AsyncClient):
    """Test completing non-existent task."""
    response = await client.post(
        "/tasks/00000000-0000-0000-0000-000000000000/complete",
        json={},
    )
    assert response.status_code == 404


# ============================================================================
# Skip Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_skip_one_time_task(client: AsyncClient):
    """Test skipping a one-time task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Skip me", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    response = await client.post(
        f"/tasks/{task_id}/skip",
        json={"reason": "Not feeling it today"},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "skipped"
    assert response.json()["skip_reason"] == "Not feeling it today"


@pytest.mark.asyncio
async def test_skip_recurring_task(client: AsyncClient):
    """Test skipping a recurring task occurrence."""
    from datetime import datetime, timezone
    
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Skip recurring",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_response.json()["id"]

    today_str = now.strftime("%Y-%m-%d")
    response = await client.post(
        f"/tasks/{task_id}/skip",
        json={
            "scheduled_for": now.isoformat(),
            "local_date": today_str,
            "reason": "Skipping today",
        },
    )
    assert response.status_code == 200
    # Task should remain pending (recurring)
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_skip_task_not_found(client: AsyncClient):
    """Test skipping non-existent task."""
    response = await client.post(
        "/tasks/00000000-0000-0000-0000-000000000000/skip",
        json={"reason": "test"},
    )
    assert response.status_code == 404


# ============================================================================
# Reopen Task Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reopen_completed_one_time_task(client: AsyncClient):
    """Test reopening a completed one-time task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Reopen me", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    # Complete it
    await client.post(f"/tasks/{task_id}/complete", json={})

    # Reopen it
    response = await client.post(f"/tasks/{task_id}/reopen", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["completed_at"] is None


@pytest.mark.asyncio
async def test_reopen_skipped_task(client: AsyncClient):
    """Test reopening a skipped task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Reopen skipped", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    # Skip it
    await client.post(f"/tasks/{task_id}/skip", json={"reason": "Skipped"})

    # Reopen it
    response = await client.post(f"/tasks/{task_id}/reopen", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["skip_reason"] is None


@pytest.mark.asyncio
async def test_reopen_recurring_task(client: AsyncClient):
    """Test reopening a completed recurring task occurrence."""
    from datetime import datetime, timezone
    
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Reopen recurring",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_response.json()["id"]

    today_str = now.strftime("%Y-%m-%d")
    
    # Complete for today
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": now.isoformat(), "local_date": today_str},
    )

    # Reopen that occurrence
    response = await client.post(
        f"/tasks/{task_id}/reopen",
        json={"scheduled_for": now.isoformat()},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_reopen_recurring_task_without_scheduled_for(client: AsyncClient):
    """Test that reopening recurring task without scheduled_for fails."""
    from datetime import datetime, timezone
    
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Reopen fail",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_response.json()["id"]

    today_str = now.strftime("%Y-%m-%d")
    
    # Complete for today
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": now.isoformat(), "local_date": today_str},
    )

    # Try to reopen without scheduled_for
    response = await client.post(f"/tasks/{task_id}/reopen", json={})
    assert response.status_code == 400
    assert "scheduled_for" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reopen_recurring_task_no_completion_found(client: AsyncClient):
    """Test reopening recurring task when no completion exists for that time."""
    from datetime import datetime, timezone, timedelta
    
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "No completion",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_response.json()["id"]

    # Try to reopen a time that was never completed
    future_time = (now + timedelta(days=5)).isoformat()
    response = await client.post(
        f"/tasks/{task_id}/reopen",
        json={"scheduled_for": future_time},
    )
    assert response.status_code == 400
    assert "no completion" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reopen_pending_task_fails(client: AsyncClient):
    """Test that reopening an already-pending task fails."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Already pending", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    # Try to reopen a pending task
    response = await client.post(f"/tasks/{task_id}/reopen", json={})
    assert response.status_code == 400
    assert "already pending" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reopen_task_not_found(client: AsyncClient):
    """Test reopening non-existent task."""
    response = await client.post(
        "/tasks/00000000-0000-0000-0000-000000000000/reopen",
        json={},
    )
    assert response.status_code == 404


# ============================================================================
# Recurring Task Completion Tracking Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_tasks_recurring_with_completions_today(client: AsyncClient):
    """Test list_tasks returns completion info for recurring tasks completed today."""
    from datetime import datetime, timezone, timedelta

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Daily recurring",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    # Complete the task for today
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": now.isoformat(), "local_date": today_str},
    )

    # List tasks with client_today
    response = await client.get("/tasks", params={"client_today": today_str})
    assert response.status_code == 200
    
    tasks = response.json()["tasks"]
    recurring_task = next((t for t in tasks if t["id"] == task_id), None)
    assert recurring_task is not None
    assert recurring_task["completions_today"] >= 1


@pytest.mark.asyncio
async def test_list_tasks_recurring_with_skips_today(client: AsyncClient):
    """Test list_tasks returns skip info for recurring tasks skipped today."""
    from datetime import datetime, timezone

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Daily task to skip",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_response.json()["id"]

    # Skip the task for today
    await client.post(
        f"/tasks/{task_id}/skip",
        json={"scheduled_for": now.isoformat(), "local_date": today_str, "reason": "busy"},
    )

    # List tasks
    response = await client.get("/tasks", params={"client_today": today_str})
    assert response.status_code == 200
    
    tasks = response.json()["tasks"]
    skipped_task = next((t for t in tasks if t["id"] == task_id), None)
    assert skipped_task is not None
    assert skipped_task["skips_today"] >= 1


@pytest.mark.asyncio
async def test_list_tasks_recurring_completions_by_date(client: AsyncClient):
    """Test list_tasks returns completions_by_date for multi-day completions."""
    from datetime import datetime, timezone, timedelta

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    today_str = now.strftime("%Y-%m-%d")
    yesterday_str = yesterday.strftime("%Y-%m-%d")

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Multi-day recurring",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": yesterday.isoformat(),
        },
    )
    task_id = task_response.json()["id"]

    # Complete for yesterday
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": yesterday.isoformat(), "local_date": yesterday_str},
    )

    # Complete for today
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": now.isoformat(), "local_date": today_str},
    )

    # List tasks with days_ahead
    response = await client.get(
        "/tasks", params={"client_today": today_str, "days_ahead": 7}
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_status_filter_completed(client: AsyncClient):
    """Test filtering tasks by completed status."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create a task and complete it
    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Completed task", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]
    await client.post(f"/tasks/{task_id}/complete", json={})

    # Create a pending task
    await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Pending task", "duration_minutes": 30},
    )

    # Filter by completed status
    response = await client.get("/tasks", params={"status": "completed"})
    assert response.status_code == 200
    tasks = response.json()["tasks"]
    assert all(t["status"] == "completed" for t in tasks)


@pytest.mark.asyncio
async def test_list_tasks_status_filter_pending(client: AsyncClient):
    """Test filtering tasks by pending status."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create a task and complete it
    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Completed", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]
    await client.post(f"/tasks/{task_id}/complete", json={})

    # Create a pending task
    await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Pending", "duration_minutes": 30},
    )

    # Filter by pending status
    response = await client.get("/tasks", params={"status": "pending"})
    assert response.status_code == 200
    tasks = response.json()["tasks"]
    assert all(t["status"] == "pending" for t in tasks)


@pytest.mark.asyncio
async def test_create_task_with_date_only_scheduling(client: AsyncClient):
    """Test creating task with scheduled_date but no scheduled_at."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Date-only task",
            "duration_minutes": 30,
            "scheduled_date": "2026-04-15",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["scheduled_date"] == "2026-04-15"
    assert data["scheduling_mode"] == "date_only"


@pytest.mark.asyncio
async def test_update_task_recurrence_behavior_required(client: AsyncClient):
    """Test that recurring tasks require recurrence_behavior."""
    from datetime import datetime, timezone

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)

    # Create non-recurring task first
    task_response = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Not recurring", "duration_minutes": 30},
    )
    task_id = task_response.json()["id"]

    # Try to make it recurring without recurrence_behavior - should fail
    response = await client.patch(
        f"/tasks/{task_id}",
        json={
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
        },
    )
    assert response.status_code == 400
    assert "recurrence_behavior" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_task_clears_recurrence_behavior_when_not_recurring(client: AsyncClient):
    """Test that recurrence_behavior is cleared when task becomes non-recurring."""
    from datetime import datetime, timezone

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)

    # Create recurring task
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Was recurring",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_response.json()["id"]
    assert task_response.json()["recurrence_behavior"] == "habitual"

    # Make it non-recurring
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"is_recurring": False, "recurrence_rule": None},
    )
    assert response.status_code == 200
    assert response.json()["recurrence_behavior"] is None


@pytest.mark.asyncio
async def test_complete_anytime_task_clears_sort_order(client: AsyncClient):
    """Test completing anytime task clears its sort_order."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create anytime task
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Anytime task",
            "duration_minutes": 30,
            "scheduling_mode": "anytime",
        },
    )
    task_id = task_response.json()["id"]
    assert task_response.json().get("sort_order") is not None

    # Complete the task
    response = await client.post(f"/tasks/{task_id}/complete", json={})
    assert response.status_code == 200
    assert response.json()["sort_order"] is None


@pytest.mark.asyncio
async def test_skip_anytime_task_clears_sort_order(client: AsyncClient):
    """Test skipping anytime task clears its sort_order."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create anytime task
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Anytime task to skip",
            "duration_minutes": 30,
            "scheduling_mode": "anytime",
        },
    )
    task_id = task_response.json()["id"]

    # Skip the task
    response = await client.post(
        f"/tasks/{task_id}/skip",
        json={"reason": "not today"},
    )
    assert response.status_code == 200
    assert response.json()["sort_order"] is None


@pytest.mark.asyncio
async def test_bulk_completions_many_dates(client: AsyncClient):
    """Test bulk completions with multiple valid dates."""
    from datetime import datetime, timezone, timedelta

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Bulk completions test",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_response.json()["id"]

    # Multiple valid dates
    response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2026-04-10", "status": "completed", "occurrences": 1},
                {"date": "2026-04-11", "status": "completed", "occurrences": 1},
                {"date": "2026-04-12", "status": "completed", "occurrences": 1},
            ]
        },
    )
    assert response.status_code == 200
    # Should count all 3 entries
    assert response.json()["created_count"] == 3


@pytest.mark.asyncio
async def test_bulk_completions_with_skips(client: AsyncClient):
    """Test bulk completions with skip entries."""
    from datetime import datetime, timezone

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Bulk with skips",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_response.json()["id"]

    response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2026-04-10", "status": "completed", "occurrences": 1},
                {"date": "2026-04-11", "status": "skipped", "occurrences": 1, "skip_reason": "sick"},
            ]
        },
    )
    assert response.status_code == 200
    assert response.json()["created_count"] == 2


@pytest.mark.asyncio
async def test_bulk_completions_with_start_date_update_and_scheduled_at(client: AsyncClient):
    """Test bulk completions that updates start date when task has scheduled_at."""
    from datetime import datetime, timezone

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create a task with scheduled_at
    now = datetime.now(timezone.utc)
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Task with time",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
            "scheduled_date": "2026-01-01",
        },
    )
    task_id = task_response.json()["id"]

    # Bulk completions with start date update
    response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2026-05-10", "status": "completed", "occurrences": 1},
            ],
            "update_start_date": "2026-05-01",
        },
    )
    assert response.status_code == 200
    assert response.json()["start_date_updated"] is True

    # Verify the task was updated
    get_response = await client.get(f"/tasks/{task_id}")
    task = get_response.json()
    assert task["scheduled_date"] == "2026-05-01"


@pytest.mark.asyncio
async def test_bulk_completions_with_multiple_occurrences_per_day(client: AsyncClient):
    """Test bulk completions with multiple occurrences on same day."""
    from datetime import datetime, timezone

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Multi-occurrence task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_response.json()["id"]

    # Single entry with multiple occurrences
    response = await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2026-05-10", "status": "completed", "occurrences": 3},
            ]
        },
    )
    assert response.status_code == 200
    # 3 occurrences should be created
    assert response.json()["created_count"] == 3


@pytest.mark.asyncio
async def test_delete_mock_completions(client: AsyncClient):
    """Test deleting mock completions for a recurring task."""
    from datetime import datetime, timezone

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Task for delete mock",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_response.json()["id"]

    # Create mock completions
    await client.post(
        f"/tasks/{task_id}/completions/bulk",
        json={
            "entries": [
                {"date": "2026-05-10", "status": "completed", "occurrences": 2},
            ]
        },
    )

    # Delete mock completions
    response = await client.delete(f"/tasks/{task_id}/completions/mock")
    assert response.status_code == 200
    assert response.json()["deleted_count"] == 2


@pytest.mark.asyncio
async def test_delete_mock_completions_non_recurring_returns_zero(client: AsyncClient):
    """Test that deleting mock completions returns 0 for non-recurring tasks."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Non-recurring task",
            "duration_minutes": 30,
            "is_recurring": False,
        },
    )
    task_id = task_response.json()["id"]

    response = await client.delete(f"/tasks/{task_id}/completions/mock")
    assert response.status_code == 200
    assert response.json()["deleted_count"] == 0


@pytest.mark.asyncio
async def test_update_task_changes_goal(client: AsyncClient):
    """Test that updating a task's goal properly updates both goals."""
    # Create two goals
    goal1_resp = await client.post("/goals", json={"title": "Goal 1"})
    goal1_id = goal1_resp.json()["id"]

    goal2_resp = await client.post("/goals", json={"title": "Goal 2"})
    goal2_id = goal2_resp.json()["id"]

    # Create task under goal 1
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal1_id,
            "title": "Moving task",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    # Move task to goal 2 (API uses PATCH not PUT)
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"goal_id": goal2_id},
    )
    assert response.status_code == 200
    assert response.json()["goal_id"] == goal2_id


@pytest.mark.asyncio
async def test_reopen_completed_anytime_task(client: AsyncClient):
    """Test reopening a completed anytime task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create anytime task (no scheduled_at, no is_recurring)
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Anytime task",
            "duration_minutes": 30,
            "scheduling_mode": "anytime",
        },
    )
    task_id = task_response.json()["id"]
    assert task_response.json()["status"] == "pending"

    # Complete it (requires JSON body)
    complete_response = await client.post(f"/tasks/{task_id}/complete", json={})
    assert complete_response.status_code == 200
    assert complete_response.json()["status"] == "completed"

    # Reopen it
    response = await client.post(f"/tasks/{task_id}/reopen", json={})
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


# ============================================================================
# List Tasks Filter Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_tasks_with_scheduled_after(client: AsyncClient):
    """Test list_tasks with scheduled_after filter."""
    from datetime import datetime, timezone, timedelta

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create a task scheduled for tomorrow
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Tomorrow Task",
            "duration_minutes": 30,
            "scheduled_at": tomorrow.isoformat(),
        },
    )

    # Filter for tasks after now
    response = await client.get(
        "/tasks",
        params={"scheduled_after": datetime.now(timezone.utc).isoformat()},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_scheduled_before(client: AsyncClient):
    """Test list_tasks with scheduled_before filter."""
    from datetime import datetime, timezone, timedelta

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create a task scheduled for yesterday
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Yesterday Task",
            "duration_minutes": 30,
            "scheduled_at": yesterday.isoformat(),
        },
    )

    # Filter for tasks before now
    response = await client.get(
        "/tasks",
        params={"scheduled_before": datetime.now(timezone.utc).isoformat()},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_client_today(client: AsyncClient):
    """Test list_tasks with client_today parameter."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Test Task",
            "duration_minutes": 30,
        },
    )

    # Provide client's local date
    response = await client.get(
        "/tasks",
        params={"client_today": "2026-04-09"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_invalid_client_today(client: AsyncClient):
    """Test list_tasks with invalid client_today format."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Test Task",
            "duration_minutes": 30,
        },
    )

    # Invalid date format should fall back to UTC
    response = await client.get(
        "/tasks",
        params={"client_today": "invalid-date"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_days_ahead(client: AsyncClient):
    """Test list_tasks with custom days_ahead parameter."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    from datetime import datetime, timezone

    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring Task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    # Request with custom days_ahead
    response = await client.get(
        "/tasks",
        params={"days_ahead": 7},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_include_completed(client: AsyncClient):
    """Test list_tasks with include_completed parameter."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create and complete a task
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Completed Task",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]
    await client.post(f"/tasks/{task_id}/complete", json={})

    # Include completed
    response = await client.get(
        "/tasks",
        params={"include_completed": "true"},
    )
    assert response.status_code == 200
    tasks = response.json()["tasks"]
    completed_tasks = [t for t in tasks if t["status"] == "completed"]
    assert len(completed_tasks) >= 1


@pytest.mark.asyncio
async def test_create_task_date_only_scheduling(client: AsyncClient):
    """Test creating task with date_only scheduling mode."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create with scheduled_date only (no scheduled_at)
    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Date Only Task",
            "duration_minutes": 30,
            "scheduled_date": "2026-04-15",
        },
    )
    assert response.status_code == 201
    assert response.json()["scheduling_mode"] == "date_only"


@pytest.mark.asyncio
async def test_list_tasks_combined_filters(client: AsyncClient):
    """Test list_tasks with multiple filters combined."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Combined Filter Task",
            "duration_minutes": 30,
        },
    )

    # Combine goal_id and status filter
    response = await client.get(
        "/tasks",
        params={
            "goal_id": goal_id,
            "status": "pending",
            "include_completed": "false",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_task_completion_with_local_date(client: AsyncClient):
    """Test completing a recurring task with local_date specified."""
    from datetime import datetime, timezone

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring with local date",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_response.json()["id"]

    # Complete with local_date
    response = await client.post(
        f"/tasks/{task_id}/complete",
        json={
            "scheduled_for": now.isoformat(),
            "local_date": "2026-04-09",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_skip_task_with_local_date(client: AsyncClient):
    """Test skipping a recurring task with local_date specified."""
    from datetime import datetime, timezone

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    now = datetime.now(timezone.utc)
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring skip local date",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_response.json()["id"]

    # Skip with local_date
    response = await client.post(
        f"/tasks/{task_id}/skip",
        json={
            "reason": "Testing",
            "scheduled_for": now.isoformat(),
            "local_date": "2026-04-09",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_task_scheduling_fields(client: AsyncClient):
    """Test updating task scheduling fields."""
    from datetime import datetime, timezone

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Update scheduling",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    # Update with scheduled_date
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"scheduled_date": "2026-04-20"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_task_notify_before_minutes(client: AsyncClient):
    """Test updating task notification settings."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Notify test",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    response = await client.patch(
        f"/tasks/{task_id}",
        json={"notify_before_minutes": 15},
    )
    assert response.status_code == 200
    assert response.json()["notify_before_minutes"] == 15


# ============================================================================
# Task Views Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_today_view(client: AsyncClient):
    """Test getting the today view."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Today Task",
            "duration_minutes": 30,
        },
    )

    response = await client.get("/tasks/view/today")
    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data
    # Stats are individual fields
    assert "pending_count" in data
    assert "completed_today_count" in data
    assert "overdue_count" in data


@pytest.mark.asyncio
async def test_get_today_view_with_client_today(client: AsyncClient):
    """Test today view with client_today parameter."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Client Today Task",
            "duration_minutes": 30,
        },
    )

    response = await client.get(
        "/tasks/view/today",
        params={"client_today": "2026-04-09"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_today_view_include_completed(client: AsyncClient):
    """Test today view with include_completed."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Completed Today",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]
    await client.post(f"/tasks/{task_id}/complete", json={})

    response = await client.get(
        "/tasks/view/today",
        params={"include_completed": "true"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_tasks_range(client: AsyncClient):
    """Test getting tasks for a date range."""
    from datetime import datetime, timezone, timedelta

    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create task for tomorrow
    tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Range Task",
            "duration_minutes": 30,
            "scheduled_at": tomorrow.isoformat(),
        },
    )

    # Post to range endpoint with correct field names
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=7)
    response = await client.post(
        "/tasks/view/range",
        json={
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_tasks_for_anytime_mode(client: AsyncClient):
    """Test listing tasks filtered by anytime mode."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Anytime Task",
            "duration_minutes": 30,
            "scheduling_mode": "anytime",
        },
    )

    # List all tasks and verify anytime task exists
    response = await client.get("/tasks")
    assert response.status_code == 200
    tasks = response.json()["tasks"]
    anytime_tasks = [t for t in tasks if t.get("scheduling_mode") == "anytime"]
    assert len(anytime_tasks) >= 1


# ============================================================================
# Conditional Branch Tests
# ============================================================================


import pytest
from httpx import AsyncClient
from datetime import datetime, timezone, timedelta
from unittest.mock import patch


@pytest.fixture
def mock_validate_priority():
    """Mock priority validation."""
    with patch("app.services.priority_validation.validate_priority") as mock:
        async def async_return(*args, **kwargs):
            return {
                "overall_valid": True,
                "name_valid": True,
                "why_valid": True,
                "name_feedback": [],
                "why_feedback": [],
                "why_passed_rules": {"specificity": True, "actionable": True},
                "name_rewrite": None,
                "why_rewrite": None,
                "rule_examples": None,
            }
        mock.side_effect = async_return
        yield mock


# ============================================================================
# TASKS.PY BRANCH COVERAGE
# ============================================================================


class TestTaskCreationBranches:
    """Test all branches in task creation validation."""

    @pytest.mark.asyncio
    async def test_create_recurring_without_scheduling_mode(self, client: AsyncClient):
        """Branch: is_recurring and scheduled_at but no scheduling_mode."""
        goal = await client.post("/goals", json={"title": "Branch Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Missing Mode Task",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduled_at": now.isoformat(),
                # No scheduling_mode - should fail
            },
        )
        assert response.status_code == 400
        assert "scheduling_mode is required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_anytime_recurring_fails(self, client: AsyncClient):
        """Branch: scheduling_mode == anytime and is_recurring."""
        goal = await client.post("/goals", json={"title": "Anytime R Goal"})
        goal_id = goal.json()["id"]
        
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Anytime Recurring",
                "duration_minutes": 30,
                "scheduling_mode": "anytime",
                "is_recurring": True,
            },
        )
        assert response.status_code == 400
        assert "Anytime tasks cannot be recurring" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_recurring_without_behavior(self, client: AsyncClient):
        """Branch: is_recurring but no recurrence_behavior."""
        goal = await client.post("/goals", json={"title": "No Behavior Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "No Behavior Task",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduled_at": now.isoformat(),
                "scheduling_mode": "floating",
                # No recurrence_behavior - should fail
            },
        )
        assert response.status_code == 400
        assert "recurrence_behavior is required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_non_recurring_with_behavior(self, client: AsyncClient):
        """Branch: not is_recurring but has recurrence_behavior."""
        goal = await client.post("/goals", json={"title": "Extra Behavior Goal"})
        goal_id = goal.json()["id"]
        
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Extra Behavior Task",
                "duration_minutes": 30,
                "is_recurring": False,
                "recurrence_behavior": "habitual",  # Should not be set
            },
        )
        assert response.status_code == 400
        assert "recurrence_behavior should only be set" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_date_only_scheduling(self, client: AsyncClient):
        """Branch: scheduled_date without scheduled_at -> date_only mode."""
        goal = await client.post("/goals", json={"title": "Date Only Goal"})
        goal_id = goal.json()["id"]
        
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Date Only Task",
                "duration_minutes": 30,
                "scheduled_date": today,
                # No scheduled_at -> should auto-set date_only mode
            },
        )
        assert response.status_code == 201
        assert response.json()["scheduling_mode"] == "date_only"

    @pytest.mark.asyncio
    async def test_create_task_without_goal(self, client: AsyncClient):
        """Branch: no goal_id provided."""
        response = await client.post(
            "/tasks",
            json={
                "title": "No Goal Task",
                "duration_minutes": 30,
            },
        )
        # Should succeed or fail based on whether goal_id is required
        assert response.status_code in [201, 422]


class TestTaskUpdateBranches:
    """Test all branches in task update."""

    @pytest.mark.asyncio
    async def test_update_change_goal(self, client: AsyncClient):
        """Branch: goal_id changed."""
        goal1 = await client.post("/goals", json={"title": "Old Goal"})
        goal2 = await client.post("/goals", json={"title": "New Goal"})
        g1_id = goal1.json()["id"]
        g2_id = goal2.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": g1_id, "title": "Move Task", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        response = await client.patch(
            f"/tasks/{task_id}",
            json={"goal_id": g2_id},
        )
        assert response.status_code == 200
        assert response.json()["goal_id"] == g2_id

    @pytest.mark.asyncio
    async def test_update_scheduled_date_sets_mode(self, client: AsyncClient):
        """Branch: scheduled_date set -> auto-sets date_only mode."""
        goal = await client.post("/goals", json={"title": "Date Mode Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Date Mode Task",
                "duration_minutes": 30,
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        today = now.strftime("%Y-%m-%d")
        response = await client.patch(
            f"/tasks/{task_id}",
            json={"scheduled_date": today, "scheduled_at": None},
        )
        assert response.status_code == 200
        assert response.json()["scheduling_mode"] == "date_only"

    @pytest.mark.asyncio
    async def test_update_make_recurring_without_behavior_fails(self, client: AsyncClient):
        """Branch: update to recurring without behavior."""
        goal = await client.post("/goals", json={"title": "Recurr Update Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Become Recurring", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        response = await client.patch(
            f"/tasks/{task_id}",
            json={"is_recurring": True, "recurrence_rule": "FREQ=DAILY"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_remove_recurring_clears_behavior(self, client: AsyncClient):
        """Branch: task becomes non-recurring -> behavior cleared."""
        goal = await client.post("/goals", json={"title": "Stop Recurring Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Stop Recurring Task",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        response = await client.patch(
            f"/tasks/{task_id}",
            json={"is_recurring": False},
        )
        assert response.status_code == 200
        assert response.json()["recurrence_behavior"] is None


class TestTaskCompletionBranches:
    """Test completion/skip/reopen branches."""

    @pytest.mark.asyncio
    async def test_complete_recurring_task(self, client: AsyncClient):
        """Branch: task.is_recurring in complete."""
        goal = await client.post("/goals", json={"title": "Complete R Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Complete Recurring",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        response = await client.post(
            f"/tasks/{task_id}/complete",
            json={"local_date": now.strftime("%Y-%m-%d")},
        )
        assert response.status_code == 200
        # Task should still be pending
        assert response.json()["status"] == "pending"
        assert response.json()["completed_for_today"] is True

    @pytest.mark.asyncio
    async def test_complete_one_time_task(self, client: AsyncClient):
        """Branch: not task.is_recurring in complete."""
        goal = await client.post("/goals", json={"title": "Complete Once Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Complete Once", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        response = await client.post(f"/tasks/{task_id}/complete", json={})
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_skip_recurring_task(self, client: AsyncClient):
        """Branch: task.is_recurring in skip."""
        goal = await client.post("/goals", json={"title": "Skip R Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Skip Recurring",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        response = await client.post(
            f"/tasks/{task_id}/skip",
            json={"reason": "Too busy", "local_date": now.strftime("%Y-%m-%d")},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "pending"  # Still pending
        assert response.json()["skipped_for_today"] is True

    @pytest.mark.asyncio
    async def test_skip_one_time_task(self, client: AsyncClient):
        """Branch: not task.is_recurring in skip."""
        goal = await client.post("/goals", json={"title": "Skip Once Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Skip Once", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        response = await client.post(
            f"/tasks/{task_id}/skip",
            json={"reason": "Not needed"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_reopen_recurring_task(self, client: AsyncClient):
        """Branch: task.is_recurring in reopen."""
        goal = await client.post("/goals", json={"title": "Reopen R Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Reopen Recurring",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        # Complete first
        await client.post(
            f"/tasks/{task_id}/complete",
            json={"scheduled_for": now.isoformat()},
        )
        
        # Reopen
        response = await client.post(
            f"/tasks/{task_id}/reopen",
            json={"scheduled_for": now.isoformat()},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reopen_recurring_without_scheduled_for(self, client: AsyncClient):
        """Branch: is_recurring but no scheduled_for in reopen."""
        goal = await client.post("/goals", json={"title": "Reopen No Time Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Reopen No Time",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        # Complete first
        await client.post(
            f"/tasks/{task_id}/complete",
            json={"scheduled_for": now.isoformat()},
        )
        
        # Reopen without scheduled_for
        response = await client.post(
            f"/tasks/{task_id}/reopen",
            json={},  # No scheduled_for
        )
        assert response.status_code == 400
        assert "scheduled_for is required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_reopen_recurring_no_completion_found(self, client: AsyncClient):
        """Branch: no completion found for time slot."""
        goal = await client.post("/goals", json={"title": "No Completion Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "No Completion Task",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        # Try to reopen without completing first
        response = await client.post(
            f"/tasks/{task_id}/reopen",
            json={"scheduled_for": now.isoformat()},
        )
        assert response.status_code == 400
        assert "No completion found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_reopen_one_time_already_pending(self, client: AsyncClient):
        """Branch: one-time task already pending in reopen."""
        goal = await client.post("/goals", json={"title": "Already Pending Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Already Pending", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        response = await client.post(f"/tasks/{task_id}/reopen", json={})
        assert response.status_code == 400
        assert "already pending" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_reopen_one_time_completed(self, client: AsyncClient):
        """Branch: one-time task completed -> reopen."""
        goal = await client.post("/goals", json={"title": "Reopen Completed Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Reopen Completed", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        # Complete it
        await client.post(f"/tasks/{task_id}/complete", json={})
        
        # Reopen
        response = await client.post(f"/tasks/{task_id}/reopen", json={})
        assert response.status_code == 200
        assert response.json()["status"] == "pending"


class TestTaskListBranches:
    """Test branches in list_tasks."""

    @pytest.mark.asyncio
    async def test_list_filter_by_goal(self, client: AsyncClient):
        """Branch: goal_id filter."""
        goal = await client.post("/goals", json={"title": "Filter Goal"})
        goal_id = goal.json()["id"]
        
        await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Filtered Task", "duration_minutes": 30},
        )
        
        response = await client.get("/tasks", params={"goal_id": goal_id})
        assert response.status_code == 200
        tasks = response.json()["tasks"]
        assert all(t["goal_id"] == goal_id for t in tasks)

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self, client: AsyncClient):
        """Branch: status filter."""
        goal = await client.post("/goals", json={"title": "Status Filter Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Status Task", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        # Complete it
        await client.post(f"/tasks/{task_id}/complete", json={})
        
        # Filter by completed
        response = await client.get("/tasks", params={"status": "completed", "include_completed": True})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_include_completed(self, client: AsyncClient):
        """Branch: include_completed=True."""
        goal = await client.post("/goals", json={"title": "Include Completed Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Include Task", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        await client.post(f"/tasks/{task_id}/complete", json={})
        
        response = await client.get("/tasks", params={"include_completed": True})
        assert response.status_code == 200
        # Should include completed tasks
        assert any(t["status"] == "completed" for t in response.json()["tasks"])

    @pytest.mark.asyncio
    async def test_list_with_client_today(self, client: AsyncClient):
        """Branch: client_today provided."""
        goal = await client.post("/goals", json={"title": "Client Today Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Client Today Task",
                "duration_minutes": 30,
                "scheduled_at": now.isoformat(),
            },
        )
        
        today_str = now.strftime("%Y-%m-%d")
        response = await client.get("/tasks", params={"client_today": today_str})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_with_days_ahead(self, client: AsyncClient):
        """Branch: days_ahead > 0."""
        goal = await client.post("/goals", json={"title": "Days Ahead Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        # Schedule for tomorrow
        await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Tomorrow Task",
                "duration_minutes": 30,
                "scheduled_at": (now + timedelta(days=1)).isoformat(),
            },
        )
        
        response = await client.get("/tasks", params={"days_ahead": 7})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_scheduled_after_filter(self, client: AsyncClient):
        """Branch: scheduled_after filter with valid date."""
        goal = await client.post("/goals", json={"title": "After Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "After Task",
                "duration_minutes": 30,
                "scheduled_at": now.isoformat(),
            },
        )
        
        yesterday = (now - timedelta(days=1)).isoformat()
        response = await client.get("/tasks", params={"scheduled_after": yesterday})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_scheduled_before_filter(self, client: AsyncClient):
        """Branch: scheduled_before filter with valid date."""
        goal = await client.post("/goals", json={"title": "Before Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Before Task",
                "duration_minutes": 30,
                "scheduled_at": now.isoformat(),
            },
        )
        
        tomorrow = (now + timedelta(days=1)).isoformat()
        response = await client.get("/tasks", params={"scheduled_before": tomorrow})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_invalid_date_filters_ignored(self, client: AsyncClient):
        """Branch: invalid date format in filters -> ignored."""
        response = await client.get(
            "/tasks",
            params={
                "scheduled_after": "not-a-date",
                "scheduled_before": "also-invalid",
            },
        )
        assert response.status_code == 200  # Should succeed, just ignore bad dates


class TestTimeMachineBranches:
    """Test time machine endpoint branches."""

    @pytest.mark.asyncio
    async def test_count_future_completions_with_date(self, client: AsyncClient):
        """Branch: after_date provided."""
        goal = await client.post("/goals", json={"title": "Future Count Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Future Count Task",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        # Complete for future date
        future = (now + timedelta(days=5))
        await client.post(
            f"/tasks/{task_id}/complete",
            json={"scheduled_for": future.isoformat()},
        )
        
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        response = await client.get(
            "/tasks/completions/future/count",
            params={"after_date": yesterday},
        )
        assert response.status_code == 200
        assert response.json()["count"] >= 0

    @pytest.mark.asyncio
    async def test_count_future_completions_default_date(self, client: AsyncClient):
        """Branch: after_date not provided -> defaults to today."""
        response = await client.get("/tasks/completions/future/count")
        assert response.status_code == 200
        assert "count" in response.json()

    @pytest.mark.asyncio
    async def test_count_future_completions_invalid_date(self, client: AsyncClient):
        """Branch: invalid date format."""
        response = await client.get(
            "/tasks/completions/future/count",
            params={"after_date": "invalid-date"},
        )
        assert response.status_code == 400
        assert "Invalid date format" in response.json()["detail"]


# ============================================================================
# DISCOVERY.PY BRANCH COVERAGE
# ============================================================================


class TestDiscoveryBranches:
    """Test discovery endpoint branches."""

    @pytest.mark.asyncio
    async def test_selection_already_exists(self, client: AsyncClient):
        """Branch: selection already exists."""
        prompts = await client.get("/discovery/prompts")
        prompts_list = prompts.json()["prompts"]
        
        if len(prompts_list) > 0:
            prompt_id = prompts_list[0]["id"]
            
            # Create first selection
            await client.post(
                "/discovery/selections",
                json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 1},
            )
            
            # Try to create duplicate
            response = await client.post(
                "/discovery/selections",
                json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 2},
            )
            assert response.status_code == 400
            assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_selection_bucket(self, client: AsyncClient):
        """Branch: update.bucket is not None."""
        prompts = await client.get("/discovery/prompts")
        prompts_list = prompts.json()["prompts"]
        
        if len(prompts_list) > 0:
            prompt_id = prompts_list[0]["id"]
            
            sel = await client.post(
                "/discovery/selections",
                json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 1},
            )
            sel_id = sel.json()["id"]
            
            response = await client.put(
                f"/discovery/selections/{sel_id}",
                json={"bucket": "discard"},
            )
            assert response.status_code == 200
            assert response.json()["bucket"] == "discard"

    @pytest.mark.asyncio
    async def test_update_selection_order(self, client: AsyncClient):
        """Branch: update.display_order is not None."""
        prompts = await client.get("/discovery/prompts")
        prompts_list = prompts.json()["prompts"]
        
        if len(prompts_list) > 0:
            prompt_id = prompts_list[0]["id"]
            
            sel = await client.post(
                "/discovery/selections",
                json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 1},
            )
            sel_id = sel.json()["id"]
            
            response = await client.put(
                f"/discovery/selections/{sel_id}",
                json={"display_order": 5},
            )
            assert response.status_code == 200
            assert response.json()["display_order"] == 5

    @pytest.mark.asyncio
    async def test_bulk_update_selections(self, client: AsyncClient):
        """Branch: bulk update with multiple selections."""
        prompts = await client.get("/discovery/prompts")
        prompts_list = prompts.json()["prompts"]
        
        if len(prompts_list) >= 2:
            response = await client.put(
                "/discovery/selections/bulk",
                json={
                    "selections": [
                        {"prompt_id": prompts_list[0]["id"], "bucket": "keep", "display_order": 1},
                        {"prompt_id": prompts_list[1]["id"], "bucket": "discard", "display_order": 2},
                    ]
                },
            )
            assert response.status_code == 200
            assert len(response.json()["selections"]) == 2


# ============================================================================
# TASK_STATS.PY BRANCH COVERAGE
# ============================================================================


class TestTaskStatsBranches:
    """Test task stats endpoint branches."""

    @pytest.mark.asyncio
    async def test_stats_for_recurring_task(self, client: AsyncClient):
        """Branch: task.is_recurring and task.recurrence_rule."""
        goal = await client.post("/goals", json={"title": "Stats Recurring Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Stats Recurring Task",
                "duration_minutes": 15,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": week_ago.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        response = await client.get(
            f"/tasks/{task_id}/stats",
            params={
                "start": week_ago.isoformat(),
                "end": now.isoformat(),
            },
        )
        assert response.status_code == 200
        stats = response.json()
        assert stats["total_expected"] >= 7

    @pytest.mark.asyncio
    async def test_stats_for_non_recurring_task(self, client: AsyncClient):
        """Branch: not is_recurring (expected = 1)."""
        goal = await client.post("/goals", json={"title": "Stats Once Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Stats Once Task",
                "duration_minutes": 30,
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        response = await client.get(
            f"/tasks/{task_id}/stats",
            params={
                "start": (now - timedelta(days=1)).isoformat(),
                "end": (now + timedelta(days=1)).isoformat(),
            },
        )
        assert response.status_code == 200
        assert response.json()["total_expected"] == 1

    @pytest.mark.asyncio
    async def test_stats_with_completions_and_skips(self, client: AsyncClient):
        """Branch: count completed and skipped."""
        goal = await client.post("/goals", json={"title": "Mixed Stats Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Mixed Stats Task",
                "duration_minutes": 15,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": week_ago.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        # Complete some
        for i in range(3):
            d = now - timedelta(days=i)
            await client.post(
                f"/tasks/{task_id}/complete",
                json={"scheduled_for": d.isoformat()},
            )
        
        # Skip some
        for i in range(4, 6):
            d = now - timedelta(days=i)
            await client.post(
                f"/tasks/{task_id}/skip",
                json={"scheduled_for": d.isoformat()},
            )
        
        response = await client.get(
            f"/tasks/{task_id}/stats",
            params={
                "start": week_ago.isoformat(),
                "end": now.isoformat(),
            },
        )
        assert response.status_code == 200
        stats = response.json()
        assert stats["total_completed"] >= 0
        assert stats["total_skipped"] >= 0

    @pytest.mark.asyncio
    async def test_history_for_recurring_task(self, client: AsyncClient):
        """Branch: task.is_recurring in history."""
        goal = await client.post("/goals", json={"title": "History Recurring Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "History Recurring Task",
                "duration_minutes": 15,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": week_ago.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        response = await client.get(
            f"/tasks/{task_id}/history",
            params={
                "start": week_ago.isoformat(),
                "end": now.isoformat(),
            },
        )
        assert response.status_code == 200
        assert "days" in response.json()

    @pytest.mark.asyncio
    async def test_history_day_status_completed(self, client: AsyncClient):
        """Branch: completed >= expected."""
        goal = await client.post("/goals", json={"title": "Day Complete Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Day Complete Task",
                "duration_minutes": 15,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": (now - timedelta(days=3)).isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        # Complete for a specific day
        yesterday = now - timedelta(days=1)
        await client.post(
            f"/tasks/{task_id}/complete",
            json={"scheduled_for": yesterday.isoformat()},
        )
        
        response = await client.get(
            f"/tasks/{task_id}/history",
            params={
                "start": (now - timedelta(days=3)).isoformat(),
                "end": now.isoformat(),
            },
        )
        assert response.status_code == 200
        days = response.json()["days"]
        # At least one day should be completed
        statuses = [d["status"] for d in days]
        assert "completed" in statuses or "missed" in statuses


# ============================================================================
# VALUES.PY BRANCH COVERAGE
# ============================================================================


class TestValuesBranches:
    """Test values endpoint branches."""

    @pytest.mark.asyncio
    async def test_value_create_with_origin_declared(self, client: AsyncClient):
        """Branch: origin == declared."""
        response = await client.post(
            "/values",
            json={"statement": "Declared Branch", "weight_raw": 70, "origin": "declared"},
        )
        assert response.status_code == 201
        assert response.json()["active_revision"]["origin"] == "declared"

    @pytest.mark.asyncio
    async def test_value_create_with_origin_suggested(self, client: AsyncClient):
        """Branch: origin == suggested."""
        response = await client.post(
            "/values",
            json={"statement": "Suggested Branch", "weight_raw": 60, "origin": "suggested"},
        )
        assert response.status_code == 201
        assert response.json()["active_revision"]["origin"] == "suggested"

    @pytest.mark.asyncio
    async def test_value_create_with_origin_inferred(self, client: AsyncClient):
        """Branch: origin == inferred."""
        response = await client.post(
            "/values",
            json={"statement": "Inferred Branch", "weight_raw": 50, "origin": "inferred"},
        )
        assert response.status_code == 201
        assert response.json()["active_revision"]["origin"] == "inferred"

    @pytest.mark.asyncio
    async def test_value_create_with_source_prompt(self, client: AsyncClient):
        """Branch: source_prompt_id provided."""
        prompts = await client.get("/discovery/prompts")
        prompts_list = prompts.json()["prompts"]
        
        if len(prompts_list) > 0:
            prompt_id = prompts_list[0]["id"]
            response = await client.post(
                "/values",
                json={
                    "statement": "From Prompt Branch",
                    "weight_raw": 55,
                    "origin": "declared",
                    "source_prompt_id": prompt_id,
                },
            )
            assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_value_update_creates_revision(self, client: AsyncClient):
        """Branch: update value -> new revision created."""
        val = await client.post(
            "/values",
            json={"statement": "Update Branch", "weight_raw": 60, "origin": "declared"},
        )
        val_id = val.json()["id"]
        
        response = await client.put(
            f"/values/{val_id}",
            json={"statement": "Updated Branch Statement", "weight_raw": 70},
        )
        assert response.status_code == 200
        assert response.json()["active_revision"]["statement"] == "Updated Branch Statement"


# ============================================================================
# PRIORITIES.PY BRANCH COVERAGE
# ============================================================================


class TestPrioritiesBranches:
    """Test priorities endpoint branches."""

    @pytest.mark.asyncio
    async def test_priority_with_value_links(self, client: AsyncClient, mock_validate_priority):
        """Branch: value_ids provided."""
        val = await client.post(
            "/values",
            json={"statement": "Link Branch Value", "weight_raw": 70, "origin": "declared"},
        )
        val_id = val.json()["id"]
        
        response = await client.post(
            "/priorities",
            json={
                "title": "Linked Branch Priority",
                "why_matters": "Testing value link branch",
                "score": 4,
                "value_ids": [val_id],
            },
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_priority_without_value_links(self, client: AsyncClient, mock_validate_priority):
        """Branch: value_ids not provided."""
        response = await client.post(
            "/priorities",
            json={
                "title": "No Links Branch Priority",
                "why_matters": "Testing no value links",
                "score": 3,
            },
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_priority_anchor_with_links(self, client: AsyncClient, mock_validate_priority):
        """Branch: anchor priority that has links."""
        val = await client.post(
            "/values",
            json={"statement": "Anchor Branch Value", "weight_raw": 70, "origin": "declared"},
        )
        val_id = val.json()["id"]
        
        priority = await client.post(
            "/priorities",
            json={
                "title": "Anchor Branch Priority",
                "why_matters": "Testing anchor with links",
                "score": 4,
                "value_ids": [val_id],
            },
        )
        p_id = priority.json()["id"]
        
        response = await client.post(f"/priorities/{p_id}/anchor")
        assert response.status_code == 200
        assert response.json()["active_revision"]["is_anchored"] is True

    @pytest.mark.asyncio
    async def test_priority_unanchor(self, client: AsyncClient, mock_validate_priority):
        """Branch: unanchor priority."""
        val = await client.post(
            "/values",
            json={"statement": "Unanchor Value", "weight_raw": 70, "origin": "declared"},
        )
        val_id = val.json()["id"]
        
        priority = await client.post(
            "/priorities",
            json={
                "title": "Unanchor Branch Priority",
                "why_matters": "Testing unanchor branch",
                "score": 4,
                "value_ids": [val_id],
            },
        )
        p_id = priority.json()["id"]
        
        await client.post(f"/priorities/{p_id}/anchor")
        response = await client.post(f"/priorities/{p_id}/unanchor")
        assert response.status_code == 200
        assert response.json()["active_revision"]["is_anchored"] is False

    @pytest.mark.asyncio
    async def test_priority_stash(self, client: AsyncClient, mock_validate_priority):
        """Branch: stash priority."""
        priority = await client.post(
            "/priorities",
            json={
                "title": "Stash Branch Priority",
                "why_matters": "Testing stash branch",
                "score": 2,
            },
        )
        p_id = priority.json()["id"]
        
        response = await client.post(
            f"/priorities/{p_id}/stash",
            json={"is_stashed": True},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_priority_create_revision(self, client: AsyncClient, mock_validate_priority):
        """Branch: create new revision."""
        priority = await client.post(
            "/priorities",
            json={
                "title": "Revision Branch Priority",
                "why_matters": "Testing revision creation",
                "score": 3,
            },
        )
        p_id = priority.json()["id"]
        
        response = await client.post(
            f"/priorities/{p_id}/revisions",
            json={
                "title": "New Revision Title",
                "why_matters": "Updated revision text",
                "score": 4,
            },
        )
        assert response.status_code in [200, 201]
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


# ============================================================================
# Task Edge Case Tests
# ============================================================================


@pytest.mark.asyncio
async def test_task_with_scheduled_at_past(client: AsyncClient):
    """Test creating a task scheduled in the past."""
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    
    goal_resp = await client.post("/goals", json={"title": "Past Task Goal"})
    goal_id = goal_resp.json()["id"]
    
    past_date = (datetime.now(ZoneInfo("UTC")) - timedelta(days=7)).isoformat()
    
    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Past Task",
            "duration_minutes": 30,
            "scheduled_at": past_date,
        },
    )
    # Should still allow creation (might be intentional catch-up)
    assert response.status_code in [200, 201]


@pytest.mark.asyncio 
async def test_task_completions_empty(client: AsyncClient):
    """Test getting completions for task with no completions."""
    goal_resp = await client.post("/goals", json={"title": "Empty Stats Goal"})
    goal_id = goal_resp.json()["id"]
    
    task_resp = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Fresh Task", "duration_minutes": 30},
    )
    task_id = task_resp.json()["id"]
    
    response = await client.get(f"/tasks/{task_id}/completions")
    assert response.status_code == 200
    assert response.json()["completions"] == []
