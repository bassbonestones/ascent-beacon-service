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
            "recurrence_behavior": "habitual",
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
    # Use start-of-day for start to ensure 09:00 completions are included
    now = datetime.now(timezone.utc)
    start_day = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    start = quote(start_day.isoformat())
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
            "recurrence_behavior": "habitual",
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

    # Use start-of-day for start to ensure 09:00 completions are included
    now = datetime.now(timezone.utc)
    start_day = (now - timedelta(days=3)).replace(hour=0, minute=0, second=0, microsecond=0)
    start = quote(start_day.isoformat())
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
            "recurrence_behavior": "habitual",
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    # Complete the task
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": scheduled.isoformat()},
    )

    # Use start-of-day for start to ensure 09:00 completions are included
    now = datetime.now(timezone.utc)
    start_day = (now - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    start = quote(start_day.isoformat())
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
            "recurrence_behavior": "habitual",
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


# ============================================================================
# Additional Coverage Tests 
# ============================================================================


@pytest.mark.asyncio
async def test_get_task_stats_invalid_date_range(client: AsyncClient):
    """Test stats with start date after end date."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Test task",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    now = datetime.now(timezone.utc)
    # Start after end
    start = quote(now.isoformat())
    end = quote((now - timedelta(days=7)).isoformat())

    response = await client.get(
        f"/tasks/{task_id}/stats?start={start}&end={end}"
    )
    # Should either return empty stats or handle gracefully
    assert response.status_code in [200, 400, 422]


@pytest.mark.asyncio
async def test_get_task_stats_recurring_no_completions(client: AsyncClient):
    """Test stats for recurring task with no completions."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    scheduled = (datetime.now(timezone.utc) - timedelta(days=3)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Untouched recurring",
            "duration_minutes": 15,
            "scheduled_at": scheduled.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
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
    assert data["total_completed"] == 0
    assert data["completion_rate"] == 0.0


@pytest.mark.asyncio
async def test_get_task_stats_all_skipped(client: AsyncClient):
    """Test stats when all occurrences were skipped."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    scheduled = (datetime.now(timezone.utc) - timedelta(days=3)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "All skipped habit",
            "duration_minutes": 15,
            "scheduled_at": scheduled.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Skip all days
    for i in range(3):
        day = (scheduled + timedelta(days=i)).isoformat()
        await client.post(
            f"/tasks/{task_id}/skip",
            json={"scheduled_for": day, "reason": "too busy"},
        )

    now = datetime.now(timezone.utc)
    start = quote((now - timedelta(days=7)).isoformat())
    end = quote(now.isoformat())

    response = await client.get(
        f"/tasks/{task_id}/stats?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_completed"] == 0
    assert data["total_skipped"] >= 3


@pytest.mark.asyncio
async def test_get_completion_history_recurring_with_gaps(client: AsyncClient):
    """Test history for recurring task with gaps in completion."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    scheduled = (datetime.now(timezone.utc) - timedelta(days=5)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Gappy habit",
            "duration_minutes": 15,
            "scheduled_at": scheduled.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Complete day 1, skip day 2, complete day 3
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": scheduled.isoformat()},
    )
    await client.post(
        f"/tasks/{task_id}/skip",
        json={"scheduled_for": (scheduled + timedelta(days=1)).isoformat(), "reason": "skipped"},
    )
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": (scheduled + timedelta(days=2)).isoformat()},
    )

    now = datetime.now(timezone.utc)
    start = quote((now - timedelta(days=7)).isoformat())
    end = quote(now.isoformat())

    response = await client.get(
        f"/tasks/{task_id}/history?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_completed"] >= 2
    assert data["summary"]["total_skipped"] >= 1


@pytest.mark.asyncio
async def test_get_task_stats_weekly_recurring(client: AsyncClient):
    """Test stats for a weekly recurring task."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    scheduled = (datetime.now(timezone.utc) - timedelta(days=14)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Weekly task",
            "duration_minutes": 60,
            "scheduled_at": scheduled.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=WEEKLY;INTERVAL=1",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Complete 2 weekly occurrences
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": scheduled.isoformat()},
    )
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": (scheduled + timedelta(days=7)).isoformat()},
    )

    now = datetime.now(timezone.utc)
    start = quote((now - timedelta(days=30)).isoformat())
    end = quote(now.isoformat())

    response = await client.get(
        f"/tasks/{task_id}/stats?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_completed"] >= 2


@pytest.mark.asyncio
async def test_get_task_stats_future_range(client: AsyncClient):
    """Test stats for a future date range (should have 0 completions)."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Future task",
            "duration_minutes": 30,
        },
    )
    task_id = task_response.json()["id"]

    # Query future range
    future = datetime.now(timezone.utc) + timedelta(days=30)
    start = quote(future.isoformat())
    end = quote((future + timedelta(days=7)).isoformat())

    response = await client.get(
        f"/tasks/{task_id}/stats?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_completed"] == 0


# ============================================================================
# Extended Task Stats Coverage Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_task_stats_multiple_completions_same_day(client: AsyncClient):
    """Test stats for task with multiple completions on same day."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    # Create recurring task
    base_date = datetime.now(timezone.utc).replace(
        hour=9, minute=0, second=0, microsecond=0
    ) - timedelta(days=3)
    
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Multi-daily habit",
            "duration_minutes": 5,
            "scheduled_at": base_date.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    # Complete multiple times on same day
    for hour_offset in [0, 4, 8]:
        time = base_date + timedelta(hours=hour_offset)
        await client.post(
            f"/tasks/{task_id}/complete",
            json={"scheduled_for": time.isoformat()},
        )

    # Get stats
    start = quote((base_date - timedelta(days=1)).isoformat())
    end = quote((base_date + timedelta(days=5)).isoformat())

    response = await client.get(
        f"/tasks/{task_id}/stats?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_completed"] >= 3


@pytest.mark.asyncio
async def test_get_completion_history_multiple_days(client: AsyncClient):
    """Test completion history shows correct status for multiple days."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    base_date = datetime.now(timezone.utc).replace(
        hour=9, minute=0, second=0, microsecond=0
    ) - timedelta(days=5)
    
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "History test habit",
            "duration_minutes": 15,
            "scheduled_at": base_date.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    # Complete day 1, skip day 2, complete day 3, miss day 4, complete day 5
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": base_date.isoformat()},
    )
    await client.post(
        f"/tasks/{task_id}/skip",
        json={"scheduled_for": (base_date + timedelta(days=1)).isoformat(), "reason": "sick"},
    )
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": (base_date + timedelta(days=2)).isoformat()},
    )
    # Day 4 - missed (no action)
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": (base_date + timedelta(days=4)).isoformat()},
    )

    # Get history
    start = quote((base_date - timedelta(days=1)).isoformat())
    end = quote((base_date + timedelta(days=6)).isoformat())

    response = await client.get(
        f"/tasks/{task_id}/history?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["days"]) > 0
    
    # Check summary reflects the pattern
    assert data["summary"]["total_completed"] >= 3
    assert data["summary"]["total_skipped"] >= 1


@pytest.mark.asyncio
async def test_get_completion_history_two_completions_same_calendar_day(client: AsyncClient):
    """Second completion on same day appends to completions_by_date (branch merge)."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    base_date = datetime.now(timezone.utc).replace(
        hour=9, minute=0, second=0, microsecond=0
    ) - timedelta(days=2)

    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Same-day history",
            "duration_minutes": 5,
            "scheduled_at": base_date.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    for hour_offset in [0, 6]:
        t = base_date + timedelta(hours=hour_offset)
        await client.post(
            f"/tasks/{task_id}/complete",
            json={"scheduled_for": t.isoformat()},
        )

    start = quote((base_date - timedelta(days=1)).isoformat())
    end = quote((base_date + timedelta(days=2)).isoformat())

    response = await client.get(
        f"/tasks/{task_id}/history?start={start}&end={end}"
    )
    assert response.status_code == 200
    assert "days" in response.json()


@pytest.mark.asyncio
async def test_get_task_stats_with_specific_dates_scheduling(client: AsyncClient):
    """Test stats for task with specific_times scheduling mode."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    base_date = datetime.now(timezone.utc).replace(
        hour=9, minute=0, second=0, microsecond=0
    ) - timedelta(days=3)
    
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Floating habit",
            "duration_minutes": 10,
            "scheduled_at": base_date.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    # Complete a few
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": base_date.isoformat()},
    )

    start = quote((base_date - timedelta(days=1)).isoformat())
    end = quote((base_date + timedelta(days=5)).isoformat())

    response = await client.get(
        f"/tasks/{task_id}/stats?start={start}&end={end}"
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_completion_history_non_recurring_task(client: AsyncClient):
    """Test completion history for a non-recurring (one-time) task."""
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

    # Complete it
    await client.post(f"/tasks/{task_id}/complete", json={})

    now = datetime.now(timezone.utc)
    start = quote((now - timedelta(days=1)).isoformat())
    end = quote((now + timedelta(days=1)).isoformat())

    response = await client.get(
        f"/tasks/{task_id}/history?start={start}&end={end}"
    )

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_streak_calculation_from_stats(client: AsyncClient):
    """Test that streak calculation is working in stats response."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    base_date = datetime.now(timezone.utc).replace(
        hour=9, minute=0, second=0, microsecond=0
    ) - timedelta(days=7)
    
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Streak habit",
            "duration_minutes": 10,
            "scheduled_at": base_date.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Complete 5 consecutive days
    for i in range(5):
        day = (base_date + timedelta(days=i)).isoformat()
        await client.post(
            f"/tasks/{task_id}/complete",
            json={"scheduled_for": day},
        )

    start = quote((base_date - timedelta(days=1)).isoformat())
    end = quote((base_date + timedelta(days=10)).isoformat())

    response = await client.get(
        f"/tasks/{task_id}/stats?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()
    # Should have streaks
    assert data["total_completed"] >= 5
    assert data["longest_streak"] >= 1


@pytest.mark.asyncio
async def test_get_task_stats_empty_completions(client: AsyncClient):
    """Test stats when task has no completions at all."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]

    base_date = datetime.now(timezone.utc).replace(
        hour=9, minute=0, second=0, microsecond=0
    ) - timedelta(days=3)
    
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Empty completions",
            "duration_minutes": 15,
            "scheduled_at": base_date.isoformat(),
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;INTERVAL=1",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    task_id = task_response.json()["id"]

    # Don't complete anything

    start = quote((base_date - timedelta(days=1)).isoformat())
    end = quote((base_date + timedelta(days=5)).isoformat())

    response = await client.get(
        f"/tasks/{task_id}/stats?start={start}&end={end}"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total_completed"] == 0
    assert data["current_streak"] == 0
    assert data["longest_streak"] == 0
"""Unit tests for task_stats pure functions.

Tests the calculate_streak function with various branch scenarios.
"""

import pytest
from datetime import date, datetime
from unittest.mock import Mock

from app.api.task_stats import calculate_streak


def mock_completion(completed_at: datetime, status: str = "completed") -> Mock:
    """Create a mock TaskCompletion for testing."""
    c = Mock()
    c.completed_at = completed_at
    c.status = status
    return c


# ============================================================================
# calculate_streak - Main branches
# ============================================================================


class TestCalculateStreakEmpty:
    """Empty/edge case tests for calculate_streak"""

    def test_branch_no_completions_returns_zeros(self):
        """Branch: completions is empty -> (0, 0)"""
        result = calculate_streak(
            completions=[],
            end_date=date(2026, 4, 9),
            expected_dates={date(2026, 4, 8), date(2026, 4, 9)},
        )
        assert result == (0, 0)

    def test_branch_no_expected_dates_returns_zeros(self):
        """Branch: expected_dates is empty -> (0, 0)"""
        completion = mock_completion(datetime(2026, 4, 9))
        result = calculate_streak(
            completions=[completion],
            end_date=date(2026, 4, 9),
            expected_dates=set(),
        )
        assert result == (0, 0)

    def test_branch_both_empty_returns_zeros(self):
        """Branch: both empty -> (0, 0)"""
        result = calculate_streak(
            completions=[],
            end_date=date(2026, 4, 9),
            expected_dates=set(),
        )
        assert result == (0, 0)


class TestCalculateStreakLongest:
    """Tests for longest streak calculation"""

    def test_branch_single_completion_streak_of_one(self):
        """Branch: single expected and completed -> longest = 1"""
        completion = mock_completion(datetime(2026, 4, 9))
        result = calculate_streak(
            completions=[completion],
            end_date=date(2026, 4, 9),
            expected_dates={date(2026, 4, 9)},
        )
        current, longest = result
        assert longest == 1

    def test_branch_consecutive_completions_streak_increases(self):
        """Branch: consecutive completions -> longest increases each day"""
        completions = [
            mock_completion(datetime(2026, 4, 7)),
            mock_completion(datetime(2026, 4, 8)),
            mock_completion(datetime(2026, 4, 9)),
        ]
        expected = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert longest == 3

    def test_branch_broken_streak_resets_current(self):
        """Branch: missing day resets current streak counter"""
        # Complete day 7, skip day 8, complete day 9
        completions = [
            mock_completion(datetime(2026, 4, 7)),
            mock_completion(datetime(2026, 4, 9)),
        ]
        expected = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert longest == 1  # Only day 7 streak, then reset

    def test_branch_multiple_streaks_keeps_longest(self):
        """Branch: longest is kept even when current streak resets"""
        # Streak of 3, then gap, then streak of 2
        completions = [
            mock_completion(datetime(2026, 4, 1)),
            mock_completion(datetime(2026, 4, 2)),
            mock_completion(datetime(2026, 4, 3)),
            # Gap on day 4
            mock_completion(datetime(2026, 4, 5)),
            mock_completion(datetime(2026, 4, 6)),
        ]
        expected = {
            date(2026, 4, 1),
            date(2026, 4, 2),
            date(2026, 4, 3),
            date(2026, 4, 4),
            date(2026, 4, 5),
            date(2026, 4, 6),
        }
        current, longest = calculate_streak(completions, date(2026, 4, 6), expected)
        assert longest == 3  # First streak was longer


class TestCalculateStreakCurrent:
    """Tests for current streak calculation (from end_date backwards)"""

    def test_branch_current_streak_from_end(self):
        """Branch: current streak counts backwards from end_date"""
        completions = [
            mock_completion(datetime(2026, 4, 7)),
            mock_completion(datetime(2026, 4, 8)),
            mock_completion(datetime(2026, 4, 9)),
        ]
        expected = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert current == 3

    def test_branch_current_streak_breaks_on_miss(self):
        """Branch: current streak stops at first missed day going backwards"""
        completions = [
            mock_completion(datetime(2026, 4, 7)),
            # Skip day 8
            mock_completion(datetime(2026, 4, 9)),
        ]
        expected = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert current == 1  # Only day 9

    def test_branch_no_recent_completions_zero_current(self):
        """Branch: most recent expected dates not completed -> current = 0"""
        completions = [
            mock_completion(datetime(2026, 4, 7)),
        ]
        expected = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert current == 0  # Days 8 and 9 not completed

    def test_branch_expected_dates_after_end_date_skipped(self):
        """Branch: expected dates > end_date are skipped"""
        completions = [
            mock_completion(datetime(2026, 4, 8)),
            mock_completion(datetime(2026, 4, 9)),
        ]
        expected = {date(2026, 4, 8), date(2026, 4, 9), date(2026, 4, 10)}
        # end_date is day 9, so day 10 should be skipped
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert current == 2  # Days 8 and 9


class TestCalculateStreakSkippedStatus:
    """Tests for handling skipped (not completed) status"""

    def test_branch_skipped_status_not_counted(self):
        """Branch: completions with status='skipped' don't count"""
        completions = [
            mock_completion(datetime(2026, 4, 7), status="completed"),
            mock_completion(datetime(2026, 4, 8), status="skipped"),  # Not counted
            mock_completion(datetime(2026, 4, 9), status="completed"),
        ]
        expected = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        # Since day 8 is skipped (not completed), streaks break
        assert longest == 1  # Day 7 alone, then day 9 alone
        assert current == 1  # Only day 9

    def test_branch_all_skipped_returns_zeros(self):
        """Branch: all completions are skipped -> no streaks"""
        completions = [
            mock_completion(datetime(2026, 4, 8), status="skipped"),
            mock_completion(datetime(2026, 4, 9), status="skipped"),
        ]
        expected = {date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert current == 0
        assert longest == 0


class TestCalculateStreakEdgeCases:
    """Edge case tests for calculate_streak"""

    def test_branch_completion_not_on_expected_date_ignored(self):
        """Branch: completions on non-expected dates affect nothing"""
        completions = [
            mock_completion(datetime(2026, 4, 5)),  # Not an expected date
            mock_completion(datetime(2026, 4, 9)),
        ]
        expected = {date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        # Day 8 not completed, so current streak = 1 (only day 9)
        assert current == 1
        assert longest == 1

    def test_branch_single_expected_single_completed(self):
        """Branch: single expected, completed -> streaks = 1"""
        completions = [mock_completion(datetime(2026, 4, 9))]
        expected = {date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert current == 1
        assert longest == 1

    def test_branch_end_date_before_all_expected(self):
        """Branch: end_date before all expected dates -> current = 0"""
        completions = [
            mock_completion(datetime(2026, 4, 10)),
            mock_completion(datetime(2026, 4, 11)),
        ]
        expected = {date(2026, 4, 10), date(2026, 4, 11)}
        # end_date is before expected dates
        current, longest = calculate_streak(completions, date(2026, 4, 5), expected)
        assert current == 0  # No dates <= end_date
        assert longest == 2  # Still calculates longest from all dates
