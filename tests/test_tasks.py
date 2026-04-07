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
