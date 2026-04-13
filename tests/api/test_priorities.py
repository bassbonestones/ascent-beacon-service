"""Tests for priorities API endpoints."""

import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

from app.models.user import User


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


@pytest.mark.asyncio
async def test_create_priority(client: AsyncClient, test_user: User, mock_validate_priority):
    """Test creating a new priority."""
    response = await client.post(
        "/priorities",
        json={
            "title": "Exercise regularly",
            "why_matters": "Physical health supports mental clarity and energy for all my goals",
            "score": 4,
            "scope": "ongoing",
        },
    )
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["user_id"] == test_user.id
    assert data["active_revision_id"] is not None
    assert data["active_revision"]["title"] == "Exercise regularly"
    assert data["active_revision"]["score"] == 4
    assert data["active_revision"]["is_anchored"] is False


@pytest.mark.asyncio
async def test_create_priority_validation_fails(client: AsyncClient):
    """Test that invalid priority is rejected."""
    with patch("app.api.priorities.validate_priority") as mock:
        mock.return_value = {
            "overall_valid": False,
            "name_valid": False,
            "why_valid": False,
            "name_feedback": ["Name too vague"],
            "why_feedback": ["Why statement needs more substance"],
            "why_passed_rules": {"specificity": False, "actionable": False},
            "name_rewrite": None,
            "why_rewrite": None,
            "rule_examples": None,
        }
        
        response = await client.post(
            "/priorities",
            json={
                "title": "Do stuff",
                "why_matters": "Just because I want to do it",
                "score": 3,
            },
        )
        
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_priorities_empty(client: AsyncClient):
    """Test listing priorities when user has none."""
    response = await client.get("/priorities")
    
    assert response.status_code == 200
    assert response.json() == {"priorities": []}


@pytest.mark.asyncio
async def test_list_priorities_with_data(client: AsyncClient, mock_validate_priority):
    """Test listing priorities returns all user priorities."""
    # Create two priorities
    await client.post(
        "/priorities",
        json={
            "title": "First priority",
            "why_matters": "This is the first priority and it matters a lot to me",
            "score": 4,
        },
    )
    await client.post(
        "/priorities",
        json={
            "title": "Second priority", 
            "why_matters": "This is the second priority and it also matters to me",
            "score": 3,
        },
    )
    
    response = await client.get("/priorities")
    
    assert response.status_code == 200
    priorities = response.json()["priorities"]
    assert len(priorities) == 2


@pytest.mark.asyncio
async def test_get_priority_history(client: AsyncClient, mock_validate_priority):
    """Test getting revision history for a priority."""
    # Create a priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Original title",
            "why_matters": "Original why statement that is long enough for validation",
            "score": 3,
        },
    )
    priority_id = create_response.json()["id"]
    
    # Update it to create a new revision
    await client.post(
        f"/priorities/{priority_id}/revisions",
        json={
            "title": "Updated title",
            "why_matters": "Updated why statement that is also long enough for validation",
            "score": 4,
        },
    )
    
    # Get history
    response = await client.get(f"/priorities/{priority_id}/history")
    
    assert response.status_code == 200
    history = response.json()
    
    # Should have 2 revisions
    assert len(history) == 2


@pytest.mark.asyncio
async def test_get_priority_history_not_found(client: AsyncClient):
    """Test getting history for non-existent priority."""
    response = await client.get("/priorities/nonexistent-id/history")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_priority(client: AsyncClient, mock_validate_priority):
    """Test deleting a priority."""
    # Create a priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "To be deleted",
            "why_matters": "This priority will be deleted to test deletion",
            "score": 2,
        },
    )
    priority_id = create_response.json()["id"]
    
    # Delete it
    delete_response = await client.delete(f"/priorities/{priority_id}")
    assert delete_response.status_code == 204
    
    # Verify it's gone
    list_response = await client.get("/priorities")
    priority_ids = [p["id"] for p in list_response.json()["priorities"]]
    assert priority_id not in priority_ids


@pytest.mark.asyncio
async def test_delete_priority_not_found(client: AsyncClient):
    """Test deleting non-existent priority."""
    response = await client.delete("/priorities/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_anchor_priority(client: AsyncClient, mock_validate_priority):
    """Test anchoring a priority."""
    # Create a priority (starts unanchored)
    create_response = await client.post(
        "/priorities",
        json={
            "title": "To be anchored",
            "why_matters": "This priority will be anchored to test anchoring",
            "score": 4,
        },
    )
    priority_id = create_response.json()["id"]
    assert create_response.json()["active_revision"]["is_anchored"] is False
    
    # Anchor it
    anchor_response = await client.post(f"/priorities/{priority_id}/anchor")
    assert anchor_response.status_code == 200
    assert anchor_response.json()["active_revision"]["is_anchored"] is True


@pytest.mark.asyncio
async def test_unanchor_priority(client: AsyncClient, mock_validate_priority):
    """Test unanchoring a priority."""
    # Create and anchor a priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "To be unanchored",
            "why_matters": "This priority will be anchored then unanchored for testing",
            "score": 4,
        },
    )
    priority_id = create_response.json()["id"]
    await client.post(f"/priorities/{priority_id}/anchor")
    
    # Unanchor it
    unanchor_response = await client.post(f"/priorities/{priority_id}/unanchor")
    assert unanchor_response.status_code == 200
    assert unanchor_response.json()["active_revision"]["is_anchored"] is False


@pytest.mark.asyncio
async def test_stash_priority(client: AsyncClient, mock_validate_priority):
    """Test stashing a priority."""
    # Create a priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "To be stashed",
            "why_matters": "This priority will be stashed to test stashing",
            "score": 3,
        },
    )
    priority_id = create_response.json()["id"]
    
    # Stash it (StashPriorityRequest uses is_stashed bool)
    stash_response = await client.post(
        f"/priorities/{priority_id}/stash",
        json={"is_stashed": True}
    )
    assert stash_response.status_code == 200
    
    # Should not appear in regular list
    list_response = await client.get("/priorities")
    priority_ids = [p["id"] for p in list_response.json()["priorities"]]
    assert priority_id not in priority_ids
    
    # Should appear in stashed list
    stashed_response = await client.get("/priorities/stashed")
    stashed_ids = [p["id"] for p in stashed_response.json()["priorities"]]
    assert priority_id in stashed_ids


@pytest.mark.asyncio
async def test_priority_with_linked_value(client: AsyncClient, mock_validate_priority):
    """Test creating a priority linked to a value."""
    # First create a value
    value_response = await client.post(
        "/values",
        json={
            "statement": "I value my health",
            "weight_raw": 50,
            "origin": "declared",
        },
    )
    value_id = value_response.json()["id"]
    
    # Create priority linked to that value
    priority_response = await client.post(
        "/priorities",
        json={
            "title": "Exercise daily",
            "why_matters": "Supporting my value of health by moving my body every day",
            "score": 4,
            "value_ids": [value_id],
        },
    )
    
    assert priority_response.status_code == 201
    data = priority_response.json()
    
    # Check value link exists
    value_links = data["active_revision"]["value_links"]
    assert len(value_links) == 1
    assert value_links[0]["value_id"] == value_id


@pytest.mark.asyncio
async def test_validate_priority_endpoint(client: AsyncClient):
    """Test the priority validation endpoint directly."""
    with patch("app.api.priorities.validate_priority") as mock:
        mock.return_value = {
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
        
        response = await client.post(
            "/priorities/validate",
            json={
                "name": "Learn Spanish",
                "why_statement": "Being able to communicate in Spanish opens up opportunities",
            },
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["overall_valid"] is True


@pytest.mark.asyncio
async def test_score_boundaries(client: AsyncClient, mock_validate_priority):
    """Test that score field is validated (1-5 range)."""
    # Score of 1 should work
    response = await client.post(
        "/priorities",
        json={
            "title": "Low score priority",
            "why_matters": "This is a priority with the minimum score value",
            "score": 1,
        },
    )
    assert response.status_code == 201
    
    # Score of 5 should work
    response = await client.post(
        "/priorities",
        json={
            "title": "High score priority",
            "why_matters": "This is a priority with the maximum score value",
            "score": 5,
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_priority_check_status(client: AsyncClient, mock_validate_priority):
    """Test checking priority status."""
    # Create a priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Status check priority",
            "why_matters": "This priority will be used to test status checking",
            "score": 3,
        },
    )
    priority_id = create_response.json()["id"]
    
    # Check status
    response = await client.get(f"/priorities/{priority_id}/check-status")
    
    assert response.status_code == 200
    data = response.json()
    # Verify expected fields from PriorityCheckResponse
    assert "status" in data
    assert "priority_id" in data
    assert "has_linked_values" in data
    assert data["priority_id"] == priority_id


@pytest.mark.asyncio
async def test_priority_check_status_with_linked_value(client: AsyncClient, mock_validate_priority):
    """Test checking priority status when priority has linked values."""
    # Create a value first
    value_response = await client.post(
        "/values",
        json={"statement": "I value health", "weight_raw": 50, "origin": "declared"},
    )
    value_id = value_response.json()["id"]
    
    # Create a priority linked to that value
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Exercise regularly",
            "why_matters": "Supporting my health value through daily movement",
            "score": 4,
            "value_ids": [value_id],
        },
    )
    priority_id = create_response.json()["id"]
    
    # Check status
    response = await client.get(f"/priorities/{priority_id}/check-status")
    
    assert response.status_code == 200
    data = response.json()
    assert data["has_linked_values"] is True
    assert data["linked_value_count"] == 1
    assert data["status"] == "complete"


@pytest.mark.asyncio
async def test_priority_check_status_not_found(client: AsyncClient):
    """Test checking status of non-existent priority."""
    response = await client.get("/priorities/nonexistent-id/check-status")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_anchor_priority_not_found(client: AsyncClient):
    """Test anchoring non-existent priority."""
    response = await client.post("/priorities/nonexistent-id/anchor")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unanchor_priority_not_found(client: AsyncClient):
    """Test unanchoring non-existent priority."""
    response = await client.post("/priorities/nonexistent-id/unanchor")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_stash_priority_not_found(client: AsyncClient):
    """Test stashing non-existent priority."""
    response = await client.post(
        "/priorities/nonexistent-id/stash",
        json={"is_stashed": True}
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unstash_priority(client: AsyncClient, mock_validate_priority):
    """Test unstashing a stashed priority."""
    # Create a priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "To be unstashed",
            "why_matters": "This priority will be stashed and then unstashed",
            "score": 3,
        },
    )
    priority_id = create_response.json()["id"]
    
    # Stash it
    await client.post(f"/priorities/{priority_id}/stash", json={"is_stashed": True})
    
    # Unstash it
    unstash_response = await client.post(
        f"/priorities/{priority_id}/stash",
        json={"is_stashed": False}
    )
    assert unstash_response.status_code == 200
    
    # Should appear in regular list
    list_response = await client.get("/priorities")
    priority_ids = [p["id"] for p in list_response.json()["priorities"]]
    assert priority_id in priority_ids


@pytest.mark.asyncio
async def test_create_revision_with_value_link(client: AsyncClient, mock_validate_priority):
    """Test creating a new revision with value links."""
    # Create a value
    value_response = await client.post(
        "/values",
        json={"statement": "I value creativity", "weight_raw": 50, "origin": "declared"},
    )
    value_id = value_response.json()["id"]
    
    # Create a priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Practice art",
            "why_matters": "Expressing myself through creative activities",
            "score": 3,
        },
    )
    priority_id = create_response.json()["id"]
    
    # Create revision with linked value
    revision_response = await client.post(
        f"/priorities/{priority_id}/revisions",
        json={
            "title": "Practice digital art",
            "why_matters": "Expressing creativity through digital medium specifically",
            "score": 4,
            "value_ids": [value_id],
        },
    )
    
    assert revision_response.status_code == 200
    data = revision_response.json()
    assert len(data["active_revision"]["value_links"]) == 1


@pytest.mark.asyncio
async def test_create_revision_not_found(client: AsyncClient, mock_validate_priority):
    """Test creating revision for non-existent priority."""
    response = await client.post(
        "/priorities/nonexistent-id/revisions",
        json={
            "title": "New revision",
            "why_matters": "This should fail because priority doesn't exist",
            "score": 3,
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_orphaned_anchor_error(client: AsyncClient, mock_validate_priority):
    """Test that orphaning an anchored priority fails."""
    # Create a value
    value_response = await client.post(
        "/values",
        json={"statement": "I value learning", "weight_raw": 50, "origin": "declared"},
    )
    value_id = value_response.json()["id"]
    
    # Create priority with linked value
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Learn daily",
            "why_matters": "Continuous learning supports my growth and development",
            "score": 4,
            "value_ids": [value_id],
        },
    )
    priority_id = create_response.json()["id"]
    
    # Anchor the priority
    await client.post(f"/priorities/{priority_id}/anchor")
    
    # Try to create revision without any values (orphaning)
    response = await client.post(
        f"/priorities/{priority_id}/revisions",
        json={
            "title": "Updated without values",
            "why_matters": "This should fail because anchored priority needs values",
            "score": 4,
            "value_ids": [],
        },
    )
    
    assert response.status_code == 400
    assert "orphan" in response.json()["detail"]["error"].lower()


@pytest.mark.asyncio
async def test_list_stashed_priorities_empty(client: AsyncClient):
    """Test listing stashed priorities when none are stashed."""
    response = await client.get("/priorities/stashed")
    assert response.status_code == 200
    assert response.json() == {"priorities": []}


# ============================================================================
# Additional Coverage Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_stashed_priorities_with_data(client: AsyncClient, mock_validate_priority):
    """Test listing stashed priorities when some exist."""
    # Create and stash a priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Stash Test Priority",
            "why_matters": "Test stashing functionality properly",
            "score": 3,
        },
    )
    priority_id = create_response.json()["id"]
    
    # Stash it (requires is_stashed body)
    await client.post(f"/priorities/{priority_id}/stash", json={"is_stashed": True})

    # List stashed
    response = await client.get("/priorities/stashed")
    assert response.status_code == 200
    stashed = response.json()["priorities"]
    assert len(stashed) == 1
    assert stashed[0]["id"] == priority_id


@pytest.mark.asyncio
async def test_update_priority_score(client: AsyncClient, mock_validate_priority):
    """Test updating priority score via revision."""
    # Create priority
    create_response = await client.post(
        "/priorities",
        json={"title": "Score Test", "why_matters": "Testing score changes nicely", "score": 3},
    )
    priority_id = create_response.json()["id"]

    # Create revision with different score
    update_response = await client.post(
        f"/priorities/{priority_id}/revisions",
        json={"title": "Score Test", "why_matters": "Updated testing score nicely", "score": 5},
    )
    
    assert update_response.status_code == 200
    assert update_response.json()["active_revision"]["score"] == 5


@pytest.mark.asyncio
async def test_priority_has_linked_values(client: AsyncClient, mock_validate_priority):
    """Test that priority includes linked values in response."""
    # Create a value
    value_response = await client.post(
        "/values",
        json={"statement": "I value health and wellbeing", "weight_raw": 50, "origin": "declared"},
    )
    value_id = value_response.json()["id"]

    # Create priority linked to value
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Exercise daily",
            "why_matters": "Supports health and wellbeing goals",
            "score": 4,
            "value_ids": [value_id],
        },
    )
    
    assert create_response.status_code == 201
    # Priority should have linked values in active_revision
    revision = create_response.json()["active_revision"]
    assert len(revision["value_links"]) == 1


@pytest.mark.asyncio
async def test_priority_linked_values_not_found(client: AsyncClient):
    """Test getting linked values for non-existent priority."""
    response = await client.get("/priorities/nonexistent-id/linked-values")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unstash_priority_not_found(client: AsyncClient):
    """Test unstashing non-existent priority."""
    response = await client.post("/priorities/nonexistent-id/unstash")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_priority_with_multiple_values(client: AsyncClient, mock_validate_priority):
    """Test creating priority linked to multiple values."""
    # Create values
    value1_response = await client.post(
        "/values",
        json={"statement": "Value 1 - integrity and honesty", "weight_raw": 50, "origin": "declared"},
    )
    value1_id = value1_response.json()["id"]
    
    value2_response = await client.post(
        "/values",
        json={"statement": "Value 2 - growth and learning", "weight_raw": 50, "origin": "declared"},
    )
    value2_id = value2_response.json()["id"]

    # Create priority with both values
    response = await client.post(
        "/priorities",
        json={
            "title": "Multi-value priority",
            "why_matters": "Linked to multiple related values",
            "score": 4,
            "value_ids": [value1_id, value2_id],
        },
    )
    
    assert response.status_code == 201
    revision = response.json()["active_revision"]
    assert len(revision["value_links"]) == 2


@pytest.mark.asyncio
async def test_anchor_already_anchored_priority(client: AsyncClient, mock_validate_priority):
    """Test anchoring an already anchored priority."""
    # Create value
    value_response = await client.post(
        "/values",
        json={"statement": "Value for anchor testing", "weight_raw": 50, "origin": "declared"},
    )
    value_id = value_response.json()["id"]

    # Create priority with value
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Anchor Test Priority",
            "why_matters": "Testing double anchor behavior",
            "score": 4,
            "value_ids": [value_id],
        },
    )
    priority_id = create_response.json()["id"]

    # Anchor
    await client.post(f"/priorities/{priority_id}/anchor")

    # Anchor again (should be idempotent)
    response = await client.post(f"/priorities/{priority_id}/anchor")
    assert response.status_code == 200


# ============================================================================
# Additional Priority Tests
# ============================================================================


@pytest.mark.asyncio
async def test_check_priority_status(client: AsyncClient, mock_validate_priority):
    """Test checking priority status."""
    # Create priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Check status test priority",
            "why_matters": "Testing checking priority status endpoint",
            "score": 3,
        },
    )
    priority_id = create_response.json()["id"]

    # Check status
    check_response = await client.get(f"/priorities/{priority_id}/check-status")
    assert check_response.status_code == 200
    assert check_response.json()["priority_id"] == priority_id


@pytest.mark.asyncio
async def test_check_priority_status_not_found(client: AsyncClient):
    """Test checking status for non-existent priority."""
    response = await client.get("/priorities/nonexistent-id/check-status")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unanchor_not_anchored_priority(client: AsyncClient, mock_validate_priority):
    """Test unanchoring a priority that isn't anchored."""
    # Create priority without value (can't anchor)
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Unanchor test priority",
            "why_matters": "Testing unanchoring behavior",
            "score": 3,
        },
    )
    priority_id = create_response.json()["id"]

    # Try to unanchor (already not anchored)
    response = await client.post(f"/priorities/{priority_id}/unanchor")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_stash_already_stashed_priority(client: AsyncClient, mock_validate_priority):
    """Test stashing an already stashed priority."""
    # Create and stash a priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Double stash test",
            "why_matters": "Testing double stash behavior",
            "score": 3,
        },
    )
    priority_id = create_response.json()["id"]
    
    # Stash it
    await client.post(f"/priorities/{priority_id}/stash", json={"is_stashed": True})

    # Stash again (should be idempotent)
    response = await client.post(f"/priorities/{priority_id}/stash", json={"is_stashed": True})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_priority_history_with_multiple_revisions(client: AsyncClient, mock_validate_priority):
    """Test getting history with multiple revisions."""
    # Create priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "History test v1",
            "why_matters": "First version of the priority for testing",
            "score": 2,
        },
    )
    priority_id = create_response.json()["id"]

    # Create second revision
    await client.post(
        f"/priorities/{priority_id}/revisions",
        json={
            "title": "History test v2",
            "why_matters": "Second version of the priority for testing",
            "score": 3,
        },
    )

    # Create third revision
    await client.post(
        f"/priorities/{priority_id}/revisions",
        json={
            "title": "History test v3",
            "why_matters": "Third version of the priority for testing",
            "score": 4,
        },
    )

    # Get history
    history_response = await client.get(f"/priorities/{priority_id}/history")
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 3


@pytest.mark.asyncio
async def test_anchor_priority_without_values_succeeds(client: AsyncClient, mock_validate_priority):
    """Test that anchoring a priority without values is allowed."""
    # Create priority without values
    create_response = await client.post(
        "/priorities",
        json={
            "title": "No values anchor test priority",
            "why_matters": "Testing anchor without linked values",
            "score": 3,
        },
    )
    priority_id = create_response.json()["id"]

    # Anchoring without values is allowed
    response = await client.post(f"/priorities/{priority_id}/anchor")
    assert response.status_code == 200
    assert response.json()["active_revision"]["is_anchored"] is True


@pytest.mark.asyncio
async def test_create_priority_with_invalid_score(client: AsyncClient, mock_validate_priority):
    """Test creating priority with out-of-range score."""
    response = await client.post(
        "/priorities",
        json={
            "title": "Invalid score test",
            "why_matters": "Testing invalid score values",
            "score": 10,  # Invalid - should be 1-5
        },
    )
    assert response.status_code == 422  # Validation error


# ============================================================================
# Priority Revision Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_revision_removes_values_unanchored(client: AsyncClient, mock_validate_priority):
    """Test creating revision without values is allowed for unanchored priority."""
    # Create priority with values
    value_response = await client.post(
        "/values",
        json={"statement": "Test value for revision unanchored", "weight_raw": 50, "origin": "declared"},
    )
    value_id = value_response.json()["id"]

    create_response = await client.post(
        "/priorities",
        json={
            "title": "Unanchored revision test priority",
            "why_matters": "Testing revision without values when unanchored allows flexibility",
            "score": 3,
            "value_ids": [value_id],
        },
    )
    priority_id = create_response.json()["id"]

    # Create revision without values (allowed when unanchored)
    revision_response = await client.post(
        f"/priorities/{priority_id}/revisions",
        json={
            "title": "Updated title revision unanchored",
            "why_matters": "Updated why matters statement with sufficient length for validation",
            "score": 4,
            "value_ids": [],
        },
    )
    assert revision_response.status_code == 200


@pytest.mark.asyncio
async def test_create_revision_removes_values_anchored_fails(client: AsyncClient, mock_validate_priority):
    """Test creating revision that orphans anchored priority fails."""
    # Create priority with values
    value_response = await client.post(
        "/values",
        json={"statement": "Test value for anchor orphan test", "weight_raw": 50, "origin": "declared"},
    )
    value_id = value_response.json()["id"]

    create_response = await client.post(
        "/priorities",
        json={
            "title": "Anchored orphan test priority",
            "why_matters": "Testing orphan prevention for anchored priorities",
            "score": 3,
            "value_ids": [value_id],
        },
    )
    priority_id = create_response.json()["id"]

    # Anchor the priority
    await client.post(f"/priorities/{priority_id}/anchor")

    # Try to create revision without values (should fail for anchored)
    revision_response = await client.post(
        f"/priorities/{priority_id}/revisions",
        json={
            "title": "Try to orphan this priority",
            "why_matters": "This should fail because we cant orphan anchored priority",
            "score": 4,
            "value_ids": [],
        },
    )
    assert revision_response.status_code == 400


# ============================================================================
# Unanchor Priority Tests
# ============================================================================


@pytest.mark.asyncio
async def test_unanchor_priority_block_2(client: AsyncClient, mock_validate_priority):
    """Test unanchoring a priority."""
    # Create and anchor priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Unanchor test priority statement",
            "why_matters": "Testing unanchor functionality with sufficient description",
            "score": 3,
        },
    )
    assert create_response.status_code == 201, f"Create failed: {create_response.json()}"
    priority_id = create_response.json()["id"]
    await client.post(f"/priorities/{priority_id}/anchor")

    # Unanchor
    response = await client.post(f"/priorities/{priority_id}/unanchor")
    assert response.status_code == 200
    assert response.json()["active_revision"]["is_anchored"] is False


@pytest.mark.asyncio
async def test_unanchor_priority_not_found_block_2(client: AsyncClient):
    """Test unanchoring non-existent priority."""
    response = await client.post("/priorities/00000000-0000-0000-0000-000000000000/unanchor")
    assert response.status_code == 404


# ============================================================================
# Delete Priority Tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_priority_block_2(client: AsyncClient, mock_validate_priority):
    """Test deleting a priority."""
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Delete test priority statement",
            "why_matters": "Testing delete functionality with sufficient description",
            "score": 3,
        },
    )
    assert create_response.status_code == 201, f"Create failed: {create_response.json()}"
    priority_id = create_response.json()["id"]

    # Delete it
    delete_response = await client.delete(f"/priorities/{priority_id}")
    assert delete_response.status_code == 204

    # Verify it's gone
    get_response = await client.get(f"/priorities/{priority_id}/check-status")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_priority_not_found_block_2(client: AsyncClient):
    """Test deleting non-existent priority."""
    response = await client.delete("/priorities/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# ============================================================================
# Priority Stash Tests
# ============================================================================


@pytest.mark.asyncio
async def test_stash_priority_block_2(client: AsyncClient, mock_validate_priority):
    """Test stashing a priority (POST with body)."""
    # Create priority
    response = await client.post(
        "/priorities",
        json={
            "title": "Priority to stash for later",
            "why_matters": "Testing stash functionality",
            "score": 3,
        },
    )
    priority_id = response.json()["id"]

    # Stash it (POST with body)
    stash_response = await client.post(
        f"/priorities/{priority_id}/stash",
        json={"is_stashed": True},
    )
    assert stash_response.status_code == 200


@pytest.mark.asyncio
async def test_stash_priority_not_found_block_2(client: AsyncClient):
    """Test stashing non-existent priority."""
    response = await client.post(
        "/priorities/00000000-0000-0000-0000-000000000000/stash",
        json={"is_stashed": True},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unstash_priority_block_2(client: AsyncClient, mock_validate_priority):
    """Test unstashing a priority (POST with is_stashed=False)."""
    # Create priority
    response = await client.post(
        "/priorities",
        json={
            "title": "Priority to unstash after stashing",
            "why_matters": "Testing unstash functionality",
            "score": 3,
        },
    )
    priority_id = response.json()["id"]

    # Stash then unstash
    await client.post(f"/priorities/{priority_id}/stash", json={"is_stashed": True})
    unstash_response = await client.post(
        f"/priorities/{priority_id}/stash",
        json={"is_stashed": False},
    )
    assert unstash_response.status_code == 200


# ============================================================================
# Priority Anchor/Unanchor Tests
# ============================================================================


@pytest.mark.asyncio
async def test_anchor_priority_block_2(client: AsyncClient, mock_validate_priority):
    """Test anchoring a priority."""
    # Create priority
    response = await client.post(
        "/priorities",
        json={
            "title": "Priority to anchor permanently",
            "why_matters": "Testing anchor functionality",
            "score": 3,
        },
    )
    priority_id = response.json()["id"]

    # Anchor it (POST)
    anchor_response = await client.post(f"/priorities/{priority_id}/anchor")
    assert anchor_response.status_code == 200
    # Check via active_revision
    data = anchor_response.json()
    if data.get("active_revision"):
        assert data["active_revision"]["is_anchored"] is True


@pytest.mark.asyncio
async def test_anchor_priority_not_found_block_2(client: AsyncClient):
    """Test anchoring non-existent priority."""
    response = await client.post("/priorities/00000000-0000-0000-0000-000000000000/anchor")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unanchor_priority_block_3(client: AsyncClient, mock_validate_priority):
    """Test unanchoring a priority."""
    # Create priority
    response = await client.post(
        "/priorities",
        json={
            "title": "Priority to unanchor after anchoring",
            "why_matters": "Testing unanchor functionality",
            "score": 3,
        },
    )
    priority_id = response.json()["id"]

    # Anchor then unanchor
    await client.post(f"/priorities/{priority_id}/anchor")
    unanchor_response = await client.post(f"/priorities/{priority_id}/unanchor")
    assert unanchor_response.status_code == 200
    # Check via active_revision
    data = unanchor_response.json()
    if data.get("active_revision"):
        assert data["active_revision"]["is_anchored"] is False


@pytest.mark.asyncio
async def test_unanchor_priority_not_found_block_3(client: AsyncClient):
    """Test unanchoring non-existent priority."""
    response = await client.post("/priorities/00000000-0000-0000-0000-000000000000/unanchor")
    assert response.status_code == 404


# ============================================================================
# Priority Revision Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_priority_revision(client: AsyncClient, mock_validate_priority):
    """Test creating a new revision for a priority."""
    # Create priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Original priority title",
            "why_matters": "Original reason for priority",
            "score": 3,
        },
    )
    priority_id = create_response.json()["id"]

    # Create revision
    revision_response = await client.post(
        f"/priorities/{priority_id}/revisions",
        json={
            "title": "Updated priority title",
            "why_matters": "Updated reason for priority",
            "score": 4,
        },
    )
    assert revision_response.status_code == 200


@pytest.mark.asyncio
async def test_create_priority_revision_not_found(client: AsyncClient, mock_validate_priority):
    """Test creating revision for non-existent priority."""
    response = await client.post(
        "/priorities/00000000-0000-0000-0000-000000000000/revisions",
        json={"title": "New title", "why_matters": "New reason for this priority", "score": 3},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_priority_history_block_2(client: AsyncClient, mock_validate_priority):
    """Test getting revision history for a priority."""
    # Create priority
    create_response = await client.post(
        "/priorities",
        json={
            "title": "Priority for revision history",
            "why_matters": "Version one of this priority",
            "score": 3,
        },
    )
    priority_id = create_response.json()["id"]

    # Create more revisions
    await client.post(
        f"/priorities/{priority_id}/revisions",
        json={"title": "Version Two", "why_matters": "Version two of this priority", "score": 3},
    )
    await client.post(
        f"/priorities/{priority_id}/revisions",
        json={"title": "Version Three", "why_matters": "Version three of this priority", "score": 3},
    )

    # Get history
    response = await client.get(f"/priorities/{priority_id}/history")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) >= 3


@pytest.mark.asyncio
async def test_get_priority_history_not_found_block_2(client: AsyncClient):
    """Test getting history for non-existent priority."""
    response = await client.get("/priorities/00000000-0000-0000-0000-000000000000/history")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_stashed_priorities(client: AsyncClient, mock_validate_priority):
    """Test that stashed priorities appear in /stashed endpoint."""
    # Create priority
    resp = await client.post(
        "/priorities",
        json={"title": "Priority to stash test", "why_matters": "Stash test priority functionality", "score": 3},
    )
    assert resp.status_code == 201
    priority_id = resp.json()["id"]

    # Stash it
    await client.post(f"/priorities/{priority_id}/stash", json={"is_stashed": True})

    # Check stashed endpoint
    stashed_response = await client.get("/priorities/stashed")
    assert stashed_response.status_code == 200
    priority_ids = [p["id"] for p in stashed_response.json()["priorities"]]
    assert priority_id in priority_ids


# ============================================================================
# Validation Endpoint Tests
# ============================================================================


@pytest.mark.asyncio
async def test_validate_priority_generic_name_rejected(client: AsyncClient):
    """Test that generic names like 'health' are rejected without LLM call."""
    response = await client.post(
        "/priorities/validate",
        json={"name": "health", "why_statement": "Because I want to be healthy"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name_valid"] is False
    assert len(data["name_feedback"]) > 0


@pytest.mark.asyncio
async def test_validate_priority_generic_career(client: AsyncClient):
    """Test that 'career' is rejected as too generic."""
    response = await client.post(
        "/priorities/validate",
        json={"name": "career", "why_statement": "Because work matters"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name_valid"] is False


@pytest.mark.asyncio
async def test_validate_priority_generic_family(client: AsyncClient):
    """Test that 'family' is rejected as too generic."""
    response = await client.post(
        "/priorities/validate",
        json={"name": "family", "why_statement": "Family is very important to me for many reasons"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["name_valid"] is False


@pytest.mark.asyncio
async def test_validate_priority_returns_overall_valid(client: AsyncClient):
    """Test that validation returns overall_valid field."""
    response = await client.post(
        "/priorities/validate",
        json={"name": "money", "why_statement": "I need financial security to protect my family from uncertainty"},
    )
    assert response.status_code == 200  
    data = response.json()
    assert "overall_valid" in data


@pytest.mark.asyncio
async def test_validate_priority_why_passed_rules(client: AsyncClient, mock_validate_priority):
    """Test that validation returns why_passed_rules."""
    response = await client.post(
        "/priorities/validate",
        json={
            "name": "Restoring physical health after burnout",
            "why_statement": "Because my energy has been depleted and I need to protect time for recovery",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "why_passed_rules" in data


# ============================================================================
# Priority with Value Links Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_priority_with_value_link(client: AsyncClient, mock_validate_priority):
    """Test creating a priority linked to a value."""
    # Create a value first
    value_response = await client.post(
        "/values",
        json={"statement": "I value physical vitality", "weight_raw": 50, "origin": "declared"},
    )
    value_id = value_response.json()["id"]

    # Create priority linked to value
    response = await client.post(
        "/priorities",
        json={
            "title": "Workout routine",
            "why_matters": "Because consistent exercise protects my energy levels",
            "score": 4,
            "value_ids": [value_id],
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_create_priority_with_multiple_value_links(client: AsyncClient, mock_validate_priority):
    """Test creating a priority linked to multiple values."""
    # Create values
    v1 = await client.post(
        "/values",
        json={"statement": "I value creativity", "weight_raw": 50, "origin": "declared"},
    )
    v2 = await client.post(
        "/values",
        json={"statement": "I value self-expression", "weight_raw": 50, "origin": "declared"},
    )

    # Create priority with both
    response = await client.post(
        "/priorities",
        json={
            "title": "Art projects",
            "why_matters": "Because expressing myself creatively protects my sense of identity",
            "score": 4,
            "value_ids": [v1.json()["id"], v2.json()["id"]],
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_check_status_endpoint(client: AsyncClient, mock_validate_priority):
    """Test the check-status endpoint for a priority."""
    # Create priority
    resp = await client.post(
        "/priorities",
        json={"title": "Priority for status check", "why_matters": "Testing check status endpoint", "score": 3},
    )
    priority_id = resp.json()["id"]

    # Check status
    response = await client.get(f"/priorities/{priority_id}/check-status")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_check_status_not_found(client: AsyncClient):
    """Test check-status for non-existent priority."""
    response = await client.get("/priorities/00000000-0000-0000-0000-000000000000/check-status")
    assert response.status_code == 404


# ============================================================================
# Priority Revision Update Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_priority_revision_changes_active(client: AsyncClient, mock_validate_priority):
    """Test that creating a revision changes the active revision."""
    # Create initial priority
    create_resp = await client.post(
        "/priorities",
        json={"title": "Initial title for revision test", "why_matters": "Initial why for revision test matters", "score": 3},
    )
    assert create_resp.status_code == 201, create_resp.json()
    priority_id = create_resp.json()["id"]
    original_revision_id = create_resp.json()["active_revision_id"]

    # Create revision
    revision_resp = await client.post(
        f"/priorities/{priority_id}/revisions",
        json={"title": "Updated title for revision", "why_matters": "Updated why matters with more detail now", "score": 4},
    )
    assert revision_resp.status_code == 200
    new_revision_id = revision_resp.json()["active_revision_id"]
    
    assert new_revision_id != original_revision_id


@pytest.mark.asyncio
async def test_create_priority_revision_preserves_stash_state(client: AsyncClient, mock_validate_priority):
    """Test that creating a revision preserves stash state."""
    # Create and stash
    create_resp = await client.post(
        "/priorities",
        json={"title": "Stashed priority for test", "why_matters": "Will be stashed during testing", "score": 3},
    )
    assert create_resp.status_code == 201, create_resp.json()
    priority_id = create_resp.json()["id"]
    await client.post(f"/priorities/{priority_id}/stash", json={"is_stashed": True})

    # Create revision
    await client.post(
        f"/priorities/{priority_id}/revisions",
        json={"title": "Still stashed title update", "why_matters": "Should remain stashed during revision update", "score": 3},
    )

    # Check still stashed
    stashed_resp = await client.get("/priorities/stashed")
    priority_ids = [p["id"] for p in stashed_resp.json()["priorities"]]
    assert priority_id in priority_ids


@pytest.mark.asyncio
async def test_delete_priority_success(client: AsyncClient, mock_validate_priority):
    """Test successfully deleting a priority."""
    # Create priority
    create_resp = await client.post(
        "/priorities",
        json={"title": "Will be deleted soon", "why_matters": "Temporary priority for delete test", "score": 3},
    )
    assert create_resp.status_code == 201, create_resp.json()
    priority_id = create_resp.json()["id"]

    # Delete it
    response = await client.delete(f"/priorities/{priority_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_delete_priority_not_found_block_3(client: AsyncClient):
    """Test deleting non-existent priority."""
    response = await client.delete("/priorities/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# ---- migrated from tests/mocked/test_services_priorities_migrated.py ----

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
async def test_priority_not_found(client: AsyncClient):
    """Test getting non-existent priority."""
    response = await client.get("/priorities/00000000-0000-0000-0000-000000000000/history")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_priority_delete_not_found(client: AsyncClient):
    """Test deleting non-existent priority."""
    response = await client.delete("/priorities/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_priority_anchor_not_found(client: AsyncClient):
    """Test anchoring non-existent priority."""
    response = await client.post("/priorities/00000000-0000-0000-0000-000000000000/anchor")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_priority_unanchor_not_found(client: AsyncClient):
    """Test unanchoring non-existent priority."""
    response = await client.post("/priorities/00000000-0000-0000-0000-000000000000/unanchor")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_priority_stash_not_found(client: AsyncClient):
    """Test stashing non-existent priority."""
    response = await client.post(
        "/priorities/00000000-0000-0000-0000-000000000000/stash",
        json={"is_stashed": True},
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_priority_revision_not_found(client: AsyncClient, mock_validate_priority):
    """Test creating revision for non-existent priority."""
    response = await client.post(
        "/priorities/00000000-0000-0000-0000-000000000000/revisions",
        json={
            "title": "New Revision",
            "why_matters": "Testing revision on non-existent priority",
            "score": 3,
        },
    )
    assert response.status_code == 404


# ============================================================================
# Values API Error Scenarios  
# ============================================================================

@pytest.mark.asyncio
async def test_links_get_not_found(client: AsyncClient):
    """Test getting links for non-existent priority revision."""
    response = await client.get(
        "/priority-revisions/00000000-0000-0000-0000-000000000000/links"
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_links_set_not_found(client: AsyncClient):
    """Test setting links for non-existent priority revision."""
    response = await client.put(
        "/priority-revisions/00000000-0000-0000-0000-000000000000/links",
        json={"links": []},
    )
    assert response.status_code == 404


# ============================================================================
# Dependencies API Error Scenarios
# ============================================================================

@pytest.mark.asyncio
async def test_priority_orphan_anchored_prevention(client: AsyncClient, mock_validate_priority):
    """Test preventing orphaned anchored priorities."""
    # Create value
    val = await client.post(
        "/values",
        json={"statement": "Orphan Test Value", "weight_raw": 70, "origin": "declared"},
    )
    val_id = val.json()["id"]

    # Create priority with value link
    priority = await client.post(
        "/priorities",
        json={
            "title": "Orphan Test Priority",
            "why_matters": "Testing orphan prevention for anchored priorities",
            "score": 4,
            "value_ids": [val_id],
        },
    )
    p_id = priority.json()["id"]

    # Anchor it
    await client.post(f"/priorities/{p_id}/anchor")

    # Try to create revision without value links - should fail for anchored
    response = await client.post(
        f"/priorities/{p_id}/revisions",
        json={
            "title": "No Links Revision",
            "why_matters": "Testing revision without value links",
            "score": 3,
            "value_ids": [],
        },
    )
    # Should fail because anchored priorities need links
    assert response.status_code == 400


# ---- migrated from tests/integration/test_api_helpers_priorities.py ----

"""Integration coverage for priorities helper behavior."""

import pytest
from httpx import AsyncClient
from unittest.mock import patch


@pytest.fixture
def mock_validate_priority():
    """Mock priority validation."""
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
async def test_priority_delete(client: AsyncClient, mock_validate_priority):
    """Test deleting a priority."""
    priority = await client.post(
        "/priorities",
        json={
            "title": "Delete Priority",
            "why_matters": "Testing priority deletion",
            "score": 2,
        },
    )
    p_id = priority.json()["id"]

    response = await client.delete(f"/priorities/{p_id}")
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_priority_with_multiple_value_links(client: AsyncClient, mock_validate_priority):
    """Test priority linked to multiple values."""
    val1 = await client.post(
        "/values",
        json={"statement": "Multi Link 1", "weight_raw": 50, "origin": "declared"},
    )
    v1_id = val1.json()["id"]

    val2 = await client.post(
        "/values",
        json={"statement": "Multi Link 2", "weight_raw": 50, "origin": "declared"},
    )
    v2_id = val2.json()["id"]

    response = await client.post(
        "/priorities",
        json={
            "title": "Multi Value Priority",
            "why_matters": "Testing multiple value links",
            "score": 4,
            "value_ids": [v1_id, v2_id],
        },
    )
    assert response.status_code == 201
