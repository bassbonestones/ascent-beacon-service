"""Tests for goals API endpoints."""

import pytest
from datetime import date, timedelta
from httpx import AsyncClient

from app.models.user import User


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
    await client.patch(f"/goals/{goal_id}/status", json={"status": "completed"})

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
    await client.patch(f"/goals/{goal_id}/status", json={"status": "completed"})

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
async def test_update_goal_status(client: AsyncClient):
    """Test updating just the goal status."""
    create_response = await client.post("/goals", json={"title": "My Goal"})
    goal_id = create_response.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}/status",
        json={"status": "in_progress"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_complete_goal_sets_completed_at(client: AsyncClient):
    """Test that completing a goal sets completed_at timestamp."""
    create_response = await client.post("/goals", json={"title": "My Goal"})
    goal_id = create_response.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}/status",
        json={"status": "completed"},
    )

    assert response.status_code == 200
    assert response.json()["completed_at"] is not None


@pytest.mark.asyncio
async def test_uncomplete_goal_clears_completed_at(client: AsyncClient):
    """Test that uncompleting a goal clears completed_at timestamp."""
    create_response = await client.post("/goals", json={"title": "My Goal"})
    goal_id = create_response.json()["id"]

    # Complete
    await client.patch(f"/goals/{goal_id}/status", json={"status": "completed"})

    # Uncomplete
    response = await client.patch(
        f"/goals/{goal_id}/status",
        json={"status": "in_progress"},
    )

    assert response.json()["completed_at"] is None


@pytest.mark.asyncio
async def test_update_goal_invalid_status(client: AsyncClient):
    """Test that invalid status is rejected."""
    create_response = await client.post("/goals", json={"title": "My Goal"})
    goal_id = create_response.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}",
        json={"status": "invalid_status"},
    )

    assert response.status_code == 400


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
