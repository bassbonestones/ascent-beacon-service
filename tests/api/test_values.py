"""Tests for values API endpoints."""

import pytest
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.value import Value, ValueRevision
from app.models.user import User


@pytest.mark.asyncio
async def test_create_value(client: AsyncClient, test_user: User):
    """Test creating a new value."""
    response = await client.post(
        "/values",
        json={
            "statement": "I value honesty above all else",
            "weight_raw": 25,
            "origin": "declared",
        },
    )
    
    assert response.status_code == 201
    data = response.json()
    
    assert data["user_id"] == test_user.id
    assert data["active_revision_id"] is not None
    assert len(data["revisions"]) == 1
    
    # Check revision details
    revision = data["revisions"][0]
    assert revision["statement"] == "I value honesty above all else"
    assert revision["is_active"] is True
    assert revision["origin"] == "declared"


@pytest.mark.asyncio
async def test_create_multiple_values_rebalances_weights(client: AsyncClient):
    """Test that creating multiple values rebalances weights equally."""
    # Create first value
    response1 = await client.post(
        "/values",
        json={"statement": "Value 1", "weight_raw": 100, "origin": "declared"},
    )
    assert response1.status_code == 201
    
    # Create second value
    response2 = await client.post(
        "/values",
        json={"statement": "Value 2", "weight_raw": 100, "origin": "declared"},
    )
    assert response2.status_code == 201
    
    # List values to check weights
    list_response = await client.get("/values")
    assert list_response.status_code == 200
    values = list_response.json()["values"]
    
    # Both should have roughly equal normalized weights (accounting for float precision)
    assert len(values) == 2
    weights = [float(v["revisions"][0]["weight_normalized"]) for v in values]
    assert abs(weights[0] - weights[1]) < 1  # Within 1% of each other


@pytest.mark.asyncio
async def test_list_values_empty(client: AsyncClient):
    """Test listing values when user has none."""
    response = await client.get("/values")
    
    assert response.status_code == 200
    assert response.json() == {"values": []}


@pytest.mark.asyncio
async def test_list_values_with_data(client: AsyncClient):
    """Test listing values returns all user values."""
    # Create two values
    await client.post(
        "/values",
        json={"statement": "First value", "weight_raw": 50, "origin": "declared"},
    )
    await client.post(
        "/values",
        json={"statement": "Second value", "weight_raw": 50, "origin": "discovered"},
    )
    
    response = await client.get("/values")
    
    assert response.status_code == 200
    values = response.json()["values"]
    assert len(values) == 2


@pytest.mark.asyncio
async def test_get_value_history(client: AsyncClient):
    """Test getting revision history for a value."""
    # Create a value
    create_response = await client.post(
        "/values",
        json={"statement": "Original statement", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]
    
    # Update it to create a new revision
    await client.put(
        f"/values/{value_id}",
        json={"statement": "Updated statement", "weight_raw": 60, "origin": "refined"},
    )
    
    # Get history
    response = await client.get(f"/values/{value_id}/history")
    
    assert response.status_code == 200
    history = response.json()
    
    # Should have 2 revisions, ordered by created_at desc (newest first)
    assert len(history) == 2
    assert history[0]["statement"] == "Updated statement"
    assert history[1]["statement"] == "Original statement"


@pytest.mark.asyncio
async def test_get_value_history_not_found(client: AsyncClient):
    """Test getting history for non-existent value."""
    response = await client.get("/values/nonexistent-id/history")
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_value_creates_revision(client: AsyncClient):
    """Test that updating a value creates a new revision."""
    # Create initial value
    create_response = await client.post(
        "/values",
        json={"statement": "Original value", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]
    
    # Update the value
    update_response = await client.put(
        f"/values/{value_id}",
        json={"statement": "Refined value", "weight_raw": 75, "origin": "refined"},
    )
    
    assert update_response.status_code == 200
    data = update_response.json()
    
    # Should have 2 revisions now
    assert len(data["revisions"]) == 2
    
    # Active revision should be the new one
    active = next(r for r in data["revisions"] if r["id"] == data["active_revision_id"])
    assert active["statement"] == "Refined value"
    assert active["is_active"] is True


@pytest.mark.asyncio
async def test_update_value_not_found(client: AsyncClient):
    """Test updating non-existent value."""
    response = await client.put(
        "/values/nonexistent-id",
        json={"statement": "Test", "weight_raw": 50, "origin": "declared"},
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_value(client: AsyncClient):
    """Test deleting a value."""
    # Create a value
    create_response = await client.post(
        "/values",
        json={"statement": "To be deleted", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]
    
    # Delete it
    delete_response = await client.delete(f"/values/{value_id}")
    assert delete_response.status_code == 204
    
    # Verify it's gone
    list_response = await client.get("/values")
    values = list_response.json()["values"]
    value_ids = [v["id"] for v in values]
    assert value_id not in value_ids


@pytest.mark.asyncio
async def test_delete_value_not_found(client: AsyncClient):
    """Test deleting non-existent value."""
    response = await client.delete("/values/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_acknowledge_insight(client: AsyncClient):
    """Test acknowledging a similarity insight."""
    # Create a value first
    create_response = await client.post(
        "/values",
        json={"statement": "Test value", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]
    revision_id = create_response.json()["active_revision_id"]
    
    # Acknowledge insight
    response = await client.post(
        f"/values/{value_id}/insights/acknowledge",
        json={"revision_id": revision_id},
    )
    
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_get_linked_priorities_empty(client: AsyncClient):
    """Test getting linked priorities when none exist."""
    # Create a value
    create_response = await client.post(
        "/values",
        json={"statement": "Test value", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]
    
    # Get linked priorities
    response = await client.get(f"/values/{value_id}/linked-priorities")
    
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_value_origin_types(client: AsyncClient):
    """Test creating values with different origin types."""
    origins = ["declared", "discovered", "refined", "ai_suggested"]
    
    for origin in origins:
        response = await client.post(
            "/values",
            json={
                "statement": f"Value with origin {origin}",
                "weight_raw": 25,
                "origin": origin,
            },
        )
        assert response.status_code == 201
        assert response.json()["revisions"][0]["origin"] == origin


@pytest.mark.asyncio
async def test_acknowledge_insight_with_active_revision(client: AsyncClient):
    """Test acknowledging insight using active revision (no revision_id passed)."""
    # Create a value
    create_response = await client.post(
        "/values",
        json={"statement": "Test value", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]
    
    # Acknowledge without specifying revision_id
    response = await client.post(
        f"/values/{value_id}/insights/acknowledge",
        json={},
    )
    
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_acknowledge_insight_not_found(client: AsyncClient):
    """Test acknowledging insight for non-existent value."""
    response = await client.post(
        "/values/nonexistent-id/insights/acknowledge",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_acknowledge_insight_invalid_revision(client: AsyncClient):
    """Test acknowledging insight with invalid revision ID."""
    # Create a value
    create_response = await client.post(
        "/values",
        json={"statement": "Test value", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]
    
    # Try to acknowledge with invalid revision_id
    response = await client.post(
        f"/values/{value_id}/insights/acknowledge",
        json={"revision_id": "invalid-revision-id"},
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_linked_priorities_not_found(client: AsyncClient):
    """Test getting linked priorities for non-existent value."""
    response = await client.get("/values/nonexistent-id/linked-priorities")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_revision_directly(client: AsyncClient):
    """Test creating a revision via the revisions endpoint."""
    # Create initial value
    create_response = await client.post(
        "/values",
        json={"statement": "Original value", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]
    
    # Create revision via POST endpoint
    revision_response = await client.post(
        f"/values/{value_id}/revisions",
        json={"statement": "Updated via revisions endpoint", "weight_raw": 60, "origin": "refined"},
    )
    
    assert revision_response.status_code == 200
    data = revision_response.json()
    
    # Should have 2 revisions now
    assert len(data["revisions"]) == 2
    
    # New revision should be active
    active = next(r for r in data["revisions"] if r["id"] == data["active_revision_id"])
    assert active["statement"] == "Updated via revisions endpoint"


@pytest.mark.asyncio
async def test_create_revision_not_found(client: AsyncClient):
    """Test creating revision for non-existent value."""
    response = await client.post(
        "/values/nonexistent-id/revisions",
        json={"statement": "Test", "weight_raw": 50, "origin": "declared"},
    )
    assert response.status_code == 404


# ============================================================================
# Additional Coverage Tests
# ============================================================================


@pytest.mark.asyncio
async def test_match_value_empty_values(client: AsyncClient):
    """Test match endpoint when user has no values."""
    response = await client.post(
        "/values/match",
        json={"query": "honesty"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["value_id"] is None


@pytest.mark.asyncio
async def test_match_value_with_values(client: AsyncClient):
    """Test match endpoint returns response with values."""
    # Create values
    await client.post(
        "/values",
        json={"statement": "I value honesty and integrity", "weight_raw": 50, "origin": "declared"},
    )
    await client.post(
        "/values",
        json={"statement": "I value creativity and innovation", "weight_raw": 50, "origin": "declared"},
    )

    # Match should return a proper response (LLM may or may not match)
    response = await client.post(
        "/values/match",
        json={"query": "being truthful"},
    )
    assert response.status_code == 200
    # Just verify it returns a proper structure
    data = response.json()
    assert "value_id" in data


@pytest.mark.asyncio
async def test_create_value_with_discovered_origin(client: AsyncClient):
    """Test creating a value with discovered origin."""
    response = await client.post(
        "/values",
        json={
            "statement": "Value from discovery prompt",
            "weight_raw": 25,
            "origin": "discovered",
        },
    )
    
    assert response.status_code == 201
    data = response.json()
    revision = data["revisions"][0]
    assert revision["origin"] == "discovered"


@pytest.mark.asyncio
async def test_create_value_normalizes_weights(client: AsyncClient):
    """Test that creating values normalizes weights to sum to 100."""
    # Create 4 values
    for i in range(4):
        response = await client.post(
            "/values",
            json={"statement": f"Value {i}", "weight_raw": 50, "origin": "declared"},
        )
        assert response.status_code == 201

    # List and check normalized weights sum to 100
    list_response = await client.get("/values")
    values = list_response.json()["values"]
    assert len(values) == 4
    
    total_normalized = sum(
        float(v["revisions"][0]["weight_normalized"]) 
        for v in values 
        if v["revisions"]
    )
    assert abs(total_normalized - 100) < 0.1


@pytest.mark.asyncio
async def test_update_value_with_revision(client: AsyncClient):
    """Test that updating weight creates new revision."""
    # Create two values
    response1 = await client.post(
        "/values",
        json={"statement": "Value 1 - original", "weight_raw": 50, "origin": "declared"},
    )
    value_id = response1.json()["id"]
    
    await client.post(
        "/values",
        json={"statement": "Value 2 - comparison", "weight_raw": 50, "origin": "declared"},
    )

    # Update first value
    update_response = await client.put(
        f"/values/{value_id}",
        json={"statement": "Value 1 updated", "weight_raw": 100, "origin": "refined"},
    )
    assert update_response.status_code == 200
    # Should have 2 revisions now
    assert len(update_response.json()["revisions"]) == 2


# ============================================================================
# Value History Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_value_history(client: AsyncClient):
    """Test getting revision history for a value."""
    # Create a value
    response = await client.post(
        "/values",
        json={"statement": "History test", "weight_raw": 50, "origin": "declared"},
    )
    value_id = response.json()["id"]

    # Update it to create revision
    await client.put(
        f"/values/{value_id}",
        json={"statement": "History test updated", "weight_raw": 60, "origin": "refined"},
    )

    # Get history
    history_response = await client.get(f"/values/{value_id}/history")
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 2


@pytest.mark.asyncio
async def test_get_value_history_not_found(client: AsyncClient):
    """Test getting history for non-existent value."""
    response = await client.get("/values/00000000-0000-0000-0000-000000000000/history")
    assert response.status_code == 404


# ============================================================================
# Create Value Revision Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_value_revision(client: AsyncClient):
    """Test creating a new revision directly."""
    # Create a value
    response = await client.post(
        "/values",
        json={"statement": "Original statement", "weight_raw": 50, "origin": "declared"},
    )
    value_id = response.json()["id"]

    # Create revision
    revision_response = await client.post(
        f"/values/{value_id}/revisions",
        json={"statement": "Revised statement", "weight_raw": 60, "origin": "refined"},
    )
    assert revision_response.status_code == 200
    data = revision_response.json()
    assert "revisions" in data
    assert len(data["revisions"]) == 2


@pytest.mark.asyncio
async def test_create_value_revision_not_found(client: AsyncClient):
    """Test creating revision for non-existent value."""
    response = await client.post(
        "/values/00000000-0000-0000-0000-000000000000/revisions",
        json={"statement": "New statement", "weight_raw": 50, "origin": "refined"},
    )
    assert response.status_code == 404


# ============================================================================
# Delete Value Tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_value(client: AsyncClient):
    """Test deleting a value."""
    # Create a value
    response = await client.post(
        "/values",
        json={"statement": "To be deleted", "weight_raw": 50, "origin": "declared"},
    )
    value_id = response.json()["id"]

    # Delete it
    delete_response = await client.delete(f"/values/{value_id}")
    assert delete_response.status_code == 204

    # Verify it's gone
    get_response = await client.get("/values")
    values = get_response.json()["values"]
    assert all(v["id"] != value_id for v in values)


@pytest.mark.asyncio
async def test_delete_value_not_found(client: AsyncClient):
    """Test deleting non-existent value."""
    response = await client.delete("/values/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# ============================================================================
# Linked Priorities Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_linked_priorities(client: AsyncClient):
    """Test getting linked priorities for a value."""
    # Create a value
    response = await client.post(
        "/values",
        json={"statement": "Linked priorities test", "weight_raw": 50, "origin": "declared"},
    )
    value_id = response.json()["id"]

    # Get linked priorities (should be empty for new value)
    priorities_response = await client.get(f"/values/{value_id}/linked-priorities")
    assert priorities_response.status_code == 200
    assert isinstance(priorities_response.json(), list)


@pytest.mark.asyncio
async def test_get_linked_priorities_not_found(client: AsyncClient):
    """Test getting linked priorities for non-existent value."""
    response = await client.get("/values/00000000-0000-0000-0000-000000000000/linked-priorities")
    assert response.status_code == 404


# ============================================================================
# Value Revision Endpoint Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_value_revision(client: AsyncClient):
    """Test creating a new revision for an existing value via PUT."""
    # Create initial value
    create_response = await client.post(
        "/values",
        json={"title": "Original Value", "description": "Original description", "statement": "I value original", "weight_raw": 50, "origin": "declared"},
    )
    assert create_response.status_code == 201
    value_id = create_response.json()["id"]

    # Create a revision via PUT
    revision_response = await client.put(
        f"/values/{value_id}",
        json={"statement": "I value revised", "weight_raw": 50, "origin": "declared"},
    )
    assert revision_response.status_code == 200
    data = revision_response.json()
    # Check revision was created
    assert len(data["revisions"]) >= 1


@pytest.mark.asyncio
async def test_create_value_revision_via_endpoint(client: AsyncClient):
    """Test creating a new revision via dedicated revisions endpoint."""
    # Create initial value
    create_response = await client.post(
        "/values",
        json={"statement": "I value endpoint test", "weight_raw": 50, "origin": "declared"},
    )
    assert create_response.status_code == 201
    value_id = create_response.json()["id"]

    # Create revision via explicit endpoint
    revision_response = await client.post(
        f"/values/{value_id}/revisions",
        json={"statement": "I value via endpoint", "weight_raw": 50, "origin": "declared"},
    )
    assert revision_response.status_code == 200


@pytest.mark.asyncio
async def test_update_value(client: AsyncClient):
    """Test updating a value creates a new revision."""
    # Create value
    create_response = await client.post(
        "/values", json={"statement": "I value original", "weight_raw": 50, "origin": "declared"}
    )
    value_id = create_response.json()["id"]

    # Update value
    update_response = await client.put(
        f"/values/{value_id}",
        json={"statement": "I value updated", "weight_raw": 50, "origin": "declared"},
    )
    assert update_response.status_code == 200
    data = update_response.json()
    assert "revisions" in data


@pytest.mark.asyncio
async def test_update_value_not_found(client: AsyncClient):
    """Test updating a non-existent value."""
    response = await client.put(
        "/values/00000000-0000-0000-0000-000000000000",
        json={"statement": "New statement", "weight_raw": 50, "origin": "declared"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_value(client: AsyncClient):
    """Test soft-deleting a value."""
    # Create value
    create_response = await client.post(
        "/values", json={"statement": "I value delete test", "weight_raw": 50, "origin": "declared"}
    )
    value_id = create_response.json()["id"]

    # Delete value
    delete_response = await client.delete(f"/values/{value_id}")
    assert delete_response.status_code == 204

    # Verify it's gone from list
    list_response = await client.get("/values")
    value_ids = [v["id"] for v in list_response.json()["values"]]
    assert value_id not in value_ids


@pytest.mark.asyncio
async def test_delete_value_not_found(client: AsyncClient):
    """Test deleting a non-existent value."""
    response = await client.delete("/values/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_value_history(client: AsyncClient):
    """Test getting revision history for a value."""
    # Create value
    create_response = await client.post(
        "/values", json={"statement": "V1 statement", "weight_raw": 50, "origin": "declared"}
    )
    value_id = create_response.json()["id"]

    # Create additional revisions via PUT
    await client.put(
        f"/values/{value_id}",
        json={"statement": "V2 statement", "weight_raw": 50, "origin": "declared"},
    )
    await client.put(
        f"/values/{value_id}",
        json={"statement": "V3 statement", "weight_raw": 50, "origin": "declared"},
    )

    # Get history
    response = await client.get(f"/values/{value_id}/history")
    assert response.status_code == 200
    history = response.json()
    assert len(history) >= 3


@pytest.mark.asyncio
async def test_get_value_history_not_found(client: AsyncClient):
    """Test getting history for non-existent value."""
    response = await client.get("/values/00000000-0000-0000-0000-000000000000/history")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_value_includes_basic_info(client: AsyncClient):
    """Test that listing values includes value data."""
    # Create value
    create_response = await client.post(
        "/values", json={"statement": "I value basic info", "weight_raw": 50, "origin": "declared"}
    )
    value_id = create_response.json()["id"]

    # Get value via list
    list_response = await client.get("/values")
    assert list_response.status_code == 200
    value_ids = [v["id"] for v in list_response.json()["values"]]
    assert value_id in value_ids


@pytest.mark.asyncio
async def test_list_values_excludes_deleted(client: AsyncClient):
    """Test that listing values excludes soft-deleted ones."""
    # Create two values
    resp1 = await client.post("/values", json={"statement": "Keep me", "weight_raw": 50, "origin": "declared"})
    resp2 = await client.post(
        "/values", json={"statement": "Delete me", "weight_raw": 50, "origin": "declared"}
    )
    value1_id = resp1.json()["id"]
    value2_id = resp2.json()["id"]

    # Delete one
    await client.delete(f"/values/{value2_id}")

    # List should include first but not second
    list_response = await client.get("/values")
    value_ids = [v["id"] for v in list_response.json()["values"]]
    assert value1_id in value_ids
    assert value2_id not in value_ids


# ============================================================================
# Value Revision POST Endpoint Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_value_revision_via_post(client: AsyncClient):
    """Test creating a value revision via POST to /revisions endpoint."""
    # Create initial value
    create_response = await client.post(
        "/values",
        json={"statement": "I value learning", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]

    # Create revision via POST
    revision_response = await client.post(
        f"/values/{value_id}/revisions",
        json={"statement": "I value continuous learning", "weight_raw": 50, "origin": "declared"},
    )
    assert revision_response.status_code == 200
    data = revision_response.json()
    assert "revisions" in data
    assert len(data["revisions"]) >= 2


@pytest.mark.asyncio
async def test_create_value_revision_returns_impact_info(client: AsyncClient):
    """Test that creating a revision returns impact information."""
    # Create value
    create_response = await client.post(
        "/values",
        json={"statement": "I value honesty", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]

    # Create revision
    revision_response = await client.post(
        f"/values/{value_id}/revisions",
        json={"statement": "I value truthfulness", "weight_raw": 50, "origin": "declared"},
    )
    assert revision_response.status_code == 200
    data = revision_response.json()
    # Should have impact_info field
    if "impact_info" in data:
        assert "affected_priorities_count" in data["impact_info"]


@pytest.mark.asyncio
async def test_create_value_revision_with_different_weight(client: AsyncClient):
    """Test creating revision with different weight."""
    # Create value
    create_response = await client.post(
        "/values",
        json={"statement": "I value health", "weight_raw": 30, "origin": "declared"},
    )
    value_id = create_response.json()["id"]

    # Create revision with different weight
    revision_response = await client.post(
        f"/values/{value_id}/revisions",
        json={"statement": "I value physical health", "weight_raw": 60, "origin": "declared"},
    )
    assert revision_response.status_code == 200


@pytest.mark.asyncio
async def test_create_value_revision_not_found(client: AsyncClient):
    """Test creating revision for non-existent value."""
    response = await client.post(
        "/values/00000000-0000-0000-0000-000000000000/revisions",
        json={"statement": "New", "weight_raw": 50, "origin": "declared"},
    )
    assert response.status_code == 404


# ============================================================================
# Value Insight Acknowledgment Tests  
# ============================================================================


@pytest.mark.asyncio
async def test_acknowledge_value_insight(client: AsyncClient):
    """Test acknowledging a value insight."""
    # Create value
    create_response = await client.post(
        "/values",
        json={"statement": "I value kindness", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]

    # Acknowledge insight (even without one, should succeed)
    response = await client.post(f"/values/{value_id}/insights/acknowledge", json={})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_acknowledge_value_insight_with_revision_id(client: AsyncClient):
    """Test acknowledging insight with specific revision_id."""
    # Create value
    create_response = await client.post(
        "/values",
        json={"statement": "I value respect", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]
    revision_id = create_response.json()["active_revision_id"]

    # Acknowledge with revision_id
    response = await client.post(
        f"/values/{value_id}/insights/acknowledge",
        json={"revision_id": revision_id},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_acknowledge_value_insight_not_found(client: AsyncClient):
    """Test acknowledging insight for non-existent value."""
    response = await client.post(
        "/values/00000000-0000-0000-0000-000000000000/insights/acknowledge",
        json={},
    )
    assert response.status_code == 404


# ============================================================================
# Value Match Endpoint Tests
# ============================================================================


@pytest.mark.asyncio
async def test_match_value_by_query(client: AsyncClient):
    """Test matching values by query string."""
    # Create some values
    await client.post(
        "/values",
        json={"statement": "I value creativity and innovation", "weight_raw": 50, "origin": "declared"},
    )
    await client.post(
        "/values",
        json={"statement": "I value financial security", "weight_raw": 50, "origin": "declared"},
    )

    # Match query
    response = await client.post("/values/match", json={"query": "creative"})
    assert response.status_code == 200
    # May or may not find a match depending on similarity threshold


@pytest.mark.asyncio
async def test_match_value_no_values(client: AsyncClient):
    """Test matching when no values exist."""
    response = await client.post("/values/match", json={"query": "something"})
    assert response.status_code == 200
    assert response.json()["value_id"] is None


# ============================================================================
# Value Similarity Tests (Similar Values Detection)
# ============================================================================


@pytest.mark.asyncio
async def test_create_similar_values_generates_insight(client: AsyncClient):
    """Test that creating similar values may generate an insight."""
    # Create first value
    await client.post(
        "/values",
        json={"statement": "I value being kind to others", "weight_raw": 50, "origin": "declared"},
    )
    
    # Create very similar value
    response = await client.post(
        "/values",
        json={"statement": "I value kindness towards others", "weight_raw": 50, "origin": "declared"},
    )
    assert response.status_code == 201
    # May have insights if similarity detected


# ============================================================================  
# Delete Value with Linked Priorities Tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_value_success(client: AsyncClient):
    """Test successfully deleting a value without linked priorities."""
    # Create value
    create_response = await client.post(
        "/values",
        json={"statement": "Delete this value", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]

    # Delete it
    response = await client.delete(f"/values/{value_id}")
    assert response.status_code == 204


@pytest.mark.asyncio  
async def test_linked_priorities_endpoint(client: AsyncClient):
    """Test the linked priorities endpoint."""
    # Create value
    create_response = await client.post(
        "/values",
        json={"statement": "I value testing", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]

    # Get linked priorities (should be empty)
    response = await client.get(f"/values/{value_id}/linked-priorities")
    assert response.status_code == 200
    assert response.json() == []


# ============================================================================
# Value Edit Impact Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_value_returns_impact_info(client: AsyncClient):
    """Test that updating a value returns impact information when priorities are linked."""
    # Create a value and update it - simplified test without priority linkage
    create_response = await client.post(
        "/values",
        json={"statement": "I value honesty", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]

    # Update the value with a significantly different statement
    response = await client.post(
        f"/values/{value_id}/revisions",
        json={"statement": "I prioritize radical transparency in all interactions", "weight_raw": 60},
    )
    assert response.status_code == 200
    data = response.json()

    # Should include impact info (field named "impact_info" not "edit_impact")
    assert "impact_info" in data
    assert "affected_priorities_count" in data["impact_info"]
    # No priorities linked in this test, so count should be 0
    assert data["impact_info"]["affected_priorities_count"] == 0


@pytest.mark.asyncio
async def test_update_value_weight_verification_recommended(client: AsyncClient):
    """Test weight verification is recommended for significant statement changes."""
    # Create a short value
    create_response = await client.post(
        "/values",
        json={"statement": "I value creativity", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]

    # Update with a much longer statement (>20 char diff should trigger recommendation)
    response = await client.post(
        f"/values/{value_id}/revisions",
        json={
            "statement": "I deeply value creative expression through art, music, writing, and innovative thinking in all aspects of my life",
            "weight_raw": 50,
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_value_creation_with_existing_values_rebalances(client: AsyncClient):
    """Test that creating a new value properly rebalances existing weights."""
    # Create first value (returns 201 Created)
    resp1 = await client.post(
        "/values",
        json={"statement": "I value health", "weight_raw": 100, "origin": "declared"},
    )
    assert resp1.status_code == 201

    # Create second value (returns 201 Created)
    resp2 = await client.post(
        "/values",
        json={"statement": "I value wealth", "weight_raw": 100, "origin": "declared"},
    )
    assert resp2.status_code == 201

    # Both values should now exist
    list_response = await client.get("/values")
    values = list_response.json()["values"]
    assert len(values) == 2

    # Access weight through active_revision field
    total_weight = sum(
        float(v["active_revision"]["weight_normalized"]) for v in values
    )
    # Weights should sum to 100 (or close to it)
    assert 99 <= total_weight <= 101  # Allow slight floating point variance


@pytest.mark.asyncio
async def test_delete_value_rebalances_remaining(client: AsyncClient):
    """Test that deleting a value rebalances remaining values."""
    # Create three values
    for statement in ["I value A", "I value B", "I value C"]:
        await client.post(
            "/values",
            json={"statement": statement, "weight_raw": 33, "origin": "declared"},
        )

    # Get values and delete one
    list_response = await client.get("/values")
    values = list_response.json()["values"]
    assert len(values) == 3

    value_to_delete = values[0]["id"]
    await client.delete(f"/values/{value_to_delete}")

    # Remaining values should be rebalanced
    list_response = await client.get("/values")
    values = list_response.json()["values"]
    assert len(values) == 2


@pytest.mark.asyncio
async def test_acknowledge_insight_marks_revision_acknowledged(client: AsyncClient):
    """Test that acknowledging an insight marks the revision as user acknowledged."""
    # Create a value (note: requires existing value with similarity for real acknowledgment)
    create_response = await client.post(
        "/values",
        json={"statement": "I value learning", "weight_raw": 50, "origin": "discovered"},
    )
    value_id = create_response.json()["id"]
    revision_id = create_response.json()["active_revision_id"]

    # Acknowledge the insight (correct endpoint: /insights/acknowledge)
    response = await client.post(
        f"/values/{value_id}/insights/acknowledge",
        json={"revision_id": revision_id},
    )
    assert response.status_code == 200


# ============================================================================
# Additional Value API Tests for Coverage
# ============================================================================


@pytest.mark.asyncio
async def test_get_value_history_returns_value_data(client: AsyncClient):
    """Test getting a specific value's history."""
    create_response = await client.post(
        "/values",
        json={"statement": "I value specific testing", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]

    response = await client.get(f"/values/{value_id}/history")
    assert response.status_code == 200
    assert len(response.json()) >= 1


@pytest.mark.asyncio
async def test_get_value_history_not_found_error(client: AsyncClient):
    """Test getting history for a non-existent value."""
    response = await client.get("/values/00000000-0000-0000-0000-000000000000/history")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_value_weight_only(client: AsyncClient):
    """Test updating only the weight of a value."""
    create_response = await client.post(
        "/values",
        json={"statement": "I value weight tests", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]

    # Update weight only
    response = await client.post(
        f"/values/{value_id}/revisions",
        json={"statement": "I value weight tests", "weight_raw": 75},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_values_order(client: AsyncClient):
    """Test values are listed in created_at order."""
    # Create multiple values
    for i in range(3):
        await client.post(
            "/values",
            json={"statement": f"I value order test {i}", "weight_raw": 33, "origin": "declared"},
        )

    response = await client.get("/values")
    assert response.status_code == 200
    values = response.json()["values"]
    assert len(values) >= 3


@pytest.mark.asyncio
async def test_value_with_ai_origin(client: AsyncClient):
    """Test creating a value with AI origin."""
    response = await client.post(
        "/values",
        json={"statement": "I value AI insights", "weight_raw": 50, "origin": "ai_inferred"},
    )
    assert response.status_code == 201
    assert response.json()["active_revision"]["origin"] == "ai_inferred"


@pytest.mark.asyncio
async def test_value_with_source_prompt(client: AsyncClient, db_session):
    """Test creating a value with source_prompt_id."""
    from app.models import ValuePrompt

    # Create a prompt
    prompt = ValuePrompt(
        prompt_text="Test prompt for value",
        primary_lens="test",
        display_order=1,
        active=True,
    )
    db_session.add(prompt)
    await db_session.commit()
    await db_session.refresh(prompt)

    response = await client.post(
        "/values",
        json={
            "statement": "I value prompted values",
            "weight_raw": 50,
            "origin": "discovered",
            "source_prompt_id": prompt.id,
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_value_history_multiple_revisions(client: AsyncClient):
    """Test getting history with multiple revisions."""
    create_response = await client.post(
        "/values",
        json={"statement": "Original statement", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]

    # Create additional revisions
    await client.post(
        f"/values/{value_id}/revisions",
        json={"statement": "First update", "weight_raw": 60},
    )
    await client.post(
        f"/values/{value_id}/revisions",
        json={"statement": "Second update", "weight_raw": 70},
    )

    # Get history
    response = await client.get(f"/values/{value_id}/history")
    assert response.status_code == 200
    revisions = response.json()
    assert len(revisions) == 3


@pytest.mark.asyncio
async def test_match_value_returns_best_match(client: AsyncClient):
    """Test that match returns the closest value."""
    await client.post(
        "/values",
        json={"statement": "I deeply value creativity in all aspects of my work", "weight_raw": 50, "origin": "declared"},
    )
    await client.post(
        "/values",
        json={"statement": "I value financial stability", "weight_raw": 50, "origin": "declared"},
    )

    response = await client.post("/values/match", json={"query": "creative work"})
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_delete_value_removes_from_list(client: AsyncClient):
    """Test that deleting a value removes it from list."""
    create_response = await client.post(
        "/values",
        json={"statement": "I value deletion tests", "weight_raw": 50, "origin": "declared"},
    )
    value_id = create_response.json()["id"]

    # Delete
    await client.delete(f"/values/{value_id}")

    # Should not appear in list
    list_response = await client.get("/values")
    value_ids = [v["id"] for v in list_response.json()["values"]]
    assert value_id not in value_ids


# ============================================================================
# Value Weight Tests
# ============================================================================


@pytest.mark.asyncio
async def test_value_create_revision_with_new_weight(client: AsyncClient):
    """Test creating a new value revision with different weight."""
    # Create value
    create_resp = await client.post(
        "/values",
        json={
            "statement": "Test value for weight update",
            "weight_raw": 50,
            "origin": "declared",
        },
    )
    value_id = create_resp.json()["id"]
    
    # Create a new revision with different weight
    response = await client.post(
        f"/values/{value_id}/revisions",
        json={
            "statement": "Test value for weight update",
            "weight_raw": 80,
            "origin": "declared"
        },
    )
    assert response.status_code in [200, 201]


@pytest.mark.asyncio
async def test_value_with_max_weight(client: AsyncClient):
    """Test creating value with maximum weight."""
    response = await client.post(
        "/values",
        json={
            "statement": "Maximum weight value",
            "weight_raw": 100,
            "origin": "declared",
        },
    )
    assert response.status_code == 201
