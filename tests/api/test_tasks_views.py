"""Tests for task views API endpoints.

Source file: app/api/tasks_views.py
Endpoints: GET /tasks/view/today, POST /tasks/view/range, GET /tasks/{id}/completions
"""

import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient

from app.models.user import User


# ============================================================================
# Helper Functions
# ============================================================================


async def create_goal(client: AsyncClient) -> str:
    """Create a test goal and return its ID."""
    response = await client.post("/goals", json={"title": "Test Goal"})
    assert response.status_code == 201
    return response.json()["id"]


async def create_task(
    client: AsyncClient, 
    goal_id: str, 
    is_recurring: bool = False,
    scheduled_at: str | None = None,
    **kwargs
) -> str:
    """Create a test task and return its ID."""
    now = datetime.now(timezone.utc)
    data = {
        "goal_id": goal_id,
        "title": kwargs.get("title", "Test Task"),
        "duration_minutes": kwargs.get("duration_minutes", 30),
        "scheduled_at": scheduled_at or now.isoformat(),
    }
    if is_recurring:
        data["is_recurring"] = True
        data["recurrence_rule"] = kwargs.get("recurrence_rule", "FREQ=DAILY")
        data["scheduling_mode"] = "floating"
        data["recurrence_behavior"] = "habitual"
    response = await client.post("/tasks", json=data)
    assert response.status_code == 201, f"Failed to create task: {response.json()}"
    return response.json()["id"]


# ============================================================================
# GET /tasks/view/today Tests
# ============================================================================


@pytest.mark.asyncio
async def test_today_tasks_returns_empty_when_no_tasks(client: AsyncClient):
    """Test today view returns empty list when user has no tasks."""
    response = await client.get("/tasks/view/today")
    
    assert response.status_code == 200
    data = response.json()
    assert data["tasks"] == []
    assert data["pending_count"] == 0
    assert data["completed_today_count"] == 0
    assert data["overdue_count"] == 0


@pytest.mark.asyncio
async def test_today_tasks_returns_scheduled_tasks(client: AsyncClient):
    """Test today view returns tasks scheduled for today."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    scheduled = now.isoformat()
    
    task_id = await create_task(client, goal_id, scheduled_at=scheduled)
    
    response = await client.get("/tasks/view/today")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["tasks"]) >= 1
    task_ids = [t["id"] for t in data["tasks"]]
    assert task_id in task_ids


@pytest.mark.asyncio
async def test_today_tasks_returns_recurring_tasks(client: AsyncClient):
    """Test today view returns recurring tasks."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    
    task_id = await create_task(client, goal_id, is_recurring=True, scheduled_at=now.isoformat())
    
    response = await client.get("/tasks/view/today")
    
    assert response.status_code == 200
    data = response.json()
    task_ids = [t["id"] for t in data["tasks"]]
    assert task_id in task_ids


@pytest.mark.asyncio
async def test_today_tasks_excludes_completed_by_default(client: AsyncClient):
    """Test today view excludes completed tasks by default."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    task_id = await create_task(client, goal_id, scheduled_at=now.isoformat())
    
    # Complete the task
    await client.post(f"/tasks/{task_id}/complete", json={})
    
    response = await client.get("/tasks/view/today")
    
    assert response.status_code == 200
    data = response.json()
    task_ids = [t["id"] for t in data["tasks"]]
    assert task_id not in task_ids


@pytest.mark.asyncio
async def test_today_tasks_includes_completed_when_requested(client: AsyncClient):
    """Test today view includes completed tasks when include_completed=true."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    task_id = await create_task(client, goal_id, scheduled_at=now.isoformat())
    
    # Complete the task
    await client.post(f"/tasks/{task_id}/complete", json={})
    
    response = await client.get("/tasks/view/today?include_completed=true")
    
    assert response.status_code == 200
    data = response.json()
    task_ids = [t["id"] for t in data["tasks"]]
    assert task_id in task_ids


@pytest.mark.asyncio
async def test_today_tasks_returns_pending_count(client: AsyncClient):
    """Test today view returns correct pending count."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    
    await create_task(client, goal_id, scheduled_at=now.isoformat())
    await create_task(client, goal_id, title="Task 2", scheduled_at=now.isoformat())
    
    response = await client.get("/tasks/view/today")
    
    assert response.status_code == 200
    data = response.json()
    assert data["pending_count"] >= 2


@pytest.mark.asyncio
async def test_today_tasks_with_timezone(client: AsyncClient):
    """Test today view respects timezone parameter."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    await create_task(client, goal_id, scheduled_at=now.isoformat())
    
    response = await client.get("/tasks/view/today?timezone=America/New_York")
    
    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data


@pytest.mark.asyncio
async def test_today_tasks_with_invalid_timezone_defaults_to_utc(client: AsyncClient):
    """Test today view defaults to UTC for invalid timezone."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    await create_task(client, goal_id, scheduled_at=now.isoformat())
    
    response = await client.get("/tasks/view/today?timezone=Invalid/Zone")
    
    assert response.status_code == 200  # Should not fail


# ============================================================================
# POST /tasks/view/range Tests
# ============================================================================


@pytest.mark.asyncio
async def test_range_tasks_returns_tasks_in_range(client: AsyncClient):
    """Test range view returns tasks within specified date range."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    scheduled = now.isoformat()
    
    task_id = await create_task(client, goal_id, scheduled_at=scheduled)
    
    start = (now - timedelta(hours=1)).isoformat()
    end = (now + timedelta(hours=1)).isoformat()
    
    response = await client.post(
        "/tasks/view/range",
        json={
            "start_date": start,
            "end_date": end,
            "limit": 50,
            "offset": 0,
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    task_ids = [t["id"] for t in data["tasks"]]
    assert task_id in task_ids


@pytest.mark.asyncio
async def test_range_tasks_excludes_tasks_outside_range(client: AsyncClient):
    """Test range view excludes tasks outside specified date range."""
    goal_id = await create_goal(client)
    future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    
    task_id = await create_task(client, goal_id, scheduled_at=future)
    
    now = datetime.now(timezone.utc)
    start = (now - timedelta(hours=1)).isoformat()
    end = (now + timedelta(hours=1)).isoformat()
    
    response = await client.post(
        "/tasks/view/range",
        json={
            "start_date": start,
            "end_date": end,
            "limit": 50,
            "offset": 0,
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    task_ids = [t["id"] for t in data["tasks"]]
    assert task_id not in task_ids


@pytest.mark.asyncio
async def test_range_tasks_supports_pagination(client: AsyncClient):
    """Test range view supports pagination with offset and limit."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    
    # Create multiple tasks
    for i in range(5):
        scheduled = (now + timedelta(minutes=i)).isoformat()
        await create_task(client, goal_id, title=f"Task {i}", scheduled_at=scheduled)
    
    start = (now - timedelta(hours=1)).isoformat()
    end = (now + timedelta(hours=1)).isoformat()
    
    # First page
    response = await client.post(
        "/tasks/view/range",
        json={
            "start_date": start,
            "end_date": end,
            "limit": 2,
            "offset": 0,
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["tasks"]) == 2
    assert data["has_more"] is True


@pytest.mark.asyncio
async def test_range_tasks_returns_total_count(client: AsyncClient):
    """Test range view returns total count."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    
    for i in range(3):
        scheduled = (now + timedelta(minutes=i)).isoformat()
        await create_task(client, goal_id, title=f"Task {i}", scheduled_at=scheduled)
    
    start = (now - timedelta(hours=1)).isoformat()
    end = (now + timedelta(hours=1)).isoformat()
    
    response = await client.post(
        "/tasks/view/range",
        json={
            "start_date": start,
            "end_date": end,
            "limit": 50,
            "offset": 0,
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 3


@pytest.mark.asyncio
async def test_range_tasks_excludes_completed_by_default(client: AsyncClient):
    """Test range view excludes completed tasks by default."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    scheduled = now.isoformat()
    
    task_id = await create_task(client, goal_id, scheduled_at=scheduled)
    await client.post(f"/tasks/{task_id}/complete", json={})
    
    start = (now - timedelta(hours=1)).isoformat()
    end = (now + timedelta(hours=1)).isoformat()
    
    response = await client.post(
        "/tasks/view/range",
        json={
            "start_date": start,
            "end_date": end,
            "limit": 50,
            "offset": 0,
            "include_completed": False,
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    task_ids = [t["id"] for t in data["tasks"]]
    assert task_id not in task_ids


@pytest.mark.asyncio
async def test_range_tasks_includes_completed_when_requested(client: AsyncClient):
    """Test range view includes completed when include_completed=true."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    scheduled = now.isoformat()
    
    task_id = await create_task(client, goal_id, scheduled_at=scheduled)
    await client.post(f"/tasks/{task_id}/complete", json={})
    
    start = (now - timedelta(hours=1)).isoformat()
    end = (now + timedelta(hours=1)).isoformat()
    
    response = await client.post(
        "/tasks/view/range",
        json={
            "start_date": start,
            "end_date": end,
            "limit": 50,
            "offset": 0,
            "include_completed": True,
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    task_ids = [t["id"] for t in data["tasks"]]
    assert task_id in task_ids


# ============================================================================
# GET /tasks/{id}/completions Tests
# ============================================================================


@pytest.mark.asyncio
async def test_completions_returns_empty_for_non_recurring_task(client: AsyncClient):
    """Test completions returns empty list for non-recurring task."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id, is_recurring=False)
    
    response = await client.get(f"/tasks/{task_id}/completions")
    
    assert response.status_code == 200
    data = response.json()
    assert data["completions"] == []
    assert data["total"] == 0
    assert data["completed_count"] == 0
    assert data["skipped_count"] == 0


@pytest.mark.asyncio
async def test_completions_returns_completion_history(client: AsyncClient):
    """Test completions returns completion records for recurring task."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    task_id = await create_task(client, goal_id, is_recurring=True, scheduled_at=now.isoformat())
    
    # Complete the task
    await client.post(f"/tasks/{task_id}/complete", json={"scheduled_for": now.isoformat()})
    
    response = await client.get(f"/tasks/{task_id}/completions")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert data["completed_count"] >= 1


@pytest.mark.asyncio
async def test_completions_counts_completed_and_skipped(client: AsyncClient):
    """Test completions correctly counts completed and skipped entries."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    task_id = await create_task(client, goal_id, is_recurring=True, scheduled_at=now.isoformat())
    
    # Complete twice
    await client.post(f"/tasks/{task_id}/complete", json={"scheduled_for": now.isoformat()})
    await client.post(f"/tasks/{task_id}/complete", json={"scheduled_for": (now + timedelta(days=1)).isoformat()})
    
    # Skip once
    await client.post(f"/tasks/{task_id}/skip", json={"scheduled_for": (now + timedelta(days=2)).isoformat()})
    
    response = await client.get(f"/tasks/{task_id}/completions")
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 3
    assert data["completed_count"] == 2
    assert data["skipped_count"] == 1


@pytest.mark.asyncio
async def test_completions_supports_pagination(client: AsyncClient):
    """Test completions supports limit and offset parameters."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    task_id = await create_task(client, goal_id, is_recurring=True, scheduled_at=now.isoformat())
    
    # Create multiple completions
    for i in range(5):
        await client.post(
            f"/tasks/{task_id}/complete", 
            json={"scheduled_for": (now + timedelta(days=i)).isoformat()}
        )
    
    response = await client.get(f"/tasks/{task_id}/completions?limit=2&offset=0")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["completions"]) == 2
    assert data["total"] == 5


@pytest.mark.asyncio
async def test_completions_ordered_by_completion_date(client: AsyncClient):
    """Test completions are ordered by completion date descending."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc)
    task_id = await create_task(client, goal_id, is_recurring=True, scheduled_at=now.isoformat())
    
    # Create completions
    await client.post(f"/tasks/{task_id}/complete", json={"scheduled_for": now.isoformat()})
    await client.post(f"/tasks/{task_id}/complete", json={"scheduled_for": (now + timedelta(days=1)).isoformat()})
    
    response = await client.get(f"/tasks/{task_id}/completions")
    
    assert response.status_code == 200
    data = response.json()
    # Most recent should be first (descending order)
    if len(data["completions"]) >= 2:
        first_date = data["completions"][0]["completed_at"]
        second_date = data["completions"][1]["completed_at"]
        assert first_date >= second_date


@pytest.mark.asyncio
async def test_completions_nonexistent_task_returns_404(client: AsyncClient):
    """Test completions for non-existent task returns 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    
    response = await client.get(f"/tasks/{fake_id}/completions")
    
    assert response.status_code == 404


# ---- migrated from tests/mocked/test_services_views_migrated.py ----

"""Migrated task view tests split from mixed services file."""

from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_today_view_empty(client: AsyncClient):
    response = await client.get("/tasks/view/today")
    assert response.status_code == 200
    assert "tasks" in response.json()


@pytest.mark.asyncio
async def test_range_view_invalid_dates(client: AsyncClient):
    now = datetime.now(timezone.utc)
    response = await client.post(
        "/tasks/view/range",
        json={
            "start_date": now.isoformat(),
            "end_date": (now - timedelta(days=7)).isoformat(),
        },
    )
    assert response.status_code == 200
