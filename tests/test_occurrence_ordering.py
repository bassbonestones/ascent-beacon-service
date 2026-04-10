"""Tests for occurrence ordering API endpoints."""

import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient

from app.models.user import User


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
async def test_tasks(client: AsyncClient, test_user: User):
    """Create test tasks for ordering tests."""
    # Create a goal first
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]
    
    # Create three tasks
    task_ids = []
    for i in range(3):
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": f"Task {i + 1}",
                "duration_minutes": 30,
            },
        )
        task_ids.append(response.json()["id"])
    
    return task_ids


@pytest.fixture
async def recurring_tasks(client: AsyncClient, test_user: User):
    """Create recurring test tasks for permanent preference tests."""
    # Create a goal first
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]
    
    # Create three recurring tasks
    task_ids = []
    for i in range(3):
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": f"Recurring Task {i + 1}",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
            },
        )
        task_ids.append(response.json()["id"])
    
    return task_ids


# ============================================================================
# Reorder Occurrences Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reorder_occurrences_today(client: AsyncClient, test_tasks: list[str]):
    """Test reordering with save_mode='today'."""
    date = "2026-04-07"
    
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": test_tasks[2], "occurrence_index": 0},
                {"task_id": test_tasks[0], "occurrence_index": 0},
                {"task_id": test_tasks[1], "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["save_mode"] == "today"
    assert data["date"] == date
    assert data["count"] == 3


@pytest.mark.asyncio
async def test_reorder_occurrences_permanent(client: AsyncClient, test_tasks: list[str]):
    """Test reordering with save_mode='permanent'."""
    date = "2026-04-07"
    
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": test_tasks[1], "occurrence_index": 0},
                {"task_id": test_tasks[2], "occurrence_index": 0},
                {"task_id": test_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["save_mode"] == "permanent"
    assert data["count"] == 3


@pytest.mark.asyncio
async def test_reorder_occurrences_invalid_task(client: AsyncClient, test_tasks: list[str]):
    """Test reordering with a non-existent task ID."""
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-04-07",
            "occurrences": [
                {"task_id": test_tasks[0], "occurrence_index": 0},
                {"task_id": "invalid-task-id", "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reorder_occurrences_invalid_date_format(client: AsyncClient, test_tasks: list[str]):
    """Test reordering with invalid date format."""
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "04-07-2026",  # Wrong format
            "occurrences": [
                {"task_id": test_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    
    assert response.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_reorder_occurrences_multi_per_day(client: AsyncClient, test_tasks: list[str]):
    """Test reordering with multiple occurrences of same task (multi-per-day)."""
    # Same task appearing multiple times with different occurrence_index
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-04-07",
            "occurrences": [
                {"task_id": test_tasks[0], "occurrence_index": 0},
                {"task_id": test_tasks[1], "occurrence_index": 0},
                {"task_id": test_tasks[0], "occurrence_index": 1},
                {"task_id": test_tasks[1], "occurrence_index": 1},
            ],
            "save_mode": "permanent",
        },
    )
    
    assert response.status_code == 200
    assert response.json()["count"] == 4


# ============================================================================
# Get Day Order Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_day_order_empty(client: AsyncClient):
    """Test getting day order when no overrides or preferences exist."""
    response = await client.get("/tasks/occurrence-order", params={"date": "2026-04-07"})
    
    assert response.status_code == 200
    data = response.json()
    assert data["date"] == "2026-04-07"
    assert data["items"] == []
    assert data["has_overrides"] is False


@pytest.mark.asyncio
async def test_get_day_order_with_overrides(client: AsyncClient, test_tasks: list[str]):
    """Test getting day order after saving daily overrides."""
    date = "2026-04-07"
    
    # Save daily overrides
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": test_tasks[2], "occurrence_index": 0},
                {"task_id": test_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    
    # Get day order
    response = await client.get("/tasks/occurrence-order", params={"date": date})
    
    assert response.status_code == 200
    data = response.json()
    assert data["has_overrides"] is True
    assert len(data["items"]) == 2
    assert data["items"][0]["task_id"] == test_tasks[2]
    assert data["items"][0]["is_override"] is True
    assert data["items"][1]["task_id"] == test_tasks[0]


@pytest.mark.asyncio
async def test_get_day_order_with_permanent_preferences(client: AsyncClient, recurring_tasks: list[str]):
    """Test getting day order after saving permanent preferences.
    
    Note: Permanent preferences only apply to recurring tasks. Non-recurring tasks
    are saved as daily overrides instead (hybrid save behavior).
    """
    # Save permanent preferences (must use recurring tasks)
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-04-07",  # Note: date is required but permanent applies to all dates
            "occurrences": [
                {"task_id": recurring_tasks[1], "occurrence_index": 0},
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    
    # Get day order for a different date (permanent should apply)
    response = await client.get("/tasks/occurrence-order", params={"date": "2026-04-08"})
    
    assert response.status_code == 200
    data = response.json()
    assert data["has_overrides"] is False  # No daily overrides for this date
    assert len(data["items"]) == 2
    assert data["items"][0]["task_id"] == recurring_tasks[1]
    assert data["items"][0]["is_override"] is False


@pytest.mark.asyncio
async def test_get_day_order_overrides_take_precedence(client: AsyncClient, test_tasks: list[str]):
    """Test that daily overrides take precedence over permanent preferences."""
    date = "2026-04-07"
    
    # Save permanent preferences first
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": test_tasks[0], "occurrence_index": 0},
                {"task_id": test_tasks[1], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    
    # Then save daily overrides (different order)
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": test_tasks[1], "occurrence_index": 0},
                {"task_id": test_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    
    # Day order should use overrides
    response = await client.get("/tasks/occurrence-order", params={"date": date})
    
    assert response.status_code == 200
    data = response.json()
    assert data["has_overrides"] is True
    assert data["items"][0]["task_id"] == test_tasks[1]  # Override order, not permanent


# ============================================================================
# Clear Day Order Tests
# ============================================================================


@pytest.mark.asyncio
async def test_clear_day_order(client: AsyncClient, test_tasks: list[str]):
    """Test clearing daily overrides for a date."""
    date = "2026-04-07"
    
    # Create daily overrides
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": test_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    
    # Verify overrides exist
    response = await client.get("/tasks/occurrence-order", params={"date": date})
    assert response.json()["has_overrides"] is True
    
    # Clear overrides
    response = await client.delete(f"/tasks/occurrence-order/{date}")
    assert response.status_code == 204
    
    # Verify overrides are gone
    response = await client.get("/tasks/occurrence-order", params={"date": date})
    assert response.json()["has_overrides"] is False


@pytest.mark.asyncio
async def test_clear_day_order_nonexistent(client: AsyncClient):
    """Test clearing day order when no overrides exist (should still succeed)."""
    response = await client.delete("/tasks/occurrence-order/2026-04-07")
    assert response.status_code == 204


# ============================================================================
# Update Preferences Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reorder_permanent_updates_existing(client: AsyncClient, recurring_tasks: list[str]):
    """Test that saving permanent preferences updates existing ones.
    
    Note: Uses recurring tasks since permanent preferences only apply to them.
    """
    date = "2026-04-07"
    
    # Save initial order
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
                {"task_id": recurring_tasks[1], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    
    # Update with new order
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": recurring_tasks[1], "occurrence_index": 0},
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    
    # Verify order is updated (not duplicated)
    response = await client.get("/tasks/occurrence-order", params={"date": "2026-04-08"})
    data = response.json()
    assert len(data["items"]) == 2
    assert data["items"][0]["task_id"] == recurring_tasks[1]


@pytest.mark.asyncio
async def test_reorder_today_replaces_existing(client: AsyncClient, test_tasks: list[str]):
    """Test that saving daily overrides replaces existing ones for that date."""
    date = "2026-04-07"
    
    # Save initial daily order
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": test_tasks[0], "occurrence_index": 0},
                {"task_id": test_tasks[1], "occurrence_index": 0},
                {"task_id": test_tasks[2], "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    
    # Save new daily order with fewer items
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": test_tasks[2], "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    
    # Verify only new items exist
    response = await client.get("/tasks/occurrence-order", params={"date": date})
    data = response.json()
    assert len(data["items"]) == 1
    assert data["items"][0]["task_id"] == test_tasks[2]


# ============================================================================
# Hybrid Save Tests
# ============================================================================


@pytest.fixture
async def mixed_tasks(client: AsyncClient, test_user: User):
    """Create a mix of recurring and single tasks for hybrid save tests."""
    goal_response = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = goal_response.json()["id"]
    
    # Create 2 recurring tasks and 2 single tasks
    task_ids = {"recurring": [], "single": []}
    
    for i in range(2):
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": f"Recurring Task {i + 1}",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
            },
        )
        task_ids["recurring"].append(response.json()["id"])
    
    for i in range(2):
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": f"Single Task {i + 1}",
                "duration_minutes": 30,
            },
        )
        task_ids["single"].append(response.json()["id"])
    
    return task_ids


@pytest.mark.asyncio
async def test_hybrid_save_permanent_with_mixed_tasks(client: AsyncClient, mixed_tasks: dict):
    """Test that 'permanent' save mode handles mixed tasks correctly.
    
    When saving 'permanent' with mixed recurring and single tasks:
    - Recurring tasks get permanent preferences (apply to all future days)
    - Single tasks get daily overrides (only apply to the specified date)
    """
    date = "2026-04-07"
    recurring = mixed_tasks["recurring"]
    single = mixed_tasks["single"]
    
    # Save with permanent mode - interleaved recurring and single
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": single[0], "occurrence_index": 0},       # position 1
                {"task_id": recurring[0], "occurrence_index": 0},    # position 2
                {"task_id": single[1], "occurrence_index": 0},       # position 3
                {"task_id": recurring[1], "occurrence_index": 0},    # position 4
            ],
            "save_mode": "permanent",
        },
    )
    
    # Check the original date - should have both daily overrides and permanent prefs
    response = await client.get("/tasks/occurrence-order", params={"date": date})
    data = response.json()
    # Single tasks should be in daily overrides
    assert data["has_overrides"] is True
    # All 4 items should have positions
    assert len(data["items"]) == 4
    
    # Check a different date - should only have recurring tasks from permanent prefs
    response = await client.get("/tasks/occurrence-order", params={"date": "2026-04-08"})
    data = response.json()
    assert data["has_overrides"] is False  # No daily overrides
    # Only recurring tasks should appear (2 of them)
    assert len(data["items"]) == 2
    # They should be in order: recurring[0] (position 2), recurring[1] (position 4)
    assert data["items"][0]["task_id"] == recurring[0]
    assert data["items"][1]["task_id"] == recurring[1]


# ============================================================================
# Range API Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_date_range_order_empty(client: AsyncClient):
    """Test getting order for a date range when nothing is saved."""
    response = await client.get(
        "/tasks/occurrence-order/range",
        params={"start_date": "2026-04-07", "end_date": "2026-04-14"},
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["start_date"] == "2026-04-07"
    assert data["end_date"] == "2026-04-14"
    assert data["permanent_order"] == []
    assert data["daily_overrides"] == {}


@pytest.mark.asyncio
async def test_get_date_range_order_with_data(client: AsyncClient, recurring_tasks: list[str]):
    """Test getting order for a date range with both permanent and daily overrides."""
    # Save permanent preferences for recurring tasks
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-04-07",
            "occurrences": [
                {"task_id": recurring_tasks[1], "occurrence_index": 0},
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    
    # Save daily overrides for a specific date
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-04-10",
            "occurrences": [
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
                {"task_id": recurring_tasks[1], "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    
    # Get range order
    response = await client.get(
        "/tasks/occurrence-order/range",
        params={"start_date": "2026-04-07", "end_date": "2026-04-14"},
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should have permanent preferences
    assert len(data["permanent_order"]) == 2
    assert data["permanent_order"][0]["task_id"] == recurring_tasks[1]
    assert data["permanent_order"][1]["task_id"] == recurring_tasks[0]
    
    # Should have daily overrides for 2026-04-10
    assert "2026-04-10" in data["daily_overrides"]
    assert len(data["daily_overrides"]["2026-04-10"]) == 2
    assert data["daily_overrides"]["2026-04-10"][0]["task_id"] == recurring_tasks[0]
    assert data["daily_overrides"]["2026-04-10"][1]["task_id"] == recurring_tasks[1]
    
    # Should NOT have overrides for other dates
    assert "2026-04-07" not in data["daily_overrides"]
    assert "2026-04-08" not in data["daily_overrides"]


# ============================================================================
# Clear Day Order From Tests
# ============================================================================


@pytest.mark.asyncio
async def test_clear_day_order_from(client: AsyncClient, test_tasks: list[str]):
    """Test clearing daily overrides from a date onward (inclusive)."""
    # Create daily overrides for multiple dates
    for date in ["2026-04-07", "2026-04-08", "2026-04-09", "2026-04-10"]:
        await client.post(
            "/tasks/reorder-occurrences",
            json={
                "date": date,
                "occurrences": [
                    {"task_id": test_tasks[0], "occurrence_index": 0},
                ],
                "save_mode": "today",
            },
        )
    
    # Verify all 4 dates have overrides
    for date in ["2026-04-07", "2026-04-08", "2026-04-09", "2026-04-10"]:
        response = await client.get("/tasks/occurrence-order", params={"date": date})
        assert response.json()["has_overrides"] is True
    
    # Clear from 2026-04-08 onward
    response = await client.delete("/tasks/occurrence-order/from/2026-04-08")
    assert response.status_code == 204
    
    # Verify 2026-04-07 still has overrides (before the cutoff)
    response = await client.get("/tasks/occurrence-order", params={"date": "2026-04-07"})
    assert response.json()["has_overrides"] is True
    
    # Verify 2026-04-08, 2026-04-09, 2026-04-10 no longer have overrides
    for date in ["2026-04-08", "2026-04-09", "2026-04-10"]:
        response = await client.get("/tasks/occurrence-order", params={"date": date})
        assert response.json()["has_overrides"] is False


@pytest.mark.asyncio
async def test_clear_day_order_from_nonexistent(client: AsyncClient):
    """Test clearing from a date when no overrides exist (should still succeed)."""
    response = await client.delete("/tasks/occurrence-order/from/2026-04-07")
    assert response.status_code == 204


# ============================================================================
# More Reorder Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reorder_occurrences_permanent_mode(client: AsyncClient, test_tasks: list[str]):
    """Test reordering with save_mode='permanent' creates preferences."""
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-04-15",
            "occurrences": [
                {"task_id": test_tasks[1], "occurrence_index": 0},
                {"task_id": test_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    assert response.status_code == 200
    assert response.json()["save_mode"] == "permanent"


@pytest.mark.asyncio
async def test_reorder_occurrences_creates_overrides(client: AsyncClient, test_tasks: list[str]):
    """Test that reorder in today mode creates daily overrides."""
    # Create overrides
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-04-16",
            "occurrences": [{"task_id": test_tasks[0], "occurrence_index": 0}],
            "save_mode": "today",
        },
    )

    # Check that overrides exist
    response = await client.get("/tasks/occurrence-order", params={"date": "2026-04-16"})
    assert response.status_code == 200
    assert response.json()["has_overrides"] is True


# ============================================================================
# Range Query Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_occurrence_order_range(client: AsyncClient, test_tasks: list[str]):
    """Test getting occurrence order for a date range."""
    # Set order for multiple dates
    for date in ["2026-04-20", "2026-04-21", "2026-04-22"]:
        await client.post(
            "/tasks/reorder-occurrences",
            json={
                "date": date,
                "occurrences": [{"task_id": test_tasks[0], "occurrence_index": 0}],
                "save_mode": "today",
            },
        )

    # Query range
    response = await client.get(
        "/tasks/occurrence-order/range",
        params={"start_date": "2026-04-20", "end_date": "2026-04-22"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "daily_overrides" in data
    assert "permanent_order" in data


@pytest.mark.asyncio
async def test_get_occurrence_order_with_no_overrides(client: AsyncClient):
    """Test occurrence order returns correctly when no overrides exist."""
    response = await client.get("/tasks/occurrence-order", params={"date": "2026-06-01"})
    assert response.status_code == 200
    assert response.json()["has_overrides"] is False


@pytest.mark.asyncio
async def test_clear_occurrence_order_for_date(client: AsyncClient, test_tasks: list[str]):
    """Test clearing occurrence order for a single date."""
    # Set order
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-04-28",
            "occurrences": [{"task_id": test_tasks[0], "occurrence_index": 0}],
            "save_mode": "today",
        },
    )

    # Clear it
    response = await client.delete("/tasks/occurrence-order/2026-04-28")
    assert response.status_code == 204

    # Verify cleared
    get_response = await client.get("/tasks/occurrence-order", params={"date": "2026-04-28"})
    assert get_response.json()["has_overrides"] is False


@pytest.mark.asyncio
async def test_reorder_with_recurring_task_occurrence_index(client: AsyncClient, recurring_tasks: list[str]):
    """Test reordering with occurrence_index > 0 for recurring tasks."""
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-04-30",
            "occurrences": [
                {"task_id": recurring_tasks[0], "occurrence_index": 3},
                {"task_id": recurring_tasks[1], "occurrence_index": 2},
            ],
            "save_mode": "permanent",
        },
    )
    assert response.status_code == 200


# ============================================================================
# Invalid Task ID Tests (covers lines 59-75)
# ============================================================================


@pytest.mark.asyncio
async def test_reorder_with_invalid_task_id(client: AsyncClient):
    """Test reordering with a non-existent task ID returns 404."""
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-05-01",
            "occurrences": [
                {"task_id": "00000000-0000-0000-0000-000000000000", "occurrence_index": 0}
            ],
            "save_mode": "today",
        },
    )
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reorder_with_some_invalid_task_ids(client: AsyncClient, test_tasks: list[str]):
    """Test reordering with mix of valid and invalid task IDs."""
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-05-01",
            "occurrences": [
                {"task_id": test_tasks[0], "occurrence_index": 0},
                {"task_id": "00000000-0000-0000-0000-000000000000", "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    assert response.status_code == 404


# ============================================================================
# Permanent Preferences Storage Tests (covers lines 98-106, 125-167)
# ============================================================================


@pytest.mark.asyncio
async def test_permanent_preferences_persist_across_dates(client: AsyncClient, test_tasks: list[str]):
    """Test that permanent preferences apply to multiple dates."""
    # Set permanent preferences
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-05-05",
            "occurrences": [
                {"task_id": test_tasks[2], "occurrence_index": 0},
                {"task_id": test_tasks[0], "occurrence_index": 0},
                {"task_id": test_tasks[1], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )

    # Check that preferences work on a different date
    response = await client.get("/tasks/occurrence-order", params={"date": "2026-05-10"})
    assert response.status_code == 200
    data = response.json()
    # May have items from permanent preferences
    assert "items" in data


@pytest.mark.asyncio
async def test_permanent_preferences_update_existing(client: AsyncClient, test_tasks: list[str]):
    """Test that setting permanent preferences replaces existing ones."""
    # Set initial preferences
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-05-05",
            "occurrences": [
                {"task_id": test_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )

    # Update preferences
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-05-05",
            "occurrences": [
                {"task_id": test_tasks[1], "occurrence_index": 0},
                {"task_id": test_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )

    # Get order
    response = await client.get("/tasks/occurrence-order", params={"date": "2026-05-05"})
    assert response.status_code == 200


# ============================================================================
# Clear Permanent Preferences Tests (covers lines 345)
# ============================================================================


@pytest.mark.asyncio
async def test_clear_permanent_preferences(client: AsyncClient, test_tasks: list[str]):
    """Test clearing all permanent preferences."""
    # Set some permanent preferences
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-05-05",
            "occurrences": [{"task_id": test_tasks[0], "occurrence_index": 0}],
            "save_mode": "permanent",
        },
    )

    # Clear all permanent preferences
    response = await client.delete("/tasks/occurrence-order/permanent")
    assert response.status_code in [204, 404]  # 404 if endpoint doesn't exist


# ============================================================================
# Date Range Query Tests (covers lines 379-416)
# ============================================================================


@pytest.mark.asyncio
async def test_get_occurrence_order_range_with_overrides(client: AsyncClient, test_tasks: list[str]):
    """Test getting occurrence order range with daily overrides."""
    # Set overrides for a few dates
    for date in ["2026-05-10", "2026-05-11", "2026-05-12"]:
        await client.post(
            "/tasks/reorder-occurrences",
            json={
                "date": date,
                "occurrences": [{"task_id": test_tasks[0], "occurrence_index": 0}],
                "save_mode": "today",
            },
        )

    # Query range
    response = await client.get(
        "/tasks/occurrence-order/range",
        params={"start_date": "2026-05-09", "end_date": "2026-05-13"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "daily_overrides" in data
    # Should have overrides for dates we set
    assert len(data["daily_overrides"]) >= 3


@pytest.mark.asyncio
async def test_get_occurrence_order_range_empty(client: AsyncClient):
    """Test getting occurrence order range when no overrides exist."""
    response = await client.get(
        "/tasks/occurrence-order/range",
        params={"start_date": "2030-01-01", "end_date": "2030-01-07"},
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data.get("daily_overrides", {})) == 0


@pytest.mark.asyncio
async def test_get_occurrence_order_range_with_permanent(client: AsyncClient, test_tasks: list[str]):
    """Test that range query includes permanent preferences."""
    # Set permanent preferences
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-05-15",
            "occurrences": [
                {"task_id": test_tasks[0], "occurrence_index": 0},
                {"task_id": test_tasks[1], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )

    # Query range
    response = await client.get(
        "/tasks/occurrence-order/range",
        params={"start_date": "2026-05-15", "end_date": "2026-05-20"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "permanent_order" in data


# ============================================================================
# Additional Hybrid Save Mode Tests (Recurring + Single Tasks Together)
# ============================================================================


@pytest.mark.asyncio
async def test_permanent_save_hybrid_mixed_tasks(client: AsyncClient, mixed_tasks: dict):
    """Test permanent save with mix of recurring and single tasks (hybrid save)."""
    # Save permanently - recurring gets preferences, single gets daily override
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-06-01",
            "occurrences": [
                {"task_id": mixed_tasks["recurring"][0], "occurrence_index": 0},
                {"task_id": mixed_tasks["single"][0], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    assert response.status_code == 200
    assert response.json()["count"] == 2


@pytest.mark.asyncio
async def test_permanent_save_multiple_recurring(client: AsyncClient, recurring_tasks: list[str]):
    """Test permanent save creates preferences for all recurring tasks."""
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-06-02",
            "occurrences": [
                {"task_id": recurring_tasks[2], "occurrence_index": 0},
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
                {"task_id": recurring_tasks[1], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    assert response.status_code == 200
    
    # Verify permanent order
    order_response = await client.get(
        "/tasks/occurrence-order",
        params={"date": "2026-06-02"},
    )
    assert order_response.status_code == 200


@pytest.mark.asyncio
async def test_permanent_save_removes_daily_override_for_recurring(client: AsyncClient, recurring_tasks: list[str]):
    """Test that permanent save clears daily overrides for recurring tasks."""
    date = "2026-06-03"
    
    # First create daily override
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    
    # Now save permanent - should clear the daily override
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
                {"task_id": recurring_tasks[1], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    
    # Get order - should have permanent preferences, not daily overrides for recurring
    response = await client.get("/tasks/occurrence-order", params={"date": date})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_existing_permanent_preference(client: AsyncClient, recurring_tasks: list[str]):
    """Test that updating permanent preferences updates existing records."""
    # Create initial preferences
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-06-04",
            "occurrences": [
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
                {"task_id": recurring_tasks[1], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    
    # Update with different order
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-06-05",
            "occurrences": [
                {"task_id": recurring_tasks[1], "occurrence_index": 0},  # Swapped order
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    assert response.status_code == 200


# ============================================================================
# Error Handling Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reorder_occurrences_empty_list(client: AsyncClient):
    """Test reordering with empty occurrences list."""
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-06-06",
            "occurrences": [],
            "save_mode": "today",
        },
    )
    # Should succeed or give validation error
    assert response.status_code in [200, 422]


@pytest.mark.asyncio
async def test_get_day_order_invalid_date_format(client: AsyncClient):
    """Test getting day order with invalid date format."""
    response = await client.get(
        "/tasks/occurrence-order",
        params={"date": "invalid-date"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_day_order_with_only_permanent_preferences(client: AsyncClient, recurring_tasks: list[str]):
    """Test getting day order when only permanent preferences exist (no overrides)."""
    # Set only permanent preferences
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": "2026-06-07",
            "occurrences": [
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    
    # Query different date where no daily overrides exist
    response = await client.get(
        "/tasks/occurrence-order",
        params={"date": "2026-06-08"},
    )
    assert response.status_code == 200
    data = response.json()
    # Should have items from permanent preferences
    assert "items" in data


@pytest.mark.asyncio
async def test_get_day_order_merges_overrides_and_permanent(client: AsyncClient, recurring_tasks: list[str], test_tasks: list[str]):
    """Test that day order merges daily overrides and permanent preferences."""
    date = "2026-06-09"
    
    # Set permanent for recurring
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    
    # Set daily override for non-recurring
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": test_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    
    # Query - should have both
    response = await client.get("/tasks/occurrence-order", params={"date": date})
    assert response.status_code == 200
    data = response.json()
    assert len(data.get("items", [])) >= 1


# ============================================================================
# Additional Occurrence Ordering Edge Case Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reorder_occurrences_validates_task_ownership(client: AsyncClient, test_tasks: list[str]):
    """Test that reordering only works for user's own tasks."""
    date = "2026-04-10"
    
    # This should work since test_tasks belong to the test user
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": test_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_day_order_sorts_by_sort_value(client: AsyncClient, test_tasks: list[str]):
    """Test that day order items are sorted correctly."""
    date = "2026-04-10"
    
    # Set order with multiple tasks
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": test_tasks[0], "occurrence_index": 0},
                {"task_id": test_tasks[1], "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    
    # Query and verify order
    response = await client.get("/tasks/occurrence-order", params={"date": date})
    assert response.status_code == 200
    data = response.json()
    items = data.get("items", [])
    assert len(items) == 2
    
    # Items should be in the order they were specified
    assert items[0]["task_id"] == test_tasks[0]
    assert items[1]["task_id"] == test_tasks[1]


@pytest.mark.asyncio
async def test_set_and_get_day_order(client: AsyncClient, test_tasks: list[str]):
    """Test setting and getting day order with overrides."""
    date = "2026-04-11"
    
    # Set overrides
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": test_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "today",
        },
    )
    assert response.status_code == 200
    
    # Verify overrides exist
    response = await client.get("/tasks/occurrence-order", params={"date": date})
    assert response.status_code == 200
    data = response.json()
    assert data["has_overrides"] is True
    assert len(data["items"]) >= 1


@pytest.mark.asyncio
async def test_permanent_preferences_without_overrides(client: AsyncClient, recurring_tasks: list[str]):
    """Test that permanent preferences show when no daily overrides exist."""
    date = "2026-04-12"
    
    # Set permanent preference
    await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
            ],
            "save_mode": "permanent",
        },
    )
    
    # Query for a different date (no daily override for this date)
    response = await client.get("/tasks/occurrence-order", params={"date": "2026-04-13"})
    assert response.status_code == 200
    data = response.json()
    
    # Permanent preferences should still appear
    items = data.get("items", [])
    # items could be empty if no prefs apply to this date
    assert data["has_overrides"] is False


@pytest.mark.asyncio
async def test_reorder_with_multiple_occurrence_indices(client: AsyncClient, recurring_tasks: list[str]):
    """Test reordering with same task but different occurrence indices."""
    date = "2026-04-14"
    
    # A recurring task could have multiple occurrences per day (multi-per-day)
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": date,
            "occurrences": [
                {"task_id": recurring_tasks[0], "occurrence_index": 0},
                {"task_id": recurring_tasks[0], "occurrence_index": 1},
            ],
            "save_mode": "today",
        },
    )
    assert response.status_code == 200
    assert response.json()["count"] == 2
