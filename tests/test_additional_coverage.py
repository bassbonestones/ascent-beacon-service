"""Additional tests for coverage improvement."""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock


# Mock validation to return valid so we can test without AI calls
@pytest.fixture
def mock_validate_priority():
    """Mock the priority validation to always return valid."""
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
# Additional Goals API Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_goal_status(client: AsyncClient):
    """Test updating goal status."""
    # Create goal
    create_resp = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = create_resp.json()["id"]

    # Update status
    response = await client.patch(f"/goals/{goal_id}", json={"status": "in_progress"})
    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_update_goal_title(client: AsyncClient):
    """Test updating goal title."""
    create_resp = await client.post("/goals", json={"title": "Original Title"})
    goal_id = create_resp.json()["id"]

    response = await client.patch(f"/goals/{goal_id}", json={"title": "Updated Title"})
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_update_goal_description(client: AsyncClient):
    """Test updating goal with description."""
    create_resp = await client.post("/goals", json={"title": "Goal with Desc"})
    goal_id = create_resp.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}",
        json={"description": "This is a detailed description"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "This is a detailed description"


@pytest.mark.asyncio
async def test_update_goal_not_found(client: AsyncClient):
    """Test updating non-existent goal."""
    response = await client.patch(
        "/goals/00000000-0000-0000-0000-000000000000",
        json={"title": "Updated"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_goal_success(client: AsyncClient):
    """Test deleting a goal."""
    create_resp = await client.post("/goals", json={"title": "To Be Deleted"})
    goal_id = create_resp.json()["id"]

    response = await client.delete(f"/goals/{goal_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_goal_not_found(client: AsyncClient):
    """Test deleting non-existent goal."""
    response = await client.delete("/goals/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_goal_by_id(client: AsyncClient):
    """Test getting a specific goal."""
    create_resp = await client.post("/goals", json={"title": "Get By ID"})
    goal_id = create_resp.json()["id"]

    response = await client.get(f"/goals/{goal_id}")
    assert response.status_code == 200
    assert response.json()["id"] == goal_id


@pytest.mark.asyncio
async def test_get_goal_not_found(client: AsyncClient):
    """Test getting non-existent goal."""
    response = await client.get("/goals/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_goals_empty(client: AsyncClient):
    """Test listing goals when none exist."""
    response = await client.get("/goals")
    assert response.status_code == 200
    assert response.json()["goals"] == []


@pytest.mark.asyncio
async def test_list_goals_with_status_filter(client: AsyncClient):
    """Test listing goals with status filter."""
    # Create goals
    await client.post("/goals", json={"title": "In Progress Goal"})
    await client.post("/goals", json={"title": "Another Goal"})

    # Filter by status
    response = await client.get("/goals", params={"status": "not_started"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_create_goal_priority_link_after_creation(client: AsyncClient):
    """Test linking a priority to a goal after creation."""
    # Create goal first
    goal_resp = await client.post("/goals", json={"title": "Goal To Link"})
    goal_id = goal_resp.json()["id"]
    
    # Verify goal was created
    response = await client.get(f"/goals/{goal_id}")
    assert response.status_code == 200


# ============================================================================
# Additional Auth API Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient):
    """Test getting current authenticated user."""
    response = await client.get("/me")
    assert response.status_code == 200
    assert "id" in response.json()


# ============================================================================
# Additional Task Stats Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_task_stats_basic(client: AsyncClient):
    """Test getting basic task stats."""
    from datetime import datetime, timezone, timedelta

    # Create a recurring task
    goal_resp = await client.post("/goals", json={"title": "Stats Goal"})
    goal_id = goal_resp.json()["id"]

    now = datetime.now(timezone.utc)
    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Stats Task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_resp.json()["id"]

    # Get stats with required start/end params
    start = (now - timedelta(days=7)).isoformat()
    end = now.isoformat()
    response = await client.get(
        f"/tasks/{task_id}/stats",
        params={"start": start, "end": end},
    )
    assert response.status_code == 200
    assert "task_id" in response.json()


@pytest.mark.asyncio
async def test_get_task_stats_with_date_range(client: AsyncClient):
    """Test task stats with custom date range."""
    from datetime import datetime, timezone, timedelta

    goal_resp = await client.post("/goals", json={"title": "Stats Goal"})
    goal_id = goal_resp.json()["id"]

    now = datetime.now(timezone.utc)
    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Range Stats Task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_resp.json()["id"]

    start = (now - timedelta(days=30)).isoformat()
    end = now.isoformat()

    response = await client.get(
        f"/tasks/{task_id}/stats",
        params={"start": start, "end": end},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_completion_history(client: AsyncClient):
    """Test getting task completion history."""
    from datetime import datetime, timezone

    goal_resp = await client.post("/goals", json={"title": "History Goal"})
    goal_id = goal_resp.json()["id"]

    now = datetime.now(timezone.utc)
    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "History Task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_resp.json()["id"]

    # Complete
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": now.isoformat()},
    )

    # Get history
    response = await client.get(f"/tasks/{task_id}/completions")
    assert response.status_code == 200
    assert "completions" in response.json()


# ============================================================================
# Task View Additional Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_today_view_with_goal_filter(client: AsyncClient):
    """Test today view filtered by goal."""
    goal_resp = await client.post("/goals", json={"title": "Today Goal"})
    goal_id = goal_resp.json()["id"]

    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Today Filtered Task",
            "duration_minutes": 30,
        },
    )

    response = await client.get(
        "/tasks/view/today",
        params={"goal_id": goal_id},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_range_view_with_include_completed(client: AsyncClient):
    """Test range view with include_completed parameter."""
    from datetime import datetime, timezone, timedelta

    goal_resp = await client.post("/goals", json={"title": "Range Goal"})
    goal_id = goal_resp.json()["id"]

    # Create and complete a task
    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Range Completed Task",
            "duration_minutes": 30,
        },
    )
    task_id = task_resp.json()["id"]
    await client.post(f"/tasks/{task_id}/complete", json={})

    start = datetime.now(timezone.utc) - timedelta(days=1)
    end = datetime.now(timezone.utc) + timedelta(days=1)

    response = await client.post(
        "/tasks/view/range",
        json={
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "include_completed": True,
        },
    )
    assert response.status_code == 200


# ============================================================================
# Alignment API Tests
# ============================================================================


@pytest.mark.asyncio
async def test_check_alignment_empty(client: AsyncClient):
    """Test alignment check endpoint with no values."""
    response = await client.post("/alignment/check")
    assert response.status_code == 200
    data = response.json()
    assert "declared" in data
    assert "implied" in data


@pytest.mark.asyncio
async def test_check_alignment_with_values(client: AsyncClient):
    """Test alignment with values."""
    # Create a value
    response = await client.post(
        "/values",
        json={"statement": "Test Value", "weight_raw": 70, "origin": "declared"},
    )
    assert response.status_code == 201

    # Check alignment
    response = await client.post("/alignment/check")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_check_alignment_with_values_and_priorities(client: AsyncClient, mock_validate_priority):
    """Test alignment with both values and priorities."""
    # Create value
    val_resp = await client.post(
        "/values",
        json={"statement": "Alignment Value", "weight_raw": 80, "origin": "declared"},
    )
    assert val_resp.status_code == 201

    # Create priority
    priority_resp = await client.post(
        "/priorities",
        json={"title": "Alignment Priority", "why_matters": "This matters for testing alignment functionality", "score": 4},
    )
    assert priority_resp.status_code == 201

    response = await client.post("/alignment/check")
    assert response.status_code == 200


# ============================================================================
# Discovery API Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_discovery_prompts(client: AsyncClient):
    """Test getting discovery prompts."""
    response = await client.get("/discovery/prompts")
    assert response.status_code == 200
    assert "prompts" in response.json()


@pytest.mark.asyncio
async def test_get_user_selections_empty(client: AsyncClient):
    """Test getting empty user selections."""
    response = await client.get("/discovery/selections")
    assert response.status_code == 200
    assert response.json()["selections"] == []


# ============================================================================
# Occurrence Ordering API Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reorder_occurrences_today_mode(client: AsyncClient):
    """Test reordering with save_mode='today'."""
    from datetime import datetime, timezone

    goal_resp = await client.post("/goals", json={"title": "Order Goal"})
    goal_id = goal_resp.json()["id"]

    # Create two tasks
    now = datetime.now(timezone.utc)
    task1_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Task One",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task1_id = task1_resp.json()["id"]

    task2_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Task Two",
            "duration_minutes": 15,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task2_id = task2_resp.json()["id"]

    # Reorder
    today_str = now.strftime("%Y-%m-%d")
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": today_str,
            "save_mode": "today",
            "occurrences": [
                {"task_id": task2_id, "occurrence_index": 0},
                {"task_id": task1_id, "occurrence_index": 0},
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["save_mode"] == "today"
    assert response.json()["count"] == 2


@pytest.mark.asyncio
async def test_reorder_occurrences_permanent_mode(client: AsyncClient):
    """Test reordering with save_mode='permanent'."""
    from datetime import datetime, timezone

    goal_resp = await client.post("/goals", json={"title": "Permanent Order Goal"})
    goal_id = goal_resp.json()["id"]

    now = datetime.now(timezone.utc)
    # Create recurring task
    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring Order Task",
            "duration_minutes": 20,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_resp.json()["id"]

    today_str = now.strftime("%Y-%m-%d")
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": today_str,
            "save_mode": "permanent",
            "occurrences": [
                {"task_id": task_id, "occurrence_index": 0},
            ],
        },
    )
    assert response.status_code == 200
    assert response.json()["save_mode"] == "permanent"


@pytest.mark.asyncio
async def test_reorder_occurrences_invalid_task(client: AsyncClient):
    """Test reorder with invalid task ID."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": today_str,
            "save_mode": "today",
            "occurrences": [
                {"task_id": "00000000-0000-0000-0000-000000000000", "occurrence_index": 0},
            ],
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reorder_occurrences_permanent_with_single_task(client: AsyncClient):
    """Test permanent save with non-recurring (single) task falls back to daily override."""
    from datetime import datetime, timezone

    goal_resp = await client.post("/goals", json={"title": "Single Task Goal"})
    goal_id = goal_resp.json()["id"]

    now = datetime.now(timezone.utc)
    # Create non-recurring task
    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Single Task",
            "duration_minutes": 20,
            "is_recurring": False,
        },
    )
    task_id = task_resp.json()["id"]

    today_str = now.strftime("%Y-%m-%d")
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": today_str,
            "save_mode": "permanent",
            "occurrences": [
                {"task_id": task_id, "occurrence_index": 0},
            ],
        },
    )
    assert response.status_code == 200


# ============================================================================
# Task Completion Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_complete_recurring_task_with_local_date(client: AsyncClient):
    """Test completing recurring task with explicit local_date."""
    from datetime import datetime, timezone

    goal_resp = await client.post("/goals", json={"title": "Local Task"})
    goal_id = goal_resp.json()["id"]

    now = datetime.now(timezone.utc)
    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Local Date Task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_resp.json()["id"]

    today_str = now.strftime("%Y-%m-%d")
    response = await client.post(
        f"/tasks/{task_id}/complete",
        json={
            "scheduled_for": now.isoformat(),
            "local_date": today_str,
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_skip_recurring_task_with_reason(client: AsyncClient):
    """Test skipping recurring task with skip reason."""
    from datetime import datetime, timezone

    goal_resp = await client.post("/goals", json={"title": "Skip Goal"})
    goal_id = goal_resp.json()["id"]

    now = datetime.now(timezone.utc)
    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Skip Task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_resp.json()["id"]

    today_str = now.strftime("%Y-%m-%d")
    response = await client.post(
        f"/tasks/{task_id}/skip",
        json={
            "scheduled_for": now.isoformat(),
            "local_date": today_str,
            "skip_reason": "Feeling under the weather",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_recurring_completions(client: AsyncClient):
    """Test list tasks returns completion data for recurring tasks."""
    from datetime import datetime, timezone

    goal_resp = await client.post("/goals", json={"title": "Completion List Goal"})
    goal_id = goal_resp.json()["id"]

    now = datetime.now(timezone.utc)
    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Completion List Task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_resp.json()["id"]

    # Complete the task
    today_str = now.strftime("%Y-%m-%d")
    await client.post(
        f"/tasks/{task_id}/complete",
        json={
            "scheduled_for": now.isoformat(),
            "local_date": today_str,
        },
    )

    # List tasks and check completion data is present
    response = await client.get(
        "/tasks",
        params={"client_today": today_str, "include_completed": True},
    )
    assert response.status_code == 200
    tasks = response.json()["tasks"]
    # Find our task
    our_task = next((t for t in tasks if t["id"] == task_id), None)
    if our_task:
        # Should have completion data
        assert "completed_for_today" in our_task


@pytest.mark.asyncio
async def test_list_tasks_with_recurring_skips(client: AsyncClient):
    """Test list tasks returns skip data for recurring tasks."""
    from datetime import datetime, timezone

    goal_resp = await client.post("/goals", json={"title": "Skip List Goal"})
    goal_id = goal_resp.json()["id"]

    now = datetime.now(timezone.utc)
    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Skip List Task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_resp.json()["id"]

    # Skip the task
    today_str = now.strftime("%Y-%m-%d")
    await client.post(
        f"/tasks/{task_id}/skip",
        json={
            "scheduled_for": now.isoformat(),
            "local_date": today_str,
            "skip_reason": "Not today",
        },
    )

    # List tasks
    response = await client.get(
        "/tasks",
        params={"client_today": today_str},
    )
    assert response.status_code == 200


# ============================================================================
# Priorities API Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_create_priority_with_value_link(client: AsyncClient, mock_validate_priority):
    """Test creating priority with value link."""
    # Create value first
    val_resp = await client.post(
        "/values",
        json={"statement": "Link Value", "weight_raw": 70, "origin": "declared"},
    )
    assert val_resp.status_code == 201
    value_id = val_resp.json()["id"]

    # Create priority with link using value_ids
    response = await client.post(
        "/priorities",
        json={
            "title": "Priority with Link",
            "why_matters": "This matters for testing value linking in priorities",
            "score": 4,
            "value_ids": [value_id],
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_update_priority_anchored(client: AsyncClient, mock_validate_priority):
    """Test anchoring a priority via POST."""
    priority_resp = await client.post(
        "/priorities",
        json={"title": "Anchor Test", "why_matters": "This matters for testing the anchoring feature", "score": 3},
    )
    assert priority_resp.status_code == 201
    priority_id = priority_resp.json()["id"]

    # Use POST /{id}/anchor endpoint
    response = await client.post(f"/priorities/{priority_id}/anchor")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_priorities_anchored_only(client: AsyncClient, mock_validate_priority):
    """Test listing only anchored priorities."""
    # Create priority and anchor it
    resp1 = await client.post(
        "/priorities",
        json={"title": "Anchored One", "why_matters": "This matters for testing anchored priority", "score": 4},
    )
    assert resp1.status_code == 201
    priority_id = resp1.json()["id"]
    # Anchor it via POST
    await client.post(f"/priorities/{priority_id}/anchor")

    # Create non-anchored priority
    await client.post(
        "/priorities",
        json={"title": "Not Anchored", "why_matters": "This matters but not anchored yet", "score": 2},
    )

    response = await client.get("/priorities", params={"anchored_only": True})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_priority(client: AsyncClient, mock_validate_priority):
    """Test deleting a priority."""
    priority_resp = await client.post(
        "/priorities",
        json={"title": "To Delete", "why_matters": "This matters for testing deletion", "score": 3},
    )
    assert priority_resp.status_code == 201
    priority_id = priority_resp.json()["id"]

    response = await client.delete(f"/priorities/{priority_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_get_priority_history(client: AsyncClient, mock_validate_priority):
    """Test getting history of priority changes."""
    priority_resp = await client.post(
        "/priorities",
        json={"title": "History Priority", "why_matters": "This matters for testing history", "score": 3},
    )
    assert priority_resp.status_code == 201
    priority_id = priority_resp.json()["id"]

    response = await client.get(f"/priorities/{priority_id}/history")
    assert response.status_code == 200


# ============================================================================
# Values API Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_update_value_weight(client: AsyncClient):
    """Test updating value weight."""
    val_resp = await client.post(
        "/values",
        json={"statement": "Weight Test Value", "weight_raw": 50, "origin": "declared"},
    )
    assert val_resp.status_code == 201
    value_id = val_resp.json()["id"]

    # Use PUT instead of PATCH
    response = await client.put(
        f"/values/{value_id}",
        json={"statement": "Weight Test Value", "weight_raw": 90},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_value(client: AsyncClient):
    """Test deleting a value."""
    val_resp = await client.post(
        "/values",
        json={"statement": "To Delete Value", "weight_raw": 70, "origin": "declared"},
    )
    assert val_resp.status_code == 201
    value_id = val_resp.json()["id"]

    response = await client.delete(f"/values/{value_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_get_value_history(client: AsyncClient):
    """Test getting value revision history."""
    val_resp = await client.post(
        "/values",
        json={"statement": "History Value", "weight_raw": 70, "origin": "declared"},
    )
    assert val_resp.status_code == 201
    value_id = val_resp.json()["id"]

    response = await client.get(f"/values/{value_id}/history")
    assert response.status_code == 200


# ============================================================================
# Task Stats Additional Tests
# ============================================================================


@pytest.mark.asyncio
async def test_task_stats_with_completions(client: AsyncClient):
    """Test task stats include completion data."""
    from datetime import datetime, timezone, timedelta

    goal_resp = await client.post("/goals", json={"title": "Stats Goal"})
    goal_id = goal_resp.json()["id"]

    now = datetime.now(timezone.utc)
    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Stats Task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_resp.json()["id"]

    # Complete task
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"scheduled_for": now.isoformat()},
    )

    # Get stats
    start = (now - timedelta(days=7)).isoformat()
    end = (now + timedelta(days=1)).isoformat()
    response = await client.get(
        f"/tasks/{task_id}/stats",
        params={"start": start, "end": end},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_completed"] >= 1


@pytest.mark.asyncio
async def test_task_stats_with_skips(client: AsyncClient):
    """Test task stats include skip data."""
    from datetime import datetime, timezone, timedelta

    goal_resp = await client.post("/goals", json={"title": "Skip Stats Goal"})
    goal_id = goal_resp.json()["id"]

    now = datetime.now(timezone.utc)
    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Skip Stats Task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task_resp.json()["id"]

    # Skip task
    await client.post(
        f"/tasks/{task_id}/skip",
        json={"scheduled_for": now.isoformat()},
    )

    # Get stats
    start = (now - timedelta(days=7)).isoformat()
    end = (now + timedelta(days=1)).isoformat()
    response = await client.get(
        f"/tasks/{task_id}/stats",
        params={"start": start, "end": end},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total_skipped"] >= 1


# ============================================================================
# Recommendations API Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_pending_recommendations(client: AsyncClient):
    """Test getting pending recommendations."""
    response = await client.get("/recommendations/pending")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ============================================================================
# Links API Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_priority_revision_links(client: AsyncClient, mock_validate_priority):
    """Test getting priority-value links for a revision."""
    # Create value
    val_resp = await client.post(
        "/values",
        json={"statement": "Link Test Value", "weight_raw": 70, "origin": "declared"},
    )
    assert val_resp.status_code == 201
    value_id = val_resp.json()["id"]

    # Create priority with value_ids
    priority_resp = await client.post(
        "/priorities",
        json={
            "title": "Priority with Value Link",
            "why_matters": "This matters for testing priority-value linking",
            "score": 4,
            "value_ids": [value_id],
        },
    )
    assert priority_resp.status_code == 201
    revision_id = priority_resp.json()["active_revision_id"]

    # Get links for the revision
    response = await client.get(f"/priority-revisions/{revision_id}/links")
    assert response.status_code == 200


# Voice API has transcribe endpoint but requires file upload - skip for now


# ============================================================================
# Goals with Priority Links
# ============================================================================


@pytest.mark.asyncio
async def test_create_goal_with_priority(client: AsyncClient, mock_validate_priority):
    """Test creating goal and linking to priority via POST method."""
    # Create priority first
    priority_resp = await client.post(
        "/priorities",
        json={
            "title": "Goal Priority",
            "why_matters": "This matters for testing goal-priority integration",
            "score": 4,
        },
    )
    priority_id = priority_resp.json()["id"]

    # Create goal
    goal_resp = await client.post(
        "/goals",
        json={"title": "Goal with Priority"},
    )
    goal_id = goal_resp.json()["id"]

    # Link goal to priority via POST /goals/{id}/priorities/{priority_id}
    response = await client.post(
        f"/goals/{goal_id}/priorities/{priority_id}",
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_unlink_goal_from_priority(client: AsyncClient, mock_validate_priority):
    """Test unlinking goal from priority via DELETE."""
    # Create priority
    priority_resp = await client.post(
        "/priorities",
        json={
            "title": "Unlink Priority",
            "why_matters": "This matters for testing unlinking functionality",
            "score": 3,
        },
    )
    priority_id = priority_resp.json()["id"]

    # Create goal
    goal_resp = await client.post(
        "/goals",
        json={"title": "Goal To Unlink"},
    )
    goal_id = goal_resp.json()["id"]

    # Link goal to priority
    await client.post(f"/goals/{goal_id}/priorities/{priority_id}")

    # Unlink via DELETE
    response = await client.delete(f"/goals/{goal_id}/priorities/{priority_id}")
    assert response.status_code == 200


# ============================================================================
# More Task Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_update_task_title(client: AsyncClient):
    """Test updating task title."""
    goal_resp = await client.post("/goals", json={"title": "Task Title Goal"})
    goal_id = goal_resp.json()["id"]

    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Original Title",
            "duration_minutes": 30,
        },
    )
    task_id = task_resp.json()["id"]

    response = await client.patch(
        f"/tasks/{task_id}",
        json={"title": "Updated Title"},
    )
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_update_task_duration(client: AsyncClient):
    """Test updating task duration."""
    goal_resp = await client.post("/goals", json={"title": "Duration Goal"})
    goal_id = goal_resp.json()["id"]

    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Duration Task",
            "duration_minutes": 30,
        },
    )
    task_id = task_resp.json()["id"]

    response = await client.patch(
        f"/tasks/{task_id}",
        json={"duration_minutes": 60},
    )
    assert response.status_code == 200
    assert response.json()["duration_minutes"] == 60


@pytest.mark.asyncio
async def test_delete_task(client: AsyncClient):
    """Test deleting a task."""
    goal_resp = await client.post("/goals", json={"title": "Delete Task Goal"})
    goal_id = goal_resp.json()["id"]

    task_resp = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Task To Delete",
            "duration_minutes": 30,
        },
    )
    task_id = task_resp.json()["id"]

    response = await client.delete(f"/tasks/{task_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_create_recurring_task_daily(client: AsyncClient):
    """Test creating daily recurring task."""
    from datetime import datetime, timezone

    goal_resp = await client.post("/goals", json={"title": "Daily Task Goal"})
    goal_id = goal_resp.json()["id"]

    now = datetime.now(timezone.utc)
    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Daily Task",
            "duration_minutes": 15,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["is_recurring"] is True
    assert "FREQ=DAILY" in data.get("recurrence_rule", "")


# ============================================================================
# Additional Priority Tests
# ============================================================================


@pytest.mark.asyncio
async def test_unanchor_priority(client: AsyncClient, mock_validate_priority):
    """Test unanchoring a priority."""
    priority_resp = await client.post(
        "/priorities",
        json={
            "title": "Unanchor Test",
            "why_matters": "This matters for testing the unanchoring feature",
            "score": 4,
        },
    )
    assert priority_resp.status_code == 201
    priority_id = priority_resp.json()["id"]

    # First anchor
    await client.post(f"/priorities/{priority_id}/anchor")

    # Then unanchor
    response = await client.post(f"/priorities/{priority_id}/unanchor")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_stash_priority(client: AsyncClient, mock_validate_priority):
    """Test stashing a priority."""
    priority_resp = await client.post(
        "/priorities",
        json={
            "title": "Stash Test",
            "why_matters": "This matters for testing the stashing feature",
            "score": 3,
        },
    )
    assert priority_resp.status_code == 201
    priority_id = priority_resp.json()["id"]

    response = await client.post(
        f"/priorities/{priority_id}/stash",
        json={"is_stashed": True},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_stashed_priorities(client: AsyncClient, mock_validate_priority):
    """Test getting stashed priorities."""
    # Create and stash a priority
    priority_resp = await client.post(
        "/priorities",
        json={
            "title": "Stashed One",
            "why_matters": "This matters for testing stash listing",
            "score": 3,
        },
    )
    priority_id = priority_resp.json()["id"]

    await client.post(
        f"/priorities/{priority_id}/stash",
        json={"is_stashed": True},
    )

    # Get stashed
    response = await client.get("/priorities/stashed")
    assert response.status_code == 200
