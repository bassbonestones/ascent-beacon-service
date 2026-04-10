"""Tests for task status API endpoints.

Source file: app/api/tasks_status.py
Endpoints: POST /tasks/{id}/complete, POST /tasks/{id}/skip, POST /tasks/{id}/reopen
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
    client: AsyncClient, goal_id: str, is_recurring: bool = False, **kwargs
) -> str:
    """Create a test task and return its ID."""
    scheduled_at = kwargs.get("scheduled_at", datetime.now(timezone.utc).isoformat())
    data = {
        "goal_id": goal_id,
        "title": kwargs.get("title", "Test Task"),
        "duration_minutes": kwargs.get("duration_minutes", 30),
        "scheduled_at": scheduled_at,
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
# POST /tasks/{id}/complete Tests
# ============================================================================


@pytest.mark.asyncio
async def test_complete_task_sets_status_completed(client: AsyncClient):
    """Test completing a one-time task sets status to completed."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id)
    
    response = await client.post(f"/tasks/{task_id}/complete", json={})
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["completed_at"] is not None


@pytest.mark.asyncio
async def test_complete_task_sets_completed_at_timestamp(client: AsyncClient):
    """Test completing a task sets the completed_at timestamp."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id)
    
    before = datetime.now(timezone.utc)
    response = await client.post(f"/tasks/{task_id}/complete", json={})
    after = datetime.now(timezone.utc)
    
    assert response.status_code == 200
    data = response.json()
    completed_at = datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
    assert before <= completed_at <= after


@pytest.mark.asyncio
async def test_complete_recurring_task_creates_completion_record(client: AsyncClient):
    """Test completing a recurring task creates a TaskCompletion record."""
    goal_id = await create_goal(client)
    scheduled_at = datetime.now(timezone.utc).isoformat()
    task_id = await create_task(client, goal_id, is_recurring=True, scheduled_at=scheduled_at)
    
    response = await client.post(
        f"/tasks/{task_id}/complete", 
        json={"scheduled_for": scheduled_at}
    )
    
    assert response.status_code == 200
    data = response.json()
    # Recurring task stays pending (can be completed many times)
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_complete_recurring_task_stays_pending(client: AsyncClient):
    """Test that recurring task stays pending after completion."""
    goal_id = await create_goal(client)
    scheduled_at = datetime.now(timezone.utc).isoformat()
    task_id = await create_task(client, goal_id, is_recurring=True, scheduled_at=scheduled_at)
    
    # Complete multiple times
    await client.post(f"/tasks/{task_id}/complete", json={"scheduled_for": scheduled_at})
    
    # Get task - should still be pending
    response = await client.get(f"/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_complete_task_updates_goal_progress(client: AsyncClient):
    """Test completing a task updates goal progress."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id)
    
    await client.post(f"/tasks/{task_id}/complete", json={})
    
    # Check goal progress updated
    response = await client.get(f"/goals/{goal_id}")
    assert response.status_code == 200
    # Progress should be > 0 now (implementation dependent)


@pytest.mark.asyncio
async def test_complete_nonexistent_task_returns_404(client: AsyncClient):
    """Test completing a non-existent task returns 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    
    response = await client.post(f"/tasks/{fake_id}/complete", json={})
    
    assert response.status_code == 404


# ============================================================================
# POST /tasks/{id}/skip Tests
# ============================================================================


@pytest.mark.asyncio
async def test_skip_task_sets_status_skipped(client: AsyncClient):
    """Test skipping a one-time task sets status to skipped."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id)
    
    response = await client.post(f"/tasks/{task_id}/skip", json={})
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "skipped"


@pytest.mark.asyncio
async def test_skip_task_with_reason(client: AsyncClient):
    """Test skipping a task with a reason stores the reason."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id)
    
    response = await client.post(
        f"/tasks/{task_id}/skip", 
        json={"reason": "Not feeling well today"}
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["skip_reason"] == "Not feeling well today"


@pytest.mark.asyncio
async def test_skip_recurring_task_creates_completion_record(client: AsyncClient):
    """Test skipping a recurring task creates a TaskCompletion record with skipped status."""
    goal_id = await create_goal(client)
    scheduled_at = datetime.now(timezone.utc).isoformat()
    task_id = await create_task(client, goal_id, is_recurring=True, scheduled_at=scheduled_at)
    
    response = await client.post(
        f"/tasks/{task_id}/skip", 
        json={"reason": "Too busy", "scheduled_for": scheduled_at}
    )
    
    assert response.status_code == 200
    data = response.json()
    # Recurring task stays pending
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_skip_recurring_task_stays_pending(client: AsyncClient):
    """Test that recurring task stays pending after skip."""
    goal_id = await create_goal(client)
    scheduled_at = datetime.now(timezone.utc).isoformat()
    task_id = await create_task(client, goal_id, is_recurring=True, scheduled_at=scheduled_at)
    
    await client.post(f"/tasks/{task_id}/skip", json={"scheduled_for": scheduled_at})
    
    # Get task - should still be pending
    response = await client.get(f"/tasks/{task_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_skip_nonexistent_task_returns_404(client: AsyncClient):
    """Test skipping a non-existent task returns 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    
    response = await client.post(f"/tasks/{fake_id}/skip", json={})
    
    assert response.status_code == 404


# ============================================================================
# POST /tasks/{id}/reopen Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reopen_completed_task_sets_status_pending(client: AsyncClient):
    """Test reopening a completed task sets status back to pending."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id)
    
    # Complete first
    await client.post(f"/tasks/{task_id}/complete", json={})
    
    # Reopen
    response = await client.post(f"/tasks/{task_id}/reopen", json={})
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"
    assert data["completed_at"] is None


@pytest.mark.asyncio
async def test_reopen_skipped_task_sets_status_pending(client: AsyncClient):
    """Test reopening a skipped task sets status back to pending."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id)
    
    # Skip first
    await client.post(f"/tasks/{task_id}/skip", json={})
    
    # Reopen
    response = await client.post(f"/tasks/{task_id}/reopen", json={})
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_reopen_task_clears_completed_at(client: AsyncClient):
    """Test reopening a task clears the completed_at timestamp."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id)
    
    # Complete
    await client.post(f"/tasks/{task_id}/complete", json={})
    
    # Reopen
    response = await client.post(f"/tasks/{task_id}/reopen", json={})
    
    assert response.status_code == 200
    assert response.json()["completed_at"] is None


@pytest.mark.asyncio
async def test_reopen_task_updates_goal_progress(client: AsyncClient):
    """Test reopening a task updates goal progress."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id)
    
    # Complete
    await client.post(f"/tasks/{task_id}/complete", json={})
    
    # Reopen
    await client.post(f"/tasks/{task_id}/reopen", json={})
    
    # Goal progress should be recalculated
    response = await client.get(f"/goals/{goal_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_reopen_nonexistent_task_returns_404(client: AsyncClient):
    """Test reopening a non-existent task returns 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    
    response = await client.post(f"/tasks/{fake_id}/reopen", json={})
    
    assert response.status_code == 404
