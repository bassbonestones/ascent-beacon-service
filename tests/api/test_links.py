"""Tests for priority-value links API endpoints."""

import pytest
from decimal import Decimal
from unittest.mock import patch
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


@pytest.fixture
async def value_with_revision(client: AsyncClient):
    """Create a value and return its ID and active revision ID."""
    response = await client.post(
        "/values",
        json={
            "statement": "I value continuous learning",
            "weight_raw": 50,
            "origin": "declared",
        },
    )
    data = response.json()
    return {
        "value_id": data["id"],
        "revision_id": data["active_revision_id"],
    }


@pytest.fixture
async def priority_with_revision(client: AsyncClient, mock_validate_priority):
    """Create a priority and return its ID and active revision ID."""
    response = await client.post(
        "/priorities",
        json={
            "title": "Learn new skills",
            "why_matters": "Learning helps me grow and adapt to changing situations",
            "score": 4,
        },
    )
    data = response.json()
    return {
        "priority_id": data["id"],
        "revision_id": data["active_revision_id"],
    }


@pytest.mark.asyncio
async def test_get_links_empty(client: AsyncClient, priority_with_revision):
    """Test getting links when none exist."""
    revision_id = priority_with_revision["revision_id"]
    
    response = await client.get(f"/priority-revisions/{revision_id}/links")
    
    assert response.status_code == 200
    assert response.json() == {"links": []}


@pytest.mark.asyncio
async def test_set_links(client: AsyncClient, value_with_revision, priority_with_revision):
    """Test setting value links for a priority revision."""
    value_revision_id = value_with_revision["revision_id"]
    priority_revision_id = priority_with_revision["revision_id"]
    
    response = await client.put(
        f"/priority-revisions/{priority_revision_id}/links",
        json={
            "links": [
                {"value_revision_id": value_revision_id, "link_weight": "1.0"}
            ]
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["links"]) == 1
    assert data["links"][0]["value_revision_id"] == value_revision_id
    assert Decimal(data["links"][0]["link_weight"]) == Decimal("1.0")


@pytest.mark.asyncio
async def test_set_multiple_links(client: AsyncClient, priority_with_revision):
    """Test setting multiple value links."""
    # Create two values
    value1 = await client.post(
        "/values",
        json={"statement": "Value 1", "weight_raw": 50, "origin": "declared"},
    )
    value2 = await client.post(
        "/values",
        json={"statement": "Value 2", "weight_raw": 50, "origin": "declared"},
    )
    
    value1_revision = value1.json()["active_revision_id"]
    value2_revision = value2.json()["active_revision_id"]
    priority_revision_id = priority_with_revision["revision_id"]
    
    response = await client.put(
        f"/priority-revisions/{priority_revision_id}/links",
        json={
            "links": [
                {"value_revision_id": value1_revision, "link_weight": "0.7"},
                {"value_revision_id": value2_revision, "link_weight": "0.3"},
            ]
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["links"]) == 2


@pytest.mark.asyncio
async def test_replace_links(client: AsyncClient, priority_with_revision):
    """Test that setting links replaces existing links."""
    # Create values
    value1 = await client.post(
        "/values",
        json={"statement": "Original value", "weight_raw": 50, "origin": "declared"},
    )
    value2 = await client.post(
        "/values",
        json={"statement": "Replacement value", "weight_raw": 50, "origin": "declared"},
    )
    
    priority_revision_id = priority_with_revision["revision_id"]
    
    # Set first link
    await client.put(
        f"/priority-revisions/{priority_revision_id}/links",
        json={
            "links": [
                {"value_revision_id": value1.json()["active_revision_id"], "link_weight": "1.0"}
            ]
        },
    )
    
    # Replace with different link
    response = await client.put(
        f"/priority-revisions/{priority_revision_id}/links",
        json={
            "links": [
                {"value_revision_id": value2.json()["active_revision_id"], "link_weight": "1.0"}
            ]
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Should only have the new link
    assert len(data["links"]) == 1
    assert data["links"][0]["value_revision_id"] == value2.json()["active_revision_id"]


@pytest.mark.asyncio
async def test_clear_links(client: AsyncClient, value_with_revision, priority_with_revision):
    """Test clearing all links by setting empty list."""
    value_revision_id = value_with_revision["revision_id"]
    priority_revision_id = priority_with_revision["revision_id"]
    
    # Set a link first
    await client.put(
        f"/priority-revisions/{priority_revision_id}/links",
        json={
            "links": [
                {"value_revision_id": value_revision_id, "link_weight": "1.0"}
            ]
        },
    )
    
    # Clear links
    response = await client.put(
        f"/priority-revisions/{priority_revision_id}/links",
        json={"links": []},
    )
    
    assert response.status_code == 200
    assert response.json() == {"links": []}


@pytest.mark.asyncio
async def test_get_links_not_found(client: AsyncClient):
    """Test getting links for non-existent revision."""
    response = await client.get("/priority-revisions/nonexistent-id/links")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_set_links_not_found(client: AsyncClient):
    """Test setting links for non-existent revision."""
    response = await client.put(
        "/priority-revisions/nonexistent-id/links",
        json={"links": []},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_links_persist_after_get(client: AsyncClient, value_with_revision, priority_with_revision):
    """Test that links persist and can be retrieved."""
    value_revision_id = value_with_revision["revision_id"]
    priority_revision_id = priority_with_revision["revision_id"]
    
    # Set links
    await client.put(
        f"/priority-revisions/{priority_revision_id}/links",
        json={
            "links": [
                {"value_revision_id": value_revision_id, "link_weight": "0.8"}
            ]
        },
    )
    
    # Get links
    response = await client.get(f"/priority-revisions/{priority_revision_id}/links")
    
    assert response.status_code == 200
    data = response.json()
    
    assert len(data["links"]) == 1
    assert data["links"][0]["value_revision_id"] == value_revision_id
    assert Decimal(data["links"][0]["link_weight"]) == Decimal("0.8")


# ============================================================================
# Multiple Value Links Tests
# ============================================================================


@pytest.mark.asyncio
async def test_set_multiple_value_links(client: AsyncClient, mock_validate_priority):
    """Test setting multiple value links on a priority."""
    # Create values
    val1_resp = await client.post(
        "/values",
        json={"statement": "Link Value 1", "weight_raw": 50, "origin": "declared"},
    )
    val2_resp = await client.post(
        "/values",
        json={"statement": "Link Value 2", "weight_raw": 40, "origin": "declared"},
    )
    val1_rev_id = val1_resp.json()["active_revision_id"]
    val2_rev_id = val2_resp.json()["active_revision_id"]
    
    # Create priority
    priority_resp = await client.post(
        "/priorities",
        json={
            "title": "Multi Link Priority",
            "why_matters": "Testing multiple value links",
            "score": 4,
        },
    )
    priority_rev_id = priority_resp.json()["active_revision_id"]
    
    # Set multiple links
    response = await client.put(
        f"/priority-revisions/{priority_rev_id}/links",
        json={
            "links": [
                {"value_revision_id": val1_rev_id, "link_weight": "0.6"},
                {"value_revision_id": val2_rev_id, "link_weight": "0.4"},
            ]
        },
    )
    assert response.status_code == 200
    assert len(response.json()["links"]) == 2


# ---- migrated from tests/integration/test_api_helpers_links.py ----

"""Integration coverage for links helper behavior."""

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
async def test_links_update_weights(client: AsyncClient, mock_validate_priority):
    """Test updating link weights."""
    val1 = await client.post(
        "/values",
        json={"statement": "Weight Link 1", "weight_raw": 60, "origin": "declared"},
    )
    v1_rev_id = val1.json()["active_revision"]["id"]

    val2 = await client.post(
        "/values",
        json={"statement": "Weight Link 2", "weight_raw": 40, "origin": "declared"},
    )
    v2_rev_id = val2.json()["active_revision"]["id"]

    priority = await client.post(
        "/priorities",
        json={
            "title": "Weight Links Priority",
            "why_matters": "Testing link weight updates",
            "score": 3,
        },
    )
    p_rev_id = priority.json()["active_revision"]["id"]

    response = await client.put(
        f"/priority-revisions/{p_rev_id}/links",
        json={
            "links": [
                {"value_revision_id": v1_rev_id, "link_weight": 0.7},
                {"value_revision_id": v2_rev_id, "link_weight": 0.3},
            ]
        },
    )
    assert response.status_code == 200
