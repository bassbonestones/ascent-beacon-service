# ---- migrated from tests/api/test_tasks.py (strict canonical cleanup) ----

# ---- migrated from tests/integration/test_api_helpers_tasks_stats_views.py ----

"""Integration coverage for tasks, stats, and view helper behavior."""

import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_completion import TaskCompletion


@pytest.mark.asyncio
async def test_task_with_completion_tracking(client: AsyncClient):
    """Test task operations that trigger completion tracking."""
    goal = await client.post("/goals", json={"title": "Completion Track Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Track Task",
            "duration_minutes": 15,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task.json()["id"]

    today_str = now.strftime("%Y-%m-%d")
    await client.post(f"/tasks/{task_id}/complete", json={"occurrence_date": today_str})

    response = await client.get(f"/tasks/{task_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_task_delete(client: AsyncClient):
    """Test deleting a task."""
    goal = await client.post("/goals", json={"title": "Delete Goal"})
    goal_id = goal.json()["id"]

    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Delete Task", "duration_minutes": 30},
    )
    task_id = task.json()["id"]

    response = await client.delete(f"/tasks/{task_id}")
    assert response.status_code == 204

    get_resp = await client.get(f"/tasks/{task_id}")
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_filtered_tasks_view(client: AsyncClient):
    """Test filtered tasks view."""
    goal = await client.post("/goals", json={"title": "View Filter Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)

    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "View Task 1",
            "duration_minutes": 30,
            "scheduled_at": now.isoformat(),
        },
    )
    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "View Task 2",
            "duration_minutes": 60,
            "scheduled_at": (now + timedelta(hours=1)).isoformat(),
        },
    )

    response = await client.post(
        "/tasks/view/range",
        json={
            "start_date": now.isoformat(),
            "end_date": (now + timedelta(days=1)).isoformat(),
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_task_stats_for_daily_task(client: AsyncClient):
    """Test stats for a daily recurring task over a week."""
    goal = await client.post("/goals", json={"title": "Daily Stats Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Daily Task Stats",
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
async def test_task_history_for_daily_task(client: AsyncClient):
    """Test history for a daily recurring task."""
    goal = await client.post("/goals", json={"title": "History Daily Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Daily History Task",
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


# ---- migrated from tests/integration/test_tasks_listing_and_update_flows.py ----

"""Integration flows for task listing filters and task update behavior."""

import pytest
from httpx import AsyncClient
from datetime import datetime, timezone, timedelta


# ============================================================================
# Recurring Tasks with Completions - List Tasks Endpoint
# ============================================================================


@pytest.mark.asyncio
async def test_list_tasks_with_recurring_completions(client: AsyncClient):
    """Test listing tasks when recurring tasks have completions."""
    goal = await client.post("/goals", json={"title": "Recurring List Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    
    # Create a recurring task
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Daily Recurring List Task",
            "duration_minutes": 15,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task.json()["id"]

    # Complete the task for today
    await client.post(
        f"/tasks/{task_id}/complete",
        json={"occurrence_date": today_str},
    )

    # List tasks - this should trigger the completions tracking code path
    response = await client.get("/tasks")
    assert response.status_code == 200
    data = response.json()
    assert "tasks" in data
    
    # Find our task (verify it's in the list)
    task_ids = [task["id"] for task in data["tasks"]]
    assert task_id in task_ids
    found_task = next(t for t in data["tasks"] if t["id"] == task_id)
    assert found_task["completed_for_today"] is True
    assert found_task["completions_today"] >= 1


@pytest.mark.asyncio
async def test_list_tasks_with_recurring_skips(client: AsyncClient):
    """Test listing tasks when recurring tasks have skips."""
    goal = await client.post("/goals", json={"title": "Skip List Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Daily Skip List Task",
            "duration_minutes": 15,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task.json()["id"]

    # Skip the task for today
    await client.post(
        f"/tasks/{task_id}/skip",
        json={"occurrence_date": today_str, "skip_reason": "Test skip"},
    )

    # List tasks
    response = await client.get("/tasks")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_date_filters(client: AsyncClient):
    """Test listing tasks with scheduled_after and scheduled_before."""
    goal = await client.post("/goals", json={"title": "Filter Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)
    
    # Create task
    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Filter Task",
            "duration_minutes": 30,
            "scheduled_at": now.isoformat(),
        },
    )

    # List with date filters
    yesterday = (now - timedelta(days=1)).isoformat()
    tomorrow = (now + timedelta(days=1)).isoformat()
    
    response = await client.get(
        "/tasks",
        params={
            "scheduled_after": yesterday,
            "scheduled_before": tomorrow,
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_invalid_date_filters(client: AsyncClient):
    """Test listing tasks with invalid date formats."""
    response = await client.get(
        "/tasks",
        params={
            "scheduled_after": "not-a-date",
            "scheduled_before": "also-not-a-date",
        },
    )
    # Should still work, just ignore invalid dates
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_by_goal(client: AsyncClient):
    """Test listing tasks filtered by goal."""
    goal1 = await client.post("/goals", json={"title": "Goal A"})
    goal1_id = goal1.json()["id"]
    
    goal2 = await client.post("/goals", json={"title": "Goal B"})
    goal2_id = goal2.json()["id"]

    # Create tasks for both goals
    await client.post(
        "/tasks",
        json={"goal_id": goal1_id, "title": "Task A", "duration_minutes": 30},
    )
    await client.post(
        "/tasks",
        json={"goal_id": goal2_id, "title": "Task B", "duration_minutes": 30},
    )

    # List tasks for goal1 only
    response = await client.get("/tasks", params={"goal_id": goal1_id})
    assert response.status_code == 200
    data = response.json()
    assert all(t["goal_id"] == goal1_id for t in data["tasks"])


@pytest.mark.asyncio
async def test_list_tasks_with_days_ahead_param(client: AsyncClient):
    """Test listing tasks with days_ahead parameter."""
    goal = await client.post("/goals", json={"title": "Days Ahead Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)
    
    # Create task scheduled for next week
    await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Future Task",
            "duration_minutes": 30,
            "scheduled_at": (now + timedelta(days=7)).isoformat(),
        },
    )

    # List with days_ahead=14 (should include the task)
    response = await client.get("/tasks", params={"days_ahead": 14})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_tasks_with_invalid_client_today_falls_back_to_utc(client: AsyncClient):
    """Invalid client_today should not fail listing."""
    goal = await client.post("/goals", json={"title": "Client Today Goal"})
    goal_id = goal.json()["id"]
    await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Fallback Task", "duration_minutes": 20},
    )

    response = await client.get("/tasks", params={"client_today": "2026-99-99"})
    assert response.status_code == 200
    assert isinstance(response.json()["tasks"], list)


@pytest.mark.asyncio
async def test_list_tasks_status_pending_filter(client: AsyncClient):
    """status=pending should include pending tasks and exclude completed ones."""
    goal = await client.post("/goals", json={"title": "Pending Filter Goal"})
    goal_id = goal.json()["id"]

    pending_task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Pending task"},
    )
    completed_task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Completed task"},
    )
    await client.post(f"/tasks/{completed_task.json()['id']}/complete", json={})

    response = await client.get("/tasks", params={"status": "pending"})
    assert response.status_code == 200
    ids = [t["id"] for t in response.json()["tasks"]]
    assert pending_task.json()["id"] in ids
    assert completed_task.json()["id"] not in ids


@pytest.mark.asyncio
async def test_list_tasks_status_completed_includes_completed_variants(client: AsyncClient):
    """status=completed includes one-time completed and recurring completed-in-range."""
    goal = await client.post("/goals", json={"title": "Completed Filter Goal"})
    goal_id = goal.json()["id"]
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    one_time = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "One-time done", "duration_minutes": 15},
    )
    one_time_id = one_time.json()["id"]
    await client.post(f"/tasks/{one_time_id}/complete", json={})

    recurring = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurring done",
            "duration_minutes": 15,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    recurring_id = recurring.json()["id"]
    await client.post(
        f"/tasks/{recurring_id}/complete",
        json={"scheduled_for": now.isoformat(), "local_date": today},
    )

    response = await client.get(
        "/tasks",
        params={"status": "completed", "client_today": today, "days_ahead": 14},
    )
    assert response.status_code == 200
    ids = {t["id"] for t in response.json()["tasks"]}
    assert one_time_id in ids
    assert recurring_id in ids


@pytest.mark.asyncio
async def test_list_tasks_status_filter_for_skipped(client: AsyncClient):
    """status=skipped should return skipped one-time tasks."""
    goal = await client.post("/goals", json={"title": "Skipped Filter Goal"})
    goal_id = goal.json()["id"]
    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Skip me", "duration_minutes": 15},
    )
    task_id = task.json()["id"]
    await client.post(f"/tasks/{task_id}/skip", json={"reason": "busy"})

    response = await client.get("/tasks", params={"status": "skipped"})
    assert response.status_code == 200
    ids = [t["id"] for t in response.json()["tasks"]]
    assert task_id in ids


@pytest.mark.asyncio
async def test_list_tasks_include_paused_and_archived_states(client: AsyncClient):
    """State filters should include paused and archived tasks when requested."""
    goal = await client.post("/goals", json={"title": "State Goal"})
    goal_id = goal.json()["id"]

    paused_task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Pause candidate"},
    )
    paused_task_id = paused_task.json()["id"]
    await client.post(f"/tasks/{paused_task_id}/pause")

    archive_goal = await client.post("/goals", json={"title": "Archive goal"})
    archive_goal_id = archive_goal.json()["id"]
    archived_task = await client.post(
        "/tasks",
        json={"goal_id": archive_goal_id, "title": "Archive candidate"},
    )
    archived_task_id = archived_task.json()["id"]
    await client.post(
        f"/goals/{archive_goal_id}/archive",
        json={
            "tracking_mode": "failed",
            "task_resolutions": [{"task_id": archived_task_id, "action": "archive_task"}],
        },
    )

    default_list = await client.get("/tasks")
    assert paused_task_id not in [t["id"] for t in default_list.json()["tasks"]]
    assert archived_task_id not in [t["id"] for t in default_list.json()["tasks"]]

    paused_list = await client.get("/tasks", params={"include_paused": "true"})
    assert paused_task_id in [t["id"] for t in paused_list.json()["tasks"]]

    archived_list = await client.get("/tasks", params={"include_archived": "true"})
    assert archived_task_id in [t["id"] for t in archived_list.json()["tasks"]]


@pytest.mark.asyncio
async def test_list_tasks_task_record_state_archived_only(client: AsyncClient) -> None:
    """task_record_state=archived returns only archived tasks."""
    goal = await client.post("/goals", json={"title": "Arch browse goal"})
    goal_id = goal.json()["id"]

    active_task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Still active"},
    )
    active_id = active_task.json()["id"]

    archive_goal = await client.post("/goals", json={"title": "To archive"})
    ag_id = archive_goal.json()["id"]
    archived_task = await client.post(
        "/tasks",
        json={"goal_id": ag_id, "title": "Will archive"},
    )
    archived_id = archived_task.json()["id"]
    await client.post(
        f"/goals/{ag_id}/archive",
        json={
            "tracking_mode": "failed",
            "task_resolutions": [{"task_id": archived_id, "action": "archive_task"}],
        },
    )

    bad = await client.get("/tasks", params={"task_record_state": "paused"})
    assert bad.status_code == 400

    only_archived = await client.get(
        "/tasks",
        params={"task_record_state": "archived", "client_today": "2026-04-13"},
    )
    assert only_archived.status_code == 200
    ids = {t["id"] for t in only_archived.json()["tasks"]}
    assert archived_id in ids
    assert active_id not in ids
    for t in only_archived.json()["tasks"]:
        assert t["record_state"] == "archived"


@pytest.mark.asyncio
async def test_list_tasks_handles_legacy_completion_rows(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Legacy completion rows without scheduled_for/local_date should still be parsed."""
    goal = await client.post("/goals", json={"title": "Legacy Completion Goal"})
    goal_id = goal.json()["id"]
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    recurring = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Legacy recurring",
            "duration_minutes": 10,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    recurring_id = recurring.json()["id"]

    db_session.add(
        TaskCompletion(
            task_id=recurring_id,
            status="completed",
            completed_at=now,
            scheduled_for=None,
            local_date=None,
        )
    )
    db_session.add(
        TaskCompletion(
            task_id=recurring_id,
            status="skipped",
            completed_at=now,
            scheduled_for=None,
            local_date=None,
            skip_reason="legacy",
        )
    )
    await db_session.commit()

    response = await client.get(
        "/tasks",
        params={"client_today": today, "days_ahead": 3},
    )
    assert response.status_code == 200
    task = next(t for t in response.json()["tasks"] if t["id"] == recurring_id)
    assert task["completions_today"] >= 1
    assert task["skips_today"] >= 1


@pytest.mark.asyncio
async def test_list_tasks_handles_sparse_completion_rows_with_local_date_only(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Completion rows with local_date only should still be indexed for the day."""
    goal = await client.post("/goals", json={"title": "Sparse Completion Goal"})
    goal_id = goal.json()["id"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    recurring = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Sparse recurring",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    recurring_id = recurring.json()["id"]

    db_session.add(
        TaskCompletion(
            task_id=recurring_id,
            status="completed",
            local_date=today,
            scheduled_for=None,
            completed_at=None,
        )
    )
    await db_session.commit()

    response = await client.get("/tasks", params={"client_today": today, "days_ahead": 1})
    assert response.status_code == 200
    task = next(t for t in response.json()["tasks"] if t["id"] == recurring_id)
    assert task["completions_today"] >= 1
    assert today in task["completions_by_date"]


# ============================================================================
# Task Update Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_task_update_change_goal(client: AsyncClient):
    """Test moving a task to a different goal."""
    goal1 = await client.post("/goals", json={"title": "Original Goal"})
    goal1_id = goal1.json()["id"]
    
    goal2 = await client.post("/goals", json={"title": "New Goal"})
    goal2_id = goal2.json()["id"]

    task = await client.post(
        "/tasks",
        json={"goal_id": goal1_id, "title": "Move Task", "duration_minutes": 30},
    )
    task_id = task.json()["id"]

    # Move task to goal2
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"goal_id": goal2_id},
    )
    assert response.status_code == 200
    assert response.json()["goal_id"] == goal2_id


@pytest.mark.asyncio
async def test_task_update_duration(client: AsyncClient):
    """Test updating task duration."""
    goal = await client.post("/goals", json={"title": "Duration Goal"})
    goal_id = goal.json()["id"]

    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Duration Task", "duration_minutes": 30},
    )
    task_id = task.json()["id"]

    response = await client.patch(
        f"/tasks/{task_id}",
        json={"duration_minutes": 60},
    )
    assert response.status_code == 200
    assert response.json()["duration_minutes"] == 60


@pytest.mark.asyncio
async def test_task_update_scheduled_at(client: AsyncClient):
    """Test updating task schedule."""
    goal = await client.post("/goals", json={"title": "Schedule Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Schedule Task",
            "duration_minutes": 30,
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task.json()["id"]

    new_time = (now + timedelta(hours=2)).isoformat()
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"scheduled_at": new_time},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_task_update_recurrence(client: AsyncClient):
    """Test updating task recurrence settings."""
    goal = await client.post("/goals", json={"title": "Recurrence Update Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Recurrence Task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task.json()["id"]

    # Change recurrence to weekly
    response = await client.patch(
        f"/tasks/{task_id}",
        json={"recurrence_rule": "FREQ=WEEKLY"},
    )
    assert response.status_code == 200


# ============================================================================
# Task Complete with Occurrence Index
# ============================================================================


@pytest.mark.asyncio
async def test_task_complete_with_occurrence_index(client: AsyncClient):
    """Test completing a specific occurrence of a recurring task."""
    goal = await client.post("/goals", json={"title": "Occurrence Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Multi-occurrence Task",
            "duration_minutes": 15,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY;COUNT=3",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    task_id = task.json()["id"]

    # Complete first occurrence
    response = await client.post(
        f"/tasks/{task_id}/complete",
        json={"occurrence_index": 0},
    )
    assert response.status_code == 200


# ============================================================================
# Values with Different Origins
# ============================================================================


@pytest.mark.asyncio
async def test_value_list_with_different_origins(client: AsyncClient):
    """Test listing values with different origins."""
    # Create values with different origins
    await client.post(
        "/values",
        json={"statement": "Declared Value", "weight_raw": 80, "origin": "declared"},
    )
    await client.post(
        "/values",
        json={"statement": "Suggested Value", "weight_raw": 60, "origin": "suggested"},
    )
    await client.post(
        "/values",
        json={"statement": "Inferred Value", "weight_raw": 40, "origin": "inferred"},
    )

    # List all values
    response = await client.get("/values")
    assert response.status_code == 200
    data = response.json()
    # Response is wrapped: {"values": [...]}
    values = data.get("values", data)
    assert len(values) >= 3


@pytest.mark.asyncio
async def test_value_history(client: AsyncClient):
    """Test getting value revision history."""
    val = await client.post(
        "/values",
        json={"statement": "History Value", "weight_raw": 50, "origin": "declared"},
    )
    val_id = val.json()["id"]

    # Create additional revision
    await client.post(
        f"/values/{val_id}/revisions",
        json={"statement": "Updated History Value", "weight_raw": 60},
    )

    # Get history
    response = await client.get(f"/values/{val_id}/history")
    assert response.status_code == 200
    history = response.json()
    assert len(history) >= 2


# ============================================================================
# Priority Operations
# ============================================================================


@pytest.mark.asyncio
async def test_priority_history(client: AsyncClient, mock_validate_priority):
    """Test getting priority revision history."""
    priority = await client.post(
        "/priorities",
        json={
            "title": "History Priority",
            "why_matters": "Testing revision history tracking",
            "score": 3,
        },
    )
    p_id = priority.json()["id"]

    # Create revision
    await client.post(
        f"/priorities/{p_id}/revisions",
        json={
            "title": "Updated History Priority",
            "why_matters": "Updated revision for history test",
            "score": 4,
        },
    )

    # Get history
    response = await client.get(f"/priorities/{p_id}/history")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_priorities_anchored_filter(client: AsyncClient, mock_validate_priority):
    """Test listing only anchored priorities."""
    # Create value for linking
    val = await client.post(
        "/values",
        json={"statement": "Filter Test Value", "weight_raw": 70, "origin": "declared"},
    )
    val_id = val.json()["id"]

    # Create and anchor a priority
    priority = await client.post(
        "/priorities",
        json={
            "title": "Anchored Priority",
            "why_matters": "Testing anchored filter",
            "score": 4,
            "value_ids": [val_id],
        },
    )
    p_id = priority.json()["id"]
    await client.post(f"/priorities/{p_id}/anchor")

    # Create non-anchored priority
    await client.post(
        "/priorities",
        json={
            "title": "Non-anchored Priority",
            "why_matters": "Testing non-anchored item",
            "score": 2,
        },
    )

    # List anchored only
    response = await client.get("/priorities", params={"anchored_only": True})
    assert response.status_code == 200


@pytest.fixture
def mock_validate_priority():
    """Mock priority validation."""
    from unittest.mock import patch
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
# Discovery Selections Operations
# ============================================================================


@pytest.mark.asyncio
async def test_discovery_selections_delete(client: AsyncClient):
    """Test deleting a discovery selection."""
    prompts = await client.get("/discovery/prompts")
    prompts_list = prompts.json()["prompts"]
    assert prompts.status_code == 200
    if not prompts_list:
        pytest.skip("No discovery prompts available for this user")
    prompt_id = prompts_list[0]["id"]

    sel = await client.post(
        "/discovery/selections",
        json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 1},
    )
    assert sel.status_code == 201
    sel_id = sel.json()["id"]

    response = await client.delete(f"/discovery/selections/{sel_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_discovery_move_selection_bucket(client: AsyncClient):
    """Test moving selection between buckets."""
    prompts = await client.get("/discovery/prompts")
    prompts_list = prompts.json()["prompts"]
    assert prompts.status_code == 200
    if not prompts_list:
        pytest.skip("No discovery prompts available for this user")
    prompt_id = prompts_list[0]["id"]

    sel = await client.post(
        "/discovery/selections",
        json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 1},
    )
    assert sel.status_code == 201
    sel_id = sel.json()["id"]

    response = await client.put(
        f"/discovery/selections/{sel_id}",
        json={"bucket": "ranked", "display_order": 1},
    )
    assert response.status_code == 200
    assert response.json()["bucket"] == "ranked"


# ============================================================================
# Goals Hierarchy Operations
# ============================================================================


@pytest.mark.asyncio
async def test_goal_hierarchy_depth_two(client: AsyncClient):
    """Test goals with a two-level hierarchy."""
    # Create grandparent
    grandparent = await client.post("/goals", json={"title": "Grandparent Goal"})
    gp_id = grandparent.json()["id"]

    # Create parent under grandparent
    parent = await client.post(
        "/goals",
        json={"title": "Parent Goal", "parent_goal_id": gp_id},
    )
    p_id = parent.json()["id"]

    # Create child under parent
    child = await client.post(
        "/goals",
        json={"title": "Child Goal", "parent_goal_id": p_id},
    )
    c_id = child.json()["id"]

    # Get child and verify hierarchy
    response = await client.get(f"/goals/{c_id}")
    assert response.status_code == 200
    assert response.json()["parent_goal_id"] == p_id


@pytest.mark.asyncio
async def test_goal_remove_priority_link(client: AsyncClient, mock_validate_priority):
    """Test removing a priority link from a goal."""
    priority = await client.post(
        "/priorities",
        json={
            "title": "Removable Link Priority",
            "why_matters": "Testing link removal",
            "score": 3,
        },
    )
    p_id = priority.json()["id"]

    goal = await client.post("/goals", json={"title": "Link Removal Goal"})
    goal_id = goal.json()["id"]

    # Link priority
    await client.post(f"/goals/{goal_id}/priorities/{p_id}")

    # Remove link
    response = await client.delete(f"/goals/{goal_id}/priorities/{p_id}")
    assert response.status_code == 200


# ============================================================================
# Dependencies Additional Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_dependency_satisfaction_check(client: AsyncClient):
    """Test checking if dependencies are satisfied."""
    goal = await client.post("/goals", json={"title": "Satisfaction Goal"})
    goal_id = goal.json()["id"]

    task1 = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Upstream Satisfaction", "duration_minutes": 30},
    )
    t1_id = task1.json()["id"]

    task2 = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Downstream Satisfaction", "duration_minutes": 30},
    )
    t2_id = task2.json()["id"]

    # Create dependency
    await client.post(
        "/dependencies",
        json={
            "upstream_task_id": t1_id,
            "downstream_task_id": t2_id,
            "rule_type": "completion",
            "is_hard": True,
        },
    )

    # Get task2 - should show unsatisfied dependency
    response = await client.get(f"/tasks/{t2_id}")
    assert response.status_code == 200

    # Complete task1
    await client.post(f"/tasks/{t1_id}/complete", json={})

    # Now task2 should have satisfied dependency
    response2 = await client.get(f"/tasks/{t2_id}")
    assert response2.status_code == 200


# ============================================================================
# Auth Token Operations
# ============================================================================


@pytest.mark.asyncio
async def test_authenticated_client_can_access_me_endpoint(client: AsyncClient):
    """Authenticated fixture client can access the /me endpoint."""
    response = await client.get("/me")
    assert response.status_code == 200


# ============================================================================
# Occurrence Ordering Additional Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reorder_multiple_tasks(client: AsyncClient):
    """Test reordering multiple tasks."""
    goal = await client.post("/goals", json={"title": "Multi Reorder Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    # Create multiple tasks
    tasks = []
    for i in range(3):
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": f"Reorder Task {i}",
                "duration_minutes": 30,
                "scheduled_at": now.isoformat(),
            },
        )
        tasks.append(task.json()["id"])

    # Reorder them in reverse
    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": today,
            "save_mode": "today",
            "occurrences": [
                {"task_id": tasks[2], "occurrence_index": 0},
                {"task_id": tasks[1], "occurrence_index": 0},
                {"task_id": tasks[0], "occurrence_index": 0},
            ],
        },
    )
    assert response.status_code == 200


# ============================================================================
# Task Stats Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_task_stats_empty_range(client: AsyncClient):
    """Test task stats with no occurrences in range."""
    goal = await client.post("/goals", json={"title": "Empty Stats Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)
    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Empty Stats Task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": (now + timedelta(days=30)).isoformat(),  # way in future
        },
    )
    task_id = task.json()["id"]

    # Query for dates that don't overlap
    response = await client.get(
        f"/tasks/{task_id}/stats",
        params={
            "start": (now - timedelta(days=10)).isoformat(),
            "end": (now - timedelta(days=5)).isoformat(),
        },
    )
    assert response.status_code == 200
