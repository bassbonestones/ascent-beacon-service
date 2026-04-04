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
