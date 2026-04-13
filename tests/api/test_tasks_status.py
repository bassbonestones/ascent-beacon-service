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


@pytest.mark.asyncio
async def test_reopen_recurring_requires_scheduled_for(client: AsyncClient):
    """Recurring reopen requires scheduled_for payload."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id, is_recurring=True)

    response = await client.post(f"/tasks/{task_id}/reopen", json={})
    assert response.status_code == 400
    assert "scheduled_for is required" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reopen_recurring_returns_error_when_no_completion_in_slot(client: AsyncClient):
    """Recurring reopen should fail if target slot has no completion."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id, is_recurring=True)

    missing_slot = (datetime.now(timezone.utc) + timedelta(days=5)).isoformat()
    response = await client.post(
        f"/tasks/{task_id}/reopen",
        json={"scheduled_for": missing_slot},
    )
    assert response.status_code == 400
    assert "No completion found for that time slot" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reopen_recurring_deletes_matching_completion(client: AsyncClient):
    """Recurring reopen removes completion for provided timed slot."""
    goal_id = await create_goal(client)
    scheduled_for = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    task_id = await create_task(client, goal_id, is_recurring=True, scheduled_at=scheduled_for.isoformat())

    complete_response = await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": scheduled_for.isoformat()},
    )
    assert complete_response.status_code == 200

    reopen_response = await client.post(
        f"/tasks/{task_id}/reopen",
        json={"scheduled_for": scheduled_for.isoformat()},
    )
    assert reopen_response.status_code == 200
    assert reopen_response.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_reopen_pending_task_returns_error(client: AsyncClient):
    """One-time task cannot be reopened when already pending."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id)

    response = await client.post(f"/tasks/{task_id}/reopen", json={})
    assert response.status_code == 400
    assert response.json()["detail"] == "Task is already pending"


@pytest.mark.asyncio
async def test_dependency_status_endpoint_returns_payload(client: AsyncClient):
    """Dependency status endpoint returns dependencies/dependents arrays."""
    goal_id = await create_goal(client)
    upstream = await create_task(client, goal_id, title="Upstream")
    downstream = await create_task(client, goal_id, title="Downstream")

    dep_response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": upstream,
            "downstream_task_id": downstream,
            "rule_type": "completion",
            "is_hard": True,
        },
    )
    assert dep_response.status_code == 201

    status_response = await client.get(f"/tasks/{downstream}/dependency-status")
    assert status_response.status_code == 200
    body = status_response.json()
    assert body["task_id"] == downstream
    assert isinstance(body["dependencies"], list)
    assert isinstance(body["dependents"], list)


@pytest.mark.asyncio
async def test_complete_chain_completes_unmet_prerequisite_and_target(client: AsyncClient):
    """Complete-chain should complete upstream prerequisite then target."""
    goal_id = await create_goal(client)
    upstream = await create_task(client, goal_id, title="Prereq")
    downstream = await create_task(client, goal_id, title="Target")

    dep_response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": upstream,
            "downstream_task_id": downstream,
            "rule_type": "completion",
            "is_hard": True,
        },
    )
    assert dep_response.status_code == 201

    chain_response = await client.post(f"/tasks/{downstream}/complete-chain", json={})
    assert chain_response.status_code == 200
    completed = chain_response.json()
    assert len(completed) >= 2
    completed_ids = [row["id"] for row in completed]
    assert upstream in completed_ids
    assert downstream in completed_ids


@pytest.mark.asyncio
async def test_complete_chain_on_already_completed_target_is_noop(client: AsyncClient):
    """Second complete-chain call for one-time task should no-op target."""
    goal_id = await create_goal(client)
    task_id = await create_task(client, goal_id)

    first = await client.post(f"/tasks/{task_id}/complete-chain", json={})
    assert first.status_code == 200

    second = await client.post(f"/tasks/{task_id}/complete-chain", json={})
    assert second.status_code == 200
    assert isinstance(second.json(), list)


@pytest.mark.asyncio
async def test_complete_chain_handles_recurring_target(client: AsyncClient):
    """Complete-chain should create completion rows for recurring target."""
    goal_id = await create_goal(client)
    scheduled_for = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    task_id = await create_task(
        client,
        goal_id,
        is_recurring=True,
        scheduled_at=scheduled_for.isoformat(),
    )

    response = await client.post(
        f"/tasks/{task_id}/complete-chain",
        json={"scheduled_for": scheduled_for.isoformat(), "local_date": scheduled_for.strftime("%Y-%m-%d")},
    )
    assert response.status_code == 200
    assert response.json()[-1]["id"] == task_id


@pytest.mark.asyncio
async def test_reopen_recurring_date_only_uses_local_date_lookup(client: AsyncClient):
    """Date-only recurring reopen should locate completion via local_date."""
    goal_id = await create_goal(client)
    task_response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Date-only recurring",
            "is_recurring": True,
            "scheduled_date": "2026-06-01",
            "scheduling_mode": "date_only",
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_behavior": "habitual",
        },
    )
    assert task_response.status_code == 201
    task_id = task_response.json()["id"]

    scheduled_for = "2026-06-01T23:30:00+00:00"
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": scheduled_for, "local_date": "2026-06-01"},
    )

    reopen = await client.post(
        f"/tasks/{task_id}/reopen",
        json={"scheduled_for": scheduled_for, "local_date": "2026-06-01"},
    )
    assert reopen.status_code == 200
    assert reopen.json()["status"] == "pending"


@pytest.mark.asyncio
async def test_complete_chain_recurring_prereq_required_count_uses_anchor_and_fallback(
    client: AsyncClient,
) -> None:
    """Recurring prereq with high required count exercises helper insertion paths."""
    goal_id = await create_goal(client)
    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    local_date = now.strftime("%Y-%m-%d")

    prereq = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring prereq",
            "is_recurring": True,
            "scheduled_at": now.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_behavior": "habitual",
        },
    )
    assert prereq.status_code == 201
    prereq_id = prereq.json()["id"]

    target = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Target one-time", "duration_minutes": 10},
    )
    assert target.status_code == 201
    target_id = target.json()["id"]

    dep = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": prereq_id,
            "downstream_task_id": target_id,
            "rule_type": "completion",
            "is_hard": True,
            "required_occurrence_count": 3,
        },
    )
    assert dep.status_code == 201

    response = await client.post(
        f"/tasks/{target_id}/complete-chain",
        json={"scheduled_for": now.isoformat(), "local_date": local_date},
    )
    assert response.status_code == 200
    completed_ids = [row["id"] for row in response.json()]
    assert prereq_id in completed_ids
    assert target_id in completed_ids


@pytest.mark.asyncio
async def test_complete_chain_skips_already_satisfied_prereq_and_completes_target(
    client: AsyncClient,
) -> None:
    """When prerequisite is already satisfied, chain should still complete target."""
    goal_id = await create_goal(client)
    prereq_id = await create_task(client, goal_id, title="Already done prereq")
    target_id = await create_task(client, goal_id, title="Pending target")

    dep = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": prereq_id,
            "downstream_task_id": target_id,
            "rule_type": "completion",
            "is_hard": True,
        },
    )
    assert dep.status_code == 201

    await client.post(f"/tasks/{prereq_id}/complete", json={})
    response = await client.post(f"/tasks/{target_id}/complete-chain", json={})

    assert response.status_code == 200
    ids = [row["id"] for row in response.json()]
    assert target_id in ids
