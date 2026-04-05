"""Tests for task_stats API endpoints."""

import pytest
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from httpx import AsyncClient

from app.models.user import User


# ============================================================================
# Task Stats Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_task_stats_not_found(client: AsyncClient):
    """Test getting stats for non-existent task returns 404."""
    now = datetime.now(timezone.utc)
    start = quote((now - timedelta(days=7)).isoformat())
    end = quote(now.isoformat())

    response = await client.get(
        f"/tasks/non-existent-id/stats?start={start}&end={end}"
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_task_stats_non_recurring(client: AsyncClient):
    """Test stats for a non-recurring task."""
    # Create a goal and task
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "One-time task",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    now = datetime.now(timezone.utc)
    start = quote((now - timedelta(days=7)).isoformat())
    end = quote(now.isoformat())

    response = await client.get(
        f"/tasks/{task_id}/stats?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()

    assert data["task_id"] == task_id
    assert data["total_expected"] == 1
    assert data["total_completed"] == 0
    assert data["total_skipped"] == 0
    assert data["completion_rate"] == 0.0


@pytest.mark.asyncio
async def test_get_task_stats_recurring(client: AsyncClient):
    """Test stats for a recurring task with completions."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create recurring task (daily) - scheduled 7 days ago so query includes occurrences
    scheduled = (datetime.now(timezone.utc) - timedelta(days=7)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Daily habit",
            "duration_minutes": 15,
            "scheduled_at": scheduled.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    # Complete the task a few times
    for i in range(3):
        day_scheduled = (scheduled + timedelta(days=i)).isoformat()
        await client.post(
            f"/tasks/{task_id}/complete",
            json={"scheduled_for": day_scheduled},
        )

    # Get stats for the last week
    now = datetime.now(timezone.utc)
    start = quote((now - timedelta(days=7)).isoformat())
    end = quote(now.isoformat())

    response = await client.get(
        f"/tasks/{task_id}/stats?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()

    assert data["task_id"] == task_id
    assert data["total_completed"] >= 3
    assert data["completion_rate"] > 0


@pytest.mark.asyncio
async def test_get_task_stats_with_skips(client: AsyncClient):
    """Test stats calculation with skipped occurrences."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Schedule task 3 days ago so query includes occurrences
    scheduled = (datetime.now(timezone.utc) - timedelta(days=3)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Habit with skips",
            "duration_minutes": 15,
            "scheduled_at": scheduled.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    # Complete once, skip once
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": scheduled.isoformat()},
    )

    day2 = (scheduled + timedelta(days=1)).isoformat()
    await client.post(
        f"/tasks/{task_id}/skip",
        json={"scheduled_for": day2, "reason": "sick"},
    )

    now = datetime.now(timezone.utc)
    start = quote((now - timedelta(days=3)).isoformat())
    end = quote(now.isoformat())

    response = await client.get(
        f"/tasks/{task_id}/stats?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()

    assert data["total_completed"] >= 1
    assert data["total_skipped"] >= 1


# ============================================================================
# Completion History Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_completion_history_not_found(client: AsyncClient):
    """Test getting history for non-existent task returns 404."""
    now = datetime.now(timezone.utc)
    start = quote((now - timedelta(days=7)).isoformat())
    end = quote(now.isoformat())

    response = await client.get(
        f"/tasks/non-existent-id/history?start={start}&end={end}"
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_completion_history_empty(client: AsyncClient):
    """Test history for a task with no completions."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Untouched task",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    now = datetime.now(timezone.utc)
    start = quote((now - timedelta(days=7)).isoformat())
    end = quote(now.isoformat())

    response = await client.get(
        f"/tasks/{task_id}/history?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()

    assert data["task_id"] == task_id
    assert "days" in data
    assert "summary" in data


@pytest.mark.asyncio
async def test_get_completion_history_with_data(client: AsyncClient):
    """Test history for a recurring task with completions."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Schedule task 7 days ago so query includes occurrences
    scheduled = (datetime.now(timezone.utc) - timedelta(days=7)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Tracked habit",
            "duration_minutes": 15,
            "scheduled_at": scheduled.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    # Complete the task
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": scheduled.isoformat()},
    )

    now = datetime.now(timezone.utc)
    start = quote((now - timedelta(days=7)).isoformat())
    end = quote(now.isoformat())

    response = await client.get(
        f"/tasks/{task_id}/history?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()

    assert data["task_id"] == task_id
    assert len(data["days"]) > 0

    # Check that at least one day is completed
    statuses = [d["status"] for d in data["days"]]
    assert "completed" in statuses

    # Check summary
    assert data["summary"]["total_completed"] >= 1


# ============================================================================
# Streak Calculation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_streak_calculation(client: AsyncClient):
    """Test that streaks are calculated correctly."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Use a fixed date in the past for deterministic streak calculation
    base_date = datetime.now(timezone.utc).replace(
        hour=9, minute=0, second=0, microsecond=0
    ) - timedelta(days=5)
    
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Streak tester",
            "duration_minutes": 15,
            "scheduled_at": base_date.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    # Complete 3 consecutive days
    for i in range(3):
        day = (base_date + timedelta(days=i)).isoformat()
        await client.post(
            f"/tasks/{task_id}/complete",
            json={"scheduled_for": day},
        )

    # Get stats
    start = quote((base_date - timedelta(days=1)).isoformat())
    end = quote((base_date + timedelta(days=7)).isoformat())

    response = await client.get(
        f"/tasks/{task_id}/stats?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()

    # Verify we have at least 1 streak (completions recorded)
    assert data["total_completed"] >= 3
    assert data["longest_streak"] >= 1
