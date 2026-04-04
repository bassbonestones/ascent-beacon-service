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
