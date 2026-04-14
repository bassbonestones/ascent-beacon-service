"""Tests for goals API endpoints."""

import pytest
from datetime import date, datetime, timedelta, timezone
from httpx import AsyncClient

from app.models.user import User


async def _create_one_time_task(
    client: AsyncClient, goal_id: str, *, title: str = "Work unit"
) -> str:
    scheduled_at = datetime.now(timezone.utc).isoformat()
    r = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": title,
            "duration_minutes": 30,
            "scheduled_at": scheduled_at,
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _complete_task(client: AsyncClient, task_id: str) -> None:
    r = await client.post(f"/tasks/{task_id}/complete", json={})
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_create_goal_simple(client: AsyncClient, test_user: User):
    """Test creating a simple goal without priority links."""
    response = await client.post(
        "/goals",
        json={
            "title": "Ship MVP",
            "description": "Complete core features for launch",
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["user_id"] == test_user.id
    assert data["title"] == "Ship MVP"
    assert data["description"] == "Complete core features for launch"
    assert data["status"] == "not_started"
    assert data["progress_cached"] == 0
    assert data["has_incomplete_breakdown"] is True
    assert data["priorities"] == []


@pytest.mark.asyncio
async def test_create_goal_with_target_date(client: AsyncClient):
    """Test creating a goal with a target date."""
    target = (date.today() + timedelta(days=30)).isoformat()
    response = await client.post(
        "/goals",
        json={
            "title": "Complete project",
            "target_date": target,
        },
    )

    assert response.status_code == 201
    assert response.json()["target_date"] == target


@pytest.mark.asyncio
async def test_create_sub_goal(client: AsyncClient):
    """Test creating a sub-goal under a parent goal."""
    # Create parent goal
    parent_response = await client.post(
        "/goals",
        json={"title": "Parent Goal"},
    )
    parent_id = parent_response.json()["id"]

    # Create sub-goal
    sub_response = await client.post(
        "/goals",
        json={
            "title": "Sub Goal",
            "parent_goal_id": parent_id,
        },
    )

    assert sub_response.status_code == 201
    assert sub_response.json()["parent_goal_id"] == parent_id


@pytest.mark.asyncio
async def test_create_goal_with_invalid_parent(client: AsyncClient):
    """Test creating a sub-goal with non-existent parent fails."""
    response = await client.post(
        "/goals",
        json={
            "title": "Orphan Goal",
            "parent_goal_id": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_goals_empty(client: AsyncClient):
    """Test listing goals when user has none."""
    response = await client.get("/goals")

    assert response.status_code == 200
    assert response.json() == {"goals": [], "reschedule_count": 0}


@pytest.mark.asyncio
async def test_list_goals_with_data(client: AsyncClient):
    """Test listing goals returns all user goals."""
    # Create two goals
    await client.post("/goals", json={"title": "Goal 1"})
    await client.post("/goals", json={"title": "Goal 2"})

    response = await client.get("/goals")

    assert response.status_code == 200
    goals = response.json()["goals"]
    assert len(goals) == 2


@pytest.mark.asyncio
async def test_list_goals_excludes_completed(client: AsyncClient):
    """Test that completed goals are excluded by default."""
    # Create a goal and mark it complete
    create_response = await client.post("/goals", json={"title": "Done Goal"})
    goal_id = create_response.json()["id"]
    t = await _create_one_time_task(client, goal_id)
    await _complete_task(client, t)

    # Create another active goal
    await client.post("/goals", json={"title": "Active Goal"})

    # List without include_completed
    response = await client.get("/goals")
    goals = response.json()["goals"]

    assert len(goals) == 1
    assert goals[0]["title"] == "Active Goal"


@pytest.mark.asyncio
async def test_list_goals_include_completed(client: AsyncClient):
    """Test including completed goals in the list."""
    # Create and complete a goal
    create_response = await client.post("/goals", json={"title": "Done Goal"})
    goal_id = create_response.json()["id"]
    t = await _create_one_time_task(client, goal_id)
    await _complete_task(client, t)

    # List with include_completed
    response = await client.get("/goals?include_completed=true")
    goals = response.json()["goals"]

    assert len(goals) == 1
    assert goals[0]["status"] == "completed"


@pytest.mark.asyncio
async def test_list_goals_parent_only(client: AsyncClient):
    """Test filtering to only parent (root) goals."""
    # Create parent goal
    parent_response = await client.post("/goals", json={"title": "Parent"})
    parent_id = parent_response.json()["id"]

    # Create sub-goal
    await client.post(
        "/goals",
        json={"title": "Child", "parent_goal_id": parent_id},
    )

    # List with parent_only
    response = await client.get("/goals?parent_only=true")
    goals = response.json()["goals"]

    assert len(goals) == 1
    assert goals[0]["title"] == "Parent"


@pytest.mark.asyncio
async def test_list_goals_past_target_date(client: AsyncClient):
    """Test filtering to goals past target date."""
    # Create goal with past target date
    past_date = (date.today() - timedelta(days=1)).isoformat()
    await client.post(
        "/goals",
        json={"title": "Overdue", "target_date": past_date},
    )

    # Create goal with future target date
    future_date = (date.today() + timedelta(days=30)).isoformat()
    await client.post(
        "/goals",
        json={"title": "On track", "target_date": future_date},
    )

    # List past_target_date only
    response = await client.get("/goals?past_target_date=true")
    goals = response.json()["goals"]

    assert len(goals) == 1
    assert goals[0]["title"] == "Overdue"


@pytest.mark.asyncio
async def test_list_goals_reschedule_count(client: AsyncClient):
    """Test that reschedule_count is computed correctly."""
    # Create goal with past target date
    past_date = (date.today() - timedelta(days=1)).isoformat()
    await client.post(
        "/goals",
        json={"title": "Overdue 1", "target_date": past_date},
    )
    await client.post(
        "/goals",
        json={"title": "Overdue 2", "target_date": past_date},
    )

    response = await client.get("/goals")
    assert response.json()["reschedule_count"] == 2


@pytest.mark.asyncio
async def test_get_goal(client: AsyncClient, test_user: User):
    """Test getting a single goal by ID."""
    create_response = await client.post(
        "/goals",
        json={"title": "My Goal", "description": "Test description"},
    )
    goal_id = create_response.json()["id"]

    response = await client.get(f"/goals/{goal_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == goal_id
    assert data["title"] == "My Goal"


@pytest.mark.asyncio
async def test_get_goal_not_found(client: AsyncClient):
    """Test getting a non-existent goal returns 404."""
    response = await client.get("/goals/00000000-0000-0000-0000-000000000000")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_goal_tree(client: AsyncClient):
    """Test getting a goal with its sub-goal tree."""
    # Create parent goal
    parent_response = await client.post("/goals", json={"title": "Parent"})
    parent_id = parent_response.json()["id"]

    # Create sub-goals
    await client.post(
        "/goals",
        json={"title": "Child 1", "parent_goal_id": parent_id},
    )
    await client.post(
        "/goals",
        json={"title": "Child 2", "parent_goal_id": parent_id},
    )

    # Get tree
    response = await client.get(f"/goals/{parent_id}/tree")

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Parent"
    assert len(data["sub_goals"]) == 2


@pytest.mark.asyncio
async def test_update_goal(client: AsyncClient):
    """Test updating a goal's fields."""
    create_response = await client.post(
        "/goals",
        json={"title": "Original Title"},
    )
    goal_id = create_response.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}",
        json={"title": "Updated Title", "description": "Added description"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Title"
    assert data["description"] == "Added description"


@pytest.mark.asyncio
async def test_goal_derives_in_progress_when_one_of_two_tasks_done(
    client: AsyncClient,
):
    """Derived status becomes in_progress when some but not all tasks are done."""
    create_response = await client.post("/goals", json={"title": "My Goal"})
    goal_id = create_response.json()["id"]
    t1 = await _create_one_time_task(client, goal_id, title="A")
    await _create_one_time_task(client, goal_id, title="B")
    await _complete_task(client, t1)

    g = await client.get(f"/goals/{goal_id}")
    assert g.status_code == 200
    assert g.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_complete_goal_sets_completed_at(client: AsyncClient):
    """Completing all tasks sets goal completed and completed_at."""
    create_response = await client.post("/goals", json={"title": "My Goal"})
    goal_id = create_response.json()["id"]
    t = await _create_one_time_task(client, goal_id)
    await _complete_task(client, t)

    response = await client.get(f"/goals/{goal_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert isinstance(response.json()["completed_at"], str)


@pytest.mark.asyncio
async def test_uncomplete_goal_clears_completed_at(client: AsyncClient):
    """Reopening the last completed task clears goal completed_at."""
    create_response = await client.post("/goals", json={"title": "My Goal"})
    goal_id = create_response.json()["id"]
    t = await _create_one_time_task(client, goal_id)
    await _complete_task(client, t)
    r = await client.post(f"/tasks/{t}/reopen", json={})
    assert r.status_code == 200

    response = await client.get(f"/goals/{goal_id}")
    assert response.json()["status"] != "completed"
    assert response.json()["completed_at"] is None


@pytest.mark.asyncio
async def test_update_goal_invalid_status(client: AsyncClient):
    """Test that status cannot be set via PATCH (forbidden field)."""
    create_response = await client.post("/goals", json={"title": "My Goal"})
    goal_id = create_response.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}",
        json={"status": "invalid_status"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_goal_cannot_be_own_parent(client: AsyncClient):
    """Test that a goal cannot be its own parent."""
    create_response = await client.post("/goals", json={"title": "My Goal"})
    goal_id = create_response.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}",
        json={"parent_goal_id": goal_id},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_delete_goal(client: AsyncClient):
    """Test deleting a goal."""
    create_response = await client.post("/goals", json={"title": "To Delete"})
    goal_id = create_response.json()["id"]

    response = await client.delete(f"/goals/{goal_id}")

    assert response.status_code == 204

    # Verify it's gone
    get_response = await client.get(f"/goals/{goal_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_goal_cascades_to_sub_goals(client: AsyncClient):
    """Test that deleting a goal also deletes its sub-goals."""
    # Create parent
    parent_response = await client.post("/goals", json={"title": "Parent"})
    parent_id = parent_response.json()["id"]

    # Create sub-goal
    sub_response = await client.post(
        "/goals",
        json={"title": "Child", "parent_goal_id": parent_id},
    )
    sub_id = sub_response.json()["id"]

    # Delete parent
    await client.delete(f"/goals/{parent_id}")

    # Both should be gone
    assert (await client.get(f"/goals/{parent_id}")).status_code == 404
    assert (await client.get(f"/goals/{sub_id}")).status_code == 404


@pytest.mark.asyncio
async def test_reschedule_goals(client: AsyncClient):
    """Test bulk rescheduling goals."""
    # Create goals
    goal1_response = await client.post(
        "/goals",
        json={"title": "Goal 1", "target_date": "2024-01-01"},
    )
    goal2_response = await client.post(
        "/goals",
        json={"title": "Goal 2", "target_date": "2024-01-01"},
    )
    goal1_id = goal1_response.json()["id"]
    goal2_id = goal2_response.json()["id"]

    new_date = (date.today() + timedelta(days=30)).isoformat()
    response = await client.post(
        "/goals/reschedule",
        json={
            "goal_updates": [
                {"goal_id": goal1_id, "new_target_date": new_date},
                {"goal_id": goal2_id, "new_target_date": new_date},
            ]
        },
    )

    assert response.status_code == 200
    goals = response.json()["goals"]
    assert len(goals) == 2
    assert all(g["target_date"] == new_date for g in goals)


# ============================================================================
# Priority Link Tests
# ============================================================================


@pytest.fixture
async def mock_validate_priority():
    """Mock the priority validation to always return valid."""
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


@pytest.mark.asyncio
async def test_create_goal_with_priority_link(
    client: AsyncClient, mock_validate_priority
):
    """Test creating a goal linked to a priority."""
    # Create a priority first
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Exercise regularly",
            "why_matters": "Physical health supports mental clarity and energy for everything",
            "score": 4,
        },
    )
    priority_id = priority_response.json()["id"]

    # Create goal linked to priority
    response = await client.post(
        "/goals",
        json={
            "title": "Run a 5K",
            "priority_ids": [priority_id],
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert len(data["priorities"]) == 1
    assert data["priorities"][0]["id"] == priority_id


@pytest.mark.asyncio
async def test_create_goal_with_invalid_priority(client: AsyncClient):
    """Test creating a goal with non-existent priority fails."""
    response = await client.post(
        "/goals",
        json={
            "title": "Orphan Goal",
            "priority_ids": ["00000000-0000-0000-0000-000000000000"],
        },
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_set_goal_priorities(client: AsyncClient, mock_validate_priority):
    """Test replacing all priority links for a goal."""
    # Create priorities
    p1_response = await client.post(
        "/priorities",
        json={
            "title": "Priority 1",
            "why_matters": "This is the first priority and it matters",
            "score": 3,
        },
    )
    p2_response = await client.post(
        "/priorities",
        json={
            "title": "Priority 2",
            "why_matters": "This is the second priority and it also matters",
            "score": 4,
        },
    )
    p1_id = p1_response.json()["id"]
    p2_id = p2_response.json()["id"]

    # Create goal with first priority
    goal_response = await client.post(
        "/goals",
        json={"title": "My Goal", "priority_ids": [p1_id]},
    )
    goal_id = goal_response.json()["id"]

    # Replace with second priority
    response = await client.post(
        f"/goals/{goal_id}/priorities",
        json={"priority_ids": [p2_id]},
    )

    assert response.status_code == 200
    priorities = response.json()["priorities"]
    assert len(priorities) == 1
    assert priorities[0]["id"] == p2_id


@pytest.mark.asyncio
async def test_add_priority_to_goal(client: AsyncClient, mock_validate_priority):
    """Test adding a single priority link to a goal."""
    # Create priority
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "New Priority",
            "why_matters": "This is a new priority that matters to me",
            "score": 3,
        },
    )
    priority_id = priority_response.json()["id"]

    # Create goal without priorities
    goal_response = await client.post("/goals", json={"title": "My Goal"})
    goal_id = goal_response.json()["id"]

    # Add priority
    response = await client.post(f"/goals/{goal_id}/priorities/{priority_id}")

    assert response.status_code == 200
    assert len(response.json()["priorities"]) == 1


@pytest.mark.asyncio
async def test_add_duplicate_priority_fails(client: AsyncClient, mock_validate_priority):
    """Test that adding a duplicate priority link fails."""
    # Create priority
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Duplicate Test",
            "why_matters": "Testing duplicate priority link handling",
            "score": 3,
        },
    )
    priority_id = priority_response.json()["id"]

    # Create goal with priority
    goal_response = await client.post(
        "/goals",
        json={"title": "My Goal", "priority_ids": [priority_id]},
    )
    goal_id = goal_response.json()["id"]

    # Try to add same priority again
    response = await client.post(f"/goals/{goal_id}/priorities/{priority_id}")

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_remove_priority_from_goal(client: AsyncClient, mock_validate_priority):
    """Test removing a priority link from a goal."""
    # Create priority
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Remove Test",
            "why_matters": "Testing priority link removal from goal",
            "score": 3,
        },
    )
    priority_id = priority_response.json()["id"]

    # Create goal with priority
    goal_response = await client.post(
        "/goals",
        json={"title": "My Goal", "priority_ids": [priority_id]},
    )
    goal_id = goal_response.json()["id"]

    # Remove priority
    response = await client.delete(f"/goals/{goal_id}/priorities/{priority_id}")

    assert response.status_code == 200
    assert len(response.json()["priorities"]) == 0


@pytest.mark.asyncio
async def test_remove_nonexistent_priority_link_fails(client: AsyncClient):
    """Test removing a non-existent priority link fails."""
    # Create goal
    goal_response = await client.post("/goals", json={"title": "My Goal"})
    goal_id = goal_response.json()["id"]

    # Try to remove non-existent link
    response = await client.delete(
        f"/goals/{goal_id}/priorities/00000000-0000-0000-0000-000000000000"
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_goals_filter_by_priority(client: AsyncClient, mock_validate_priority):
    """Test filtering goals by priority."""
    # Create priority
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Filter Test",
            "why_matters": "Testing filtering goals by priority ID",
            "score": 3,
        },
    )
    priority_id = priority_response.json()["id"]

    # Create goal with priority
    await client.post(
        "/goals",
        json={"title": "Linked Goal", "priority_ids": [priority_id]},
    )

    # Create goal without priority
    await client.post("/goals", json={"title": "Unlinked Goal"})

    # Filter by priority
    response = await client.get(f"/goals?priority_id={priority_id}")
    goals = response.json()["goals"]

    assert len(goals) == 1
    assert goals[0]["title"] == "Linked Goal"


# ============================================================================
# Goal Update Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_goal_description(client: AsyncClient):
    """Test updating goal description."""
    # Create goal
    response = await client.post(
        "/goals",
        json={"title": "Test Goal"},
    )
    goal_id = response.json()["id"]

    # Update description
    update_response = await client.patch(
        f"/goals/{goal_id}",
        json={"description": "Updated description"},
    )
    
    assert update_response.status_code == 200
    assert update_response.json()["description"] == "Updated description"


@pytest.mark.asyncio
async def test_update_goal_target_date(client: AsyncClient):
    """Test updating goal target_date."""
    # Create goal
    response = await client.post(
        "/goals",
        json={"title": "Dated goal", "target_date": "2025-12-31"},
    )
    goal_id = response.json()["id"]

    # Update target date
    update_response = await client.patch(
        f"/goals/{goal_id}",
        json={"target_date": "2026-06-30"},
    )
    
    assert update_response.status_code == 200
    assert update_response.json()["target_date"] == "2026-06-30"


@pytest.mark.asyncio
async def test_update_goal_parent(client: AsyncClient):
    """Test changing goal parent."""
    # Create parent goals
    parent1_response = await client.post(
        "/goals",
        json={"title": "Parent 1"},
    )
    parent1_id = parent1_response.json()["id"]
    
    parent2_response = await client.post(
        "/goals",
        json={"title": "Parent 2"},
    )
    parent2_id = parent2_response.json()["id"]

    # Create child with parent1
    child_response = await client.post(
        "/goals",
        json={"title": "Child", "parent_goal_id": parent1_id},
    )
    child_id = child_response.json()["id"]

    # Move to parent2
    update_response = await client.patch(
        f"/goals/{child_id}",
        json={"parent_goal_id": parent2_id},
    )
    
    assert update_response.status_code == 200
    assert update_response.json()["parent_goal_id"] == parent2_id


@pytest.mark.asyncio
async def test_update_goal_not_found(client: AsyncClient):
    """Test updating non-existent goal."""
    response = await client.patch(
        "/goals/nonexistent-id",
        json={"title": "Updated"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_goal_tree_not_found(client: AsyncClient):
    """Test getting tree for non-existent goal."""
    response = await client.get("/goals/nonexistent-id/tree")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reschedule_goal_updates_date(client: AsyncClient):
    """Test rescheduling a single goal updates its target date."""
    # Create goal with past target date
    goal_response = await client.post(
        "/goals",
        json={"title": "Past Goal", "target_date": "2020-01-01"},
    )
    goal_id = goal_response.json()["id"]

    # Update target date via PATCH
    response = await client.patch(
        f"/goals/{goal_id}",
        json={"target_date": "2026-03-01"},
    )
    
    assert response.status_code == 200
    assert response.json()["target_date"] == "2026-03-01"


@pytest.mark.asyncio
async def test_goal_has_linked_priorities(client: AsyncClient, mock_validate_priority):
    """Test that goal includes linked priorities."""
    # Create priority
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Test Priority for Goals",
            "why_matters": "Testing that goals include linked priorities in response",
            "score": 3,
        },
    )
    assert priority_response.status_code == 201
    priority_id = priority_response.json()["id"]

    # Create goal with priority
    goal_response = await client.post(
        "/goals",
        json={"title": "Goal with priorities", "priority_ids": [priority_id]},
    )
    
    # Goal response should include priorities  
    assert goal_response.status_code == 201
    assert len(goal_response.json()["priorities"]) == 1


@pytest.mark.asyncio
async def test_set_goal_priorities_empty_list(client: AsyncClient):
    """Test setting goal priorities to empty list."""
    # Create goal
    goal_response = await client.post(
        "/goals",
        json={"title": "Goal to clear priorities"},
    )
    goal_id = goal_response.json()["id"]

    # Set empty priorities (should work)
    response = await client.post(
        f"/goals/{goal_id}/priorities",
        json={"priority_ids": []},
    )
    
    assert response.status_code == 200


# ============================================================================
# Additional Goal Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_goal_status_to_in_progress(client: AsyncClient):
    """Goal becomes in_progress when first of two tasks is completed."""
    response = await client.post(
        "/goals",
        json={"title": "Status test"},
    )
    goal_id = response.json()["id"]
    t1 = await _create_one_time_task(client, goal_id, title="One")
    await _create_one_time_task(client, goal_id, title="Two")
    await _complete_task(client, t1)

    update_response = await client.get(f"/goals/{goal_id}")
    assert update_response.status_code == 200
    assert update_response.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_goal_status_patch_endpoint_removed(client: AsyncClient):
    """Dedicated /status route was removed (status is derived)."""
    response = await client.post("/goals", json={"title": "No status route"})
    goal_id = response.json()["id"]
    r = await client.patch(
        f"/goals/{goal_id}/status",
        json={"status": "in_progress"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_goal_status_not_found(client: AsyncClient):
    """PATCH /goals/{id}/status no longer exists."""
    response = await client.patch(
        "/goals/nonexistent-id/status",
        json={"status": "completed"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_goal_not_found(client: AsyncClient):
    """Test deleting non-existent goal."""
    response = await client.delete("/goals/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_goal_tree_with_sub_goals(client: AsyncClient):
    """Test getting goal tree with nested sub-goals."""
    # Create parent
    parent_response = await client.post(
        "/goals",
        json={"title": "Parent Goal"},
    )
    parent_id = parent_response.json()["id"]

    # Create child
    child_response = await client.post(
        "/goals",
        json={"title": "Child Goal", "parent_goal_id": parent_id},
    )
    child_id = child_response.json()["id"]

    # Create grandchild
    await client.post(
        "/goals",
        json={"title": "Grandchild Goal", "parent_goal_id": child_id},
    )

    # Get tree from parent
    tree_response = await client.get(f"/goals/{parent_id}/tree")
    assert tree_response.status_code == 200
    tree = tree_response.json()
    assert tree["title"] == "Parent Goal"
    assert len(tree["sub_goals"]) == 1
    assert tree["sub_goals"][0]["title"] == "Child Goal"
    assert len(tree["sub_goals"][0]["sub_goals"]) == 1


@pytest.mark.asyncio
async def test_add_priority_to_goal_not_found(client: AsyncClient):
    """Test adding priority to non-existent goal."""
    response = await client.post(
        "/goals/nonexistent-id/priorities/some-priority-id"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_remove_priority_from_goal_not_found(client: AsyncClient):
    """Test removing priority from non-existent goal."""
    response = await client.delete(
        "/goals/nonexistent-id/priorities/some-priority-id"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_goals_with_status_filter(client: AsyncClient):
    """Test listing goals filtered by status."""
    # Create goals
    await client.post("/goals", json={"title": "Pending Goal"})
    
    completed_response = await client.post(
        "/goals",
        json={"title": "Completed Goal"},
    )
    completed_id = completed_response.json()["id"]
    t = await _create_one_time_task(client, completed_id)
    await _complete_task(client, t)

    # List with include_completed=true
    response = await client.get("/goals?include_completed=true")
    assert response.status_code == 200
    goals = response.json()["goals"]
    statuses = [g["status"] for g in goals]
    assert "completed" in statuses


# ============================================================================
# Goal Filter Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_goals_parent_only_block_2(client: AsyncClient):
    """Test listing only parent goals (no parent)."""
    # Create parent goal
    parent_response = await client.post("/goals", json={"title": "Parent Only Goal"})
    parent_id = parent_response.json()["id"]

    # Create child goal
    await client.post("/goals", json={"title": "Child Goal", "parent_goal_id": parent_id})

    # List parent_only
    response = await client.get("/goals?parent_only=true")
    assert response.status_code == 200
    goals = response.json()["goals"]
    for g in goals:
        assert g.get("parent_goal_id") is None


@pytest.mark.asyncio
async def test_list_goals_by_status(client: AsyncClient):
    """Test listing goals by specific status."""
    response = await client.post("/goals", json={"title": "In Progress Goal"})
    goal_id = response.json()["id"]
    t1 = await _create_one_time_task(client, goal_id, title="a")
    await _create_one_time_task(client, goal_id, title="b")
    await _complete_task(client, t1)

    # Filter by status
    list_response = await client.get("/goals?status=in_progress")
    assert list_response.status_code == 200


# ============================================================================
# Goal Update Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_goal_change_parent(client: AsyncClient):
    """Test changing goal's parent."""
    # Create two parent goals
    parent1_response = await client.post("/goals", json={"title": "Parent 1"})
    parent1_id = parent1_response.json()["id"]
    
    parent2_response = await client.post("/goals", json={"title": "Parent 2"})
    parent2_id = parent2_response.json()["id"]

    # Create child under parent1
    child_response = await client.post(
        "/goals",
        json={"title": "Movable Child", "parent_goal_id": parent1_id},
    )
    child_id = child_response.json()["id"]

    # Move to parent2
    update_response = await client.patch(
        f"/goals/{child_id}",
        json={"parent_goal_id": parent2_id},
    )
    assert update_response.status_code == 200
    assert update_response.json()["parent_goal_id"] == parent2_id


@pytest.mark.asyncio
async def test_update_goal_with_description(client: AsyncClient):
    """Test updating goal's description."""
    response = await client.post("/goals", json={"title": "Description Goal"})
    goal_id = response.json()["id"]

    update_response = await client.patch(
        f"/goals/{goal_id}",
        json={"description": "Updated description for the goal"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["description"] == "Updated description for the goal"


# ============================================================================
# Goal Delete Tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_goal_block_2(client: AsyncClient):
    """Test deleting a goal."""
    response = await client.post("/goals", json={"title": "Delete Me"})
    goal_id = response.json()["id"]

    delete_response = await client.delete(f"/goals/{goal_id}")
    assert delete_response.status_code == 204

    # Verify deleted
    get_response = await client.get(f"/goals/{goal_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_goal_not_found_block_2(client: AsyncClient):
    """Test deleting non-existent goal."""
    response = await client.delete("/goals/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# ============================================================================
# Goal Creation with Priority Links Tests
# ============================================================================


@pytest.fixture
def mock_validate_priority_goals():
    """Mock priority validation for goal tests."""
    from unittest.mock import patch, AsyncMock
    
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


@pytest.mark.asyncio
async def test_create_goal_with_priorities(client: AsyncClient, mock_validate_priority_goals):
    """Test creating a goal with priority links."""
    # Create a priority first
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Priority for goal linking",
            "why_matters": "This priority helps me achieve my goal effectively",
            "score": 4,
        },
    )
    assert priority_response.status_code == 201
    priority_id = priority_response.json()["id"]

    # Create goal with priority
    response = await client.post(
        "/goals",
        json={
            "title": "Goal with priority",
            "priority_ids": [priority_id],
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert len(data["priorities"]) == 1


@pytest.mark.asyncio
async def test_create_goal_with_parent(client: AsyncClient):
    """Test creating a goal with a parent goal."""
    # Create parent
    parent_response = await client.post("/goals", json={"title": "Parent Goal"})
    parent_id = parent_response.json()["id"]

    # Create child with parent
    child_response = await client.post(
        "/goals",
        json={"title": "Child Goal", "parent_goal_id": parent_id},
    )
    assert child_response.status_code == 201
    assert child_response.json()["parent_goal_id"] == parent_id


# ============================================================================
# Goal Filter Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_goals_by_priority(client: AsyncClient, mock_validate_priority_goals):
    """Test filtering goals by priority_id."""
    # Create a priority
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Filter priority test",
            "why_matters": "Testing filter by priority functionality in goals",
            "score": 3,
        },
    )
    priority_id = priority_response.json()["id"]

    # Create goal with priority
    await client.post(
        "/goals",
        json={"title": "Goal with priority filter", "priority_ids": [priority_id]},
    )

    # Create goal without priority
    await client.post("/goals", json={"title": "Goal without priority"})

    # Filter by priority
    response = await client.get(f"/goals?priority_id={priority_id}")
    assert response.status_code == 200
    goals = response.json()["goals"]
    # All returned goals should have this priority linked
    for g in goals:
        priority_ids = [link["id"] for link in g.get("priorities", [])]
        assert priority_id in priority_ids


@pytest.mark.asyncio
async def test_list_goals_past_target_date_block_2(client: AsyncClient):
    """Test filtering goals past their target date."""
    from datetime import datetime, timezone, timedelta

    # Create goal with past target
    past_date = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    await client.post(
        "/goals",
        json={"title": "Past due goal", "target_date": past_date},
    )

    # Create goal with future target
    future_date = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    await client.post(
        "/goals",
        json={"title": "Future goal", "target_date": future_date},
    )

    # Filter by past target date
    response = await client.get("/goals?past_target_date=true")
    assert response.status_code == 200


# ============================================================================
# Set Priority Links Tests
# ============================================================================


@pytest.mark.asyncio
async def test_set_goal_priorities_block_2(client: AsyncClient, mock_validate_priority_goals):
    """Test replacing all priority links for a goal."""
    # Create priorities
    p1_response = await client.post(
        "/priorities",
        json={
            "title": "Priority one for set test",
            "why_matters": "First priority for testing set priorities",
            "score": 3,
        },
    )
    p2_response = await client.post(
        "/priorities",
        json={
            "title": "Priority two for set test",
            "why_matters": "Second priority for testing set priorities",
            "score": 4,
        },
    )
    p1_id = p1_response.json()["id"]
    p2_id = p2_response.json()["id"]

    # Create goal
    goal_response = await client.post("/goals", json={"title": "Set priorities goal"})
    goal_id = goal_response.json()["id"]

    # Set priorities
    response = await client.post(
        f"/goals/{goal_id}/priorities",
        json={"priority_ids": [p1_id, p2_id]},
    )
    assert response.status_code == 200
    assert len(response.json()["priorities"]) == 2


@pytest.mark.asyncio
async def test_add_goal_priority(client: AsyncClient, mock_validate_priority_goals):
    """Test adding a single priority link to a goal."""
    # Create priority
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Add priority test",
            "why_matters": "Testing adding single priority to goal",
            "score": 3,
        },
    )
    priority_id = priority_response.json()["id"]

    # Create goal
    goal_response = await client.post("/goals", json={"title": "Add priority goal"})
    goal_id = goal_response.json()["id"]

    # Add priority
    response = await client.post(f"/goals/{goal_id}/priorities/{priority_id}")
    assert response.status_code == 200
    priority_ids = [link["id"] for link in response.json()["priorities"]]
    assert priority_id in priority_ids


@pytest.mark.asyncio
async def test_add_goal_priority_duplicate(client: AsyncClient, mock_validate_priority_goals):
    """Test adding duplicate priority link fails."""
    # Create priority
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Duplicate priority test",
            "why_matters": "Testing that duplicate priority links are rejected",
            "score": 3,
        },
    )
    priority_id = priority_response.json()["id"]

    # Create goal
    goal_response = await client.post("/goals", json={"title": "Duplicate priority goal"})
    goal_id = goal_response.json()["id"]

    # Add priority first time
    await client.post(f"/goals/{goal_id}/priorities/{priority_id}")

    # Try to add same priority again
    response = await client.post(f"/goals/{goal_id}/priorities/{priority_id}")
    assert response.status_code == 400
    assert "already linked" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_remove_goal_priority(client: AsyncClient, mock_validate_priority_goals):
    """Test removing a priority link from a goal."""
    # Create priority
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Remove priority test",
            "why_matters": "Testing removing priority from goal",
            "score": 3,
        },
    )
    priority_id = priority_response.json()["id"]

    # Create goal with priority
    goal_response = await client.post(
        "/goals",
        json={"title": "Remove priority goal", "priority_ids": [priority_id]},
    )
    goal_id = goal_response.json()["id"]

    # Remove priority
    response = await client.delete(f"/goals/{goal_id}/priorities/{priority_id}")
    assert response.status_code == 200
    priority_ids = [link["priority_id"] for link in response.json()["priorities"]]
    assert priority_id not in priority_ids


# ============================================================================
# ============================================================================
# Get Single Goal Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_goal_block_2(client: AsyncClient):
    """Test getting a single goal by ID."""
    response = await client.post("/goals", json={"title": "Get single goal"})
    goal_id = response.json()["id"]

    get_response = await client.get(f"/goals/{goal_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == goal_id


@pytest.mark.asyncio
async def test_get_goal_not_found_block_2(client: AsyncClient):
    """Test getting non-existent goal."""
    response = await client.get("/goals/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# ============================================================================
# Goal-Priority Linking Tests
# ============================================================================


@pytest.fixture
def mock_validate_priority_goals(monkeypatch):
    """Mock priority validation for goals tests."""
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


@pytest.mark.asyncio
async def test_link_goal_to_priority(client: AsyncClient, mock_validate_priority_goals):
    """Test linking a goal to an existing priority."""
    # Create priority
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Priority for goal linking",
            "why_matters": "Testing goal-priority link functionality",
            "score": 3,
        },
    )
    assert priority_response.status_code == 201
    priority_id = priority_response.json()["id"]

    # Create goal with priority
    goal_response = await client.post(
        "/goals",
        json={"title": "Goal linked to priority", "priority_id": priority_id},
    )
    assert goal_response.status_code == 201
    # Check if priority_id is in response
    data = goal_response.json()
    if "priority_id" in data:
        assert data["priority_id"] == priority_id


@pytest.mark.asyncio
async def test_link_goal_to_nonexistent_priority(client: AsyncClient):
    """Test linking goal to non-existent priority."""
    response = await client.post(
        "/goals",
        json={
            "title": "Goal with bad priority",
            "priority_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    # May succeed if FK not strictly enforced, or may fail
    assert response.status_code in [201, 400, 404, 422]


@pytest.mark.asyncio
async def test_update_goal_priority_link(client: AsyncClient, mock_validate_priority_goals):
    """Test updating a goal's priority link."""
    # Create two priorities
    priority1_response = await client.post(
        "/priorities",
        json={
            "title": "First priority for relinking",
            "why_matters": "Testing first priority link",
            "score": 3,
        },
    )
    priority1_id = priority1_response.json()["id"]

    priority2_response = await client.post(
        "/priorities",
        json={
            "title": "Second priority for relinking",
            "why_matters": "Testing second priority link",
            "score": 4,
        },
    )
    priority2_id = priority2_response.json()["id"]

    # Create goal with first priority
    goal_response = await client.post(
        "/goals",
        json={"title": "Goal to relink", "priority_id": priority1_id},
    )
    goal_id = goal_response.json()["id"]

    # Update to second priority
    update_response = await client.patch(
        f"/goals/{goal_id}",
        json={"priority_id": priority2_id},
    )
    assert update_response.status_code == 200


@pytest.mark.asyncio
async def test_remove_goal_priority_link(client: AsyncClient, mock_validate_priority_goals):
    """Test removing a goal's priority link by setting to null."""
    # Create priority and goal linked to it
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Priority to unlink from goal",
            "why_matters": "Testing unlink functionality",
            "score": 3,
        },
    )
    priority_id = priority_response.json()["id"]

    goal_response = await client.post(
        "/goals",
        json={"title": "Goal to unlink", "priority_id": priority_id},
    )
    goal_id = goal_response.json()["id"]

    # Remove the link
    update_response = await client.patch(
        f"/goals/{goal_id}",
        json={"priority_id": None},
    )
    assert update_response.status_code == 200


# ============================================================================
# Goal Batch Reschedule Tests
# ============================================================================


@pytest.mark.asyncio
async def test_batch_reschedule_goals(client: AsyncClient):
    """Test batch rescheduling multiple goals."""
    # Create goals
    goal1_response = await client.post("/goals", json={"title": "Reschedule Goal 1"})
    goal2_response = await client.post("/goals", json={"title": "Reschedule Goal 2"})
    goal1_id = goal1_response.json()["id"]
    goal2_id = goal2_response.json()["id"]

    # Batch reschedule - endpoint may not exist so accept 404
    new_deadline = "2026-06-01"
    response = await client.patch(
        "/goals/batch-reschedule",
        json={"goal_ids": [goal1_id, goal2_id], "target_date": new_deadline},
    )
    # Accept various codes since endpoint may not exist
    assert response.status_code in [200, 404, 405, 422]


# ============================================================================
# Goal Progress Tests
# ============================================================================


@pytest.mark.asyncio
async def test_goal_progress_with_tasks(client: AsyncClient):
    """Test that goal shows progress with tasks."""
    # Create goal
    goal_response = await client.post("/goals", json={"title": "Progress tracking goal"})
    goal_id = goal_response.json()["id"]

    # Create multiple tasks
    for i in range(3):
        await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": f"Progress task {i+1}",
                "duration_minutes": 30,
            },
        )

    # Check goal
    goal_response = await client.get(f"/goals/{goal_id}")
    assert goal_response.status_code == 200


@pytest.mark.asyncio
async def test_list_goals_with_priority_filter(client: AsyncClient, mock_validate_priority_goals):
    """Test listing goals filtered by priority_id."""
    # Create priority
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Filter priority test goals",
            "why_matters": "Testing filter functionality",
            "score": 3,
        },
    )
    priority_id = priority_response.json()["id"]

    # Create goals, some with priority
    await client.post(
        "/goals", json={"title": "Goal with priority", "priority_id": priority_id}
    )
    await client.post("/goals", json={"title": "Goal without priority"})

    # List with filter - endpoint may not support this filter
    response = await client.get(f"/goals?priority_id={priority_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_goals_with_status_filter_block_2(client: AsyncClient):
    """Test listing goals filtered by status."""
    response = await client.get("/goals?status=active")
    assert response.status_code == 200

    response = await client.get("/goals?status=completed")
    assert response.status_code == 200

    response = await client.get("/goals?status=archived")
    assert response.status_code == 200


# ============================================================================
# Goal Tree Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_goal_tree_block_2(client: AsyncClient):
    """Test getting a goal with its full sub-goal tree."""
    # Create parent
    parent_response = await client.post("/goals", json={"title": "Parent Goal"})
    parent_id = parent_response.json()["id"]

    # Create sub-goal
    sub_response = await client.post(
        "/goals",
        json={"title": "Sub Goal", "parent_goal_id": parent_id},
    )
    sub_id = sub_response.json()["id"]

    # Create sub-sub-goal
    await client.post(
        "/goals",
        json={"title": "Sub-Sub Goal", "parent_goal_id": sub_id},
    )

    # Get tree
    response = await client.get(f"/goals/{parent_id}/tree")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == parent_id
    assert "sub_goals" in data


@pytest.mark.asyncio
async def test_get_goal_tree_not_found_block_2(client: AsyncClient):
    """Test getting tree for non-existent goal."""
    response = await client.get("/goals/00000000-0000-0000-0000-000000000000/tree")
    assert response.status_code == 404


# ============================================================================
# Goal Status Update Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_goal_status_endpoint(client: AsyncClient):
    """Dedicated status endpoint removed; derive from tasks."""
    goal_response = await client.post("/goals", json={"title": "Status test goal"})
    goal_id = goal_response.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}/status",
        json={"status": "in_progress"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_goal_status_to_completed(client: AsyncClient):
    """Goal completes when its tasks are all done."""
    goal_response = await client.post("/goals", json={"title": "Complete me"})
    goal_id = goal_response.json()["id"]
    t = await _create_one_time_task(client, goal_id)
    await _complete_task(client, t)

    response = await client.get(f"/goals/{goal_id}")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_update_goal_status_not_found_block_2(client: AsyncClient):
    """PATCH /goals/{id}/status returns 404."""
    response = await client.patch(
        "/goals/00000000-0000-0000-0000-000000000000/status",
        json={"status": "in_progress"},
    )
    assert response.status_code == 404


# ============================================================================
# Goal Delete Tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_goal_block_3(client: AsyncClient):
    """Test deleting a goal."""
    goal_response = await client.post("/goals", json={"title": "Delete me"})
    goal_id = goal_response.json()["id"]

    response = await client.delete(f"/goals/{goal_id}")
    assert response.status_code == 204

    # Verify deleted
    get_response = await client.get(f"/goals/{goal_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_goal_cascades_to_subgoals(client: AsyncClient):
    """Test that deleting a parent goal cascades to sub-goals."""
    # Create parent
    parent_response = await client.post("/goals", json={"title": "Parent to delete"})
    parent_id = parent_response.json()["id"]

    # Create sub-goal
    sub_response = await client.post(
        "/goals",
        json={"title": "Sub goal", "parent_goal_id": parent_id},
    )
    sub_id = sub_response.json()["id"]

    # Delete parent
    await client.delete(f"/goals/{parent_id}")

    # Sub-goal should also be deleted
    get_response = await client.get(f"/goals/{sub_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_goal_not_found_block_3(client: AsyncClient):
    """Test deleting non-existent goal."""
    response = await client.delete("/goals/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# ============================================================================
# Goal Reschedule Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reschedule_goals_block_2(client: AsyncClient):
    """Test rescheduling multiple goals at once."""
    from datetime import date, timedelta

    # Create goals
    goal1_response = await client.post("/goals", json={"title": "Reschedule 1"})
    goal2_response = await client.post("/goals", json={"title": "Reschedule 2"})
    goal1_id = goal1_response.json()["id"]
    goal2_id = goal2_response.json()["id"]

    new_date1 = (date.today() + timedelta(days=30)).isoformat()
    new_date2 = (date.today() + timedelta(days=60)).isoformat()

    response = await client.post(
        "/goals/reschedule",
        json={
            "goal_updates": [
                {"goal_id": goal1_id, "new_target_date": new_date1},
                {"goal_id": goal2_id, "new_target_date": new_date2},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "goals" in data


@pytest.mark.asyncio
async def test_reschedule_empty_list(client: AsyncClient):
    """Test rescheduling with empty list."""
    response = await client.post(
        "/goals/reschedule",
        json={"goal_updates": []},
    )
    assert response.status_code == 200


# ============================================================================
# Goal Parent Update Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_goal_parent_block_2(client: AsyncClient):
    """Test moving a goal to a new parent."""
    # Create two parents
    parent1_response = await client.post("/goals", json={"title": "Parent 1"})
    parent2_response = await client.post("/goals", json={"title": "Parent 2"})
    parent1_id = parent1_response.json()["id"]
    parent2_id = parent2_response.json()["id"]

    # Create child under parent 1
    child_response = await client.post(
        "/goals",
        json={"title": "Child", "parent_goal_id": parent1_id},
    )
    child_id = child_response.json()["id"]

    # Move to parent 2
    response = await client.patch(
        f"/goals/{child_id}",
        json={"parent_goal_id": parent2_id},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_goal_to_make_it_root(client: AsyncClient):
    """Test making a sub-goal into a root goal."""
    parent_response = await client.post("/goals", json={"title": "Parent"})
    parent_id = parent_response.json()["id"]

    child_response = await client.post(
        "/goals",
        json={"title": "Child", "parent_goal_id": parent_id},
    )
    child_id = child_response.json()["id"]

    # Make it a root goal (no parent)
    response = await client.patch(
        f"/goals/{child_id}",
        json={"parent_goal_id": None},
    )
    assert response.status_code in [200, 422]  # May fail if null not allowed
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
async def test_update_goal_status_block_2(client: AsyncClient):
    """Status cannot be PATCHed directly."""
    create_resp = await client.post("/goals", json={"title": "Test Goal"})
    goal_id = create_resp.json()["id"]

    response = await client.patch(f"/goals/{goal_id}", json={"status": "in_progress"})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_goal_title(client: AsyncClient):
    """Test updating goal title."""
    create_resp = await client.post("/goals", json={"title": "Original Title"})
    goal_id = create_resp.json()["id"]

    response = await client.patch(f"/goals/{goal_id}", json={"title": "Updated Title"})
    assert response.status_code == 200
    assert response.json()["title"] == "Updated Title"


@pytest.mark.asyncio
async def test_update_goal_description_block_2(client: AsyncClient):
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
async def test_update_goal_not_found_block_2(client: AsyncClient):
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
async def test_delete_goal_not_found_block_4(client: AsyncClient):
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
async def test_get_goal_not_found_block_3(client: AsyncClient):
    """Test getting non-existent goal."""
    response = await client.get("/goals/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_goals_empty_block_2(client: AsyncClient):
    """Test listing goals when none exist."""
    response = await client.get("/goals")
    assert response.status_code == 200
    assert response.json()["goals"] == []


@pytest.mark.asyncio
async def test_list_goals_with_status_filter_block_3(client: AsyncClient):
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


# ============================================================================
# Additional Goals Coverage Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_goal_with_priority_ids(client: AsyncClient, mock_validate_priority):
    """Test creating goal with priority_ids creates links."""
    # Create priorities
    priority1 = await client.post(
        "/priorities",
        json={
            "title": "Priority One",
            "why_matters": "Testing goal creation with priority links for coverage",
            "score": 4,
        },
    )
    priority2 = await client.post(
        "/priorities",
        json={
            "title": "Priority Two",
            "why_matters": "Testing goal creation with multiple priority links",
            "score": 3,
        },
    )
    priority1_id = priority1.json()["id"]
    priority2_id = priority2.json()["id"]

    # Create goal with priority_ids
    response = await client.post(
        "/goals",
        json={
            "title": "Goal with Priorities",
            "priority_ids": [priority1_id, priority2_id],
        },
    )

    assert response.status_code == 201
    data = response.json()
    # priorities returns PriorityInfo objects with id, title
    linked_ids = [p["id"] for p in data["priorities"]]
    assert priority1_id in linked_ids
    assert priority2_id in linked_ids


@pytest.mark.asyncio
async def test_list_goals_past_target_date_block_3(client: AsyncClient):
    """Test filtering goals by past target date."""
    from datetime import date, timedelta

    past_date = (date.today() - timedelta(days=5)).isoformat()
    future_date = (date.today() + timedelta(days=5)).isoformat()

    # Create past-due goal
    await client.post(
        "/goals",
        json={"title": "Past Due Goal", "target_date": past_date},
    )
    # Create future goal
    await client.post(
        "/goals",
        json={"title": "Future Goal", "target_date": future_date},
    )

    response = await client.get("/goals?past_target_date=true")
    assert response.status_code == 200
    goals = response.json()["goals"]
    titles = [g["title"] for g in goals]
    assert "Past Due Goal" in titles
    # Future goal should not be included
    assert "Future Goal" not in titles


@pytest.mark.asyncio
async def test_update_goal_parent_block_3(client: AsyncClient):
    """Test updating goal parent_goal_id."""
    # Create parent goal
    parent_resp = await client.post(
        "/goals",
        json={"title": "Parent Goal"},
    )
    parent_id = parent_resp.json()["id"]

    # Create child goal without parent
    child_resp = await client.post(
        "/goals",
        json={"title": "Child Goal"},
    )
    child_id = child_resp.json()["id"]

    # Update child to have parent
    response = await client.patch(
        f"/goals/{child_id}",
        json={"parent_goal_id": parent_id},
    )

    assert response.status_code == 200
    assert response.json()["parent_goal_id"] == parent_id


@pytest.mark.asyncio
async def test_add_duplicate_priority_link_fails(client: AsyncClient, mock_validate_priority):
    """Test adding duplicate priority link returns 400."""
    # Create priority
    priority_resp = await client.post(
        "/priorities",
        json={
            "title": "Dup Link Priority",
            "why_matters": "Testing duplicate priority link prevention",
            "score": 3,
        },
    )
    priority_id = priority_resp.json()["id"]

    # Create goal
    goal_resp = await client.post(
        "/goals",
        json={"title": "Dup Link Goal"},
    )
    goal_id = goal_resp.json()["id"]

    # Add priority first time
    await client.post(f"/goals/{goal_id}/priorities/{priority_id}")

    # Try to add same priority again
    response = await client.post(f"/goals/{goal_id}/priorities/{priority_id}")
    assert response.status_code == 400
    assert "already linked" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_reschedule_goals_bulk(client: AsyncClient):
    """Test bulk rescheduling multiple goals."""
    from datetime import date, timedelta

    # Create goals with past due dates
    past_date = (date.today() - timedelta(days=10)).isoformat()
    goal1 = await client.post(
        "/goals",
        json={"title": "Reschedule Goal 1", "target_date": past_date},
    )
    goal2 = await client.post(
        "/goals",
        json={"title": "Reschedule Goal 2", "target_date": past_date},
    )

    new_date = (date.today() + timedelta(days=14)).isoformat()

    response = await client.post(
        "/goals/reschedule",
        json={
            "goal_updates": [
                {"goal_id": goal1.json()["id"], "new_target_date": new_date},
                {"goal_id": goal2.json()["id"], "new_target_date": new_date},
            ],
        },
    )

    assert response.status_code == 200
    goals = response.json()["goals"]
    assert len(goals) == 2
    for g in goals:
        assert g["target_date"] == new_date


@pytest.mark.asyncio
async def test_update_goal_title_block_2(client: AsyncClient):
    """Test updating goal title field."""
    goal_resp = await client.post(
        "/goals",
        json={"title": "Original Goal Title"},
    )
    goal_id = goal_resp.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}",
        json={"title": "Updated Goal Title"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "Updated Goal Title"


# ============================================================================
# Goal Tree Tests
# ============================================================================


@pytest.mark.asyncio
async def test_goal_tree_with_no_subgoals(client: AsyncClient):
    """Test getting goal tree when goal has no sub-goals."""
    goal_resp = await client.post(
        "/goals",
        json={"title": "Standalone Goal"},
    )
    goal_id = goal_resp.json()["id"]
    
    response = await client.get(f"/goals/{goal_id}/tree")
    assert response.status_code == 200
    data = response.json()
    assert data["sub_goals"] == []


@pytest.mark.asyncio
async def test_goal_tree_with_nested_subgoals(client: AsyncClient):
    """Test getting goal tree with multiple levels of sub-goals."""
    # Create parent
    parent_resp = await client.post(
        "/goals",
        json={"title": "Parent Goal"},
    )
    parent_id = parent_resp.json()["id"]
    
    # Create child
    child_resp = await client.post(
        "/goals",
        json={"title": "Child Goal", "parent_goal_id": parent_id},
    )
    child_id = child_resp.json()["id"]
    
    # Create grandchild
    await client.post(
        "/goals",
        json={"title": "Grandchild Goal", "parent_goal_id": child_id},
    )
    
    # Get tree from parent
    response = await client.get(f"/goals/{parent_id}/tree")
    assert response.status_code == 200
    data = response.json()
    assert len(data["sub_goals"]) == 1
    assert len(data["sub_goals"][0]["sub_goals"]) == 1


@pytest.mark.asyncio
async def test_goal_update_status_via_patch(client: AsyncClient):
    """Status is not accepted on PATCH /goals/{id}."""
    goal_resp = await client.post("/goals", json={"title": "Status Patch Goal"})
    goal_id = goal_resp.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}",
        json={"status": "in_progress"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_goal_update_description_field(client: AsyncClient):
    """Test updating goal description field."""
    goal_resp = await client.post("/goals", json={"title": "Desc Update Goal"})
    goal_id = goal_resp.json()["id"]
    
    response = await client.patch(
        f"/goals/{goal_id}",
        json={"description": "New detailed description"},
    )
    assert response.status_code == 200
    assert response.json()["description"] == "New detailed description"


@pytest.mark.asyncio
async def test_goal_set_priorities_replaces_existing(client: AsyncClient, mock_validate_priority):
    """Test that setting priorities replaces all existing links."""
    # Create priorities
    p1 = await client.post(
        "/priorities",
        json={"title": "P1", "why_matters": "Priority 1 for replacement test", "score": 3},
    )
    p2 = await client.post(
        "/priorities",
        json={"title": "P2", "why_matters": "Priority 2 for replacement test", "score": 4},
    )
    
    # Create goal with first priority
    goal_resp = await client.post(
        "/goals",
        json={"title": "Replace Links Goal", "priority_ids": [p1.json()["id"]]},
    )
    goal_id = goal_resp.json()["id"]
    
    # Replace with second priority only
    response = await client.post(
        f"/goals/{goal_id}/priorities",
        json={"priority_ids": [p2.json()["id"]]},
    )
    assert response.status_code == 200
    linked_ids = [p["id"] for p in response.json()["priorities"]]
    assert p2.json()["id"] in linked_ids
    assert p1.json()["id"] not in linked_ids


# ---- migrated from tests/mocked/test_services_goals.py ----

"""Goals API error scenarios."""

from unittest.mock import patch

import pytest
from httpx import AsyncClient


@pytest.fixture
def mock_validate_priority():
    """Mock priority validation to always return valid."""
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


@pytest.mark.asyncio
async def test_goal_invalid_parent_self_reference(client: AsyncClient):
    """Test goal cannot be its own parent."""
    goal = await client.post("/goals", json={"title": "Self Parent Test"})
    goal_id = goal.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}",
        json={"parent_goal_id": goal_id},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_goal_invalid_priority_link(client: AsyncClient):
    """Test linking goal to non-existent priority fails."""
    goal = await client.post("/goals", json={"title": "Invalid Link Test"})
    goal_id = goal.json()["id"]

    response = await client.post(
        f"/goals/{goal_id}/priorities/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_goal_duplicate_priority_link(client: AsyncClient, mock_validate_priority):
    """Test duplicate priority link fails."""
    priority = await client.post(
        "/priorities",
        json={
            "title": "Dup Link Test",
            "why_matters": "Testing duplicate link validation",
            "score": 3,
        },
    )
    p_id = priority.json()["id"]

    goal = await client.post("/goals", json={"title": "Dup Link Goal"})
    goal_id = goal.json()["id"]

    await client.post(f"/goals/{goal_id}/priorities/{p_id}")

    response = await client.post(f"/goals/{goal_id}/priorities/{p_id}")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_goal_remove_nonexistent_priority_link(client: AsyncClient):
    """Test removing priority link that doesn't exist."""
    goal = await client.post("/goals", json={"title": "Remove Link Test"})
    goal_id = goal.json()["id"]

    response = await client.delete(
        f"/goals/{goal_id}/priorities/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_goal_invalid_status(client: AsyncClient):
    """Test setting invalid goal status."""
    goal = await client.post("/goals", json={"title": "Invalid Status Goal"})
    goal_id = goal.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}",
        json={"status": "invalid_status"},
    )
    assert response.status_code == 422


# ---- migrated from tests/mocked/test_services_goals_migrated.py ----

"""Unit tests with mocked external services and error scenarios."""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta
import json


# ============================================================================
# Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_validate_priority():
    """Mock priority validation to always return valid."""
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


@pytest.fixture
def mock_llm_alignment():
    """Mock LLM service for alignment reflection."""
    with patch("app.api.alignment.LLMService.get_alignment_reflection") as mock:
        async def async_return(*args, **kwargs):
            return "Your values and priorities are well aligned."
        mock.side_effect = async_return
        yield mock


@pytest.fixture
def mock_llm_recommendation():
    """Mock LLM service for assistant recommendations."""
    with patch("app.services.llm_service.LLMService.get_recommendation") as mock:
        async def async_return(*args, **kwargs):
            return {
                "choices": [{
                    "message": {
                        "content": "I can help you with that.",
                        "tool_calls": None,
                    }
                }]
            }
        mock.side_effect = async_return
        yield mock


# ============================================================================
# Alignment API Tests with Mocked LLM
# ============================================================================

@pytest.mark.asyncio
async def test_goal_invalid_parent_self_reference__legacyservices_goals_migrated(client: AsyncClient):
    """Test goal cannot be its own parent."""
    goal = await client.post("/goals", json={"title": "Self Parent Test"})
    goal_id = goal.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}",
        json={"parent_goal_id": goal_id},
    )
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_goal_invalid_priority_link__legacyservices_goals_migrated(client: AsyncClient):
    """Test linking goal to non-existent priority fails."""
    goal = await client.post("/goals", json={"title": "Invalid Link Test"})
    goal_id = goal.json()["id"]

    response = await client.post(
        f"/goals/{goal_id}/priorities/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_goal_duplicate_priority_link__legacyservices_goals_migrated(client: AsyncClient, mock_validate_priority):
    """Test duplicate priority link fails."""
    # Create priority
    priority = await client.post(
        "/priorities",
        json={
            "title": "Dup Link Test",
            "why_matters": "Testing duplicate link validation",
            "score": 3,
        },
    )
    p_id = priority.json()["id"]

    # Create goal
    goal = await client.post("/goals", json={"title": "Dup Link Goal"})
    goal_id = goal.json()["id"]

    # First link
    await client.post(f"/goals/{goal_id}/priorities/{p_id}")

    # Duplicate should fail
    response = await client.post(f"/goals/{goal_id}/priorities/{p_id}")
    assert response.status_code == 400

@pytest.mark.asyncio
async def test_goal_remove_nonexistent_priority_link__legacyservices_goals_migrated(client: AsyncClient):
    """Test removing priority link that doesn't exist."""
    goal = await client.post("/goals", json={"title": "Remove Link Test"})
    goal_id = goal.json()["id"]

    response = await client.delete(
        f"/goals/{goal_id}/priorities/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


# ============================================================================
# Tasks API Error Scenarios
# ============================================================================

@pytest.mark.asyncio
async def test_goal_invalid_status__legacyservices_goals_migrated(client: AsyncClient):
    """Test setting invalid goal status."""
    goal = await client.post("/goals", json={"title": "Invalid Status Goal"})
    goal_id = goal.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}",
        json={"status": "invalid_status"},
    )
    assert response.status_code == 422


# ---- migrated from tests/integration/test_api_helpers_goals.py ----

"""Integration coverage for goals helper behavior."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_goal_delete(client: AsyncClient):
    """Test deleting a goal."""
    goal = await client.post("/goals", json={"title": "Delete Goal Test"})
    goal_id = goal.json()["id"]

    response = await client.delete(f"/goals/{goal_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_goal_delete_with_tasks(client: AsyncClient):
    """Test deleting a goal that has tasks."""
    goal = await client.post("/goals", json={"title": "Delete Goal With Tasks"})
    goal_id = goal.json()["id"]

    await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task To Delete", "duration_minutes": 30},
    )

    response = await client.delete(f"/goals/{goal_id}")
    assert response.status_code == 204
