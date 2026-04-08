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
