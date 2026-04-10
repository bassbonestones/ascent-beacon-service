"""Tests for alignment API endpoints."""

import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

from app.models.user import User


# ============================================================================
# Alignment Check Tests
# ============================================================================


@pytest.mark.asyncio
async def test_check_alignment_no_values(client: AsyncClient):
    """Test alignment check when user has no values."""
    with patch(
        "app.api.alignment.LLMService.get_alignment_reflection",
        new_callable=AsyncMock,
        return_value="You haven't defined any values yet."
    ):
        response = await client.post("/alignment/check")
    
    assert response.status_code == 200
    data = response.json()
    assert data["alignment_fit"] == 1.0  # No misalignment with nothing
    assert "reflection" in data


@pytest.mark.asyncio
async def test_check_alignment_with_values_no_priorities(client: AsyncClient):
    """Test alignment check when user has values but no priorities."""
    # Create a value first
    await client.post(
        "/values",
        json={"statement": "I value honesty", "weight_raw": 50, "origin": "declared"},
    )
    
    with patch(
        "app.api.alignment.LLMService.get_alignment_reflection",
        new_callable=AsyncMock,
        return_value="Your values are clear. Consider creating priorities to express them."
    ):
        response = await client.post("/alignment/check")
    
    assert response.status_code == 200
    data = response.json()
    assert "declared" in data
    assert "implied" in data
    assert "alignment_fit" in data


@pytest.mark.asyncio
async def test_check_alignment_with_values_and_priorities(client: AsyncClient):
    """Test alignment check with both values and priorities."""
    # Create a value
    value_response = await client.post(
        "/values",
        json={"statement": "I value family time", "weight_raw": 50, "origin": "declared"},
    )
    value_id = value_response.json()["id"]
    
    # Mock the priority validation and create an anchored priority
    validation_result = {
        "overall_valid": True,
        "name_feedback": {"valid": True, "message": "Good"},
        "why_feedback": {"valid": True, "message": "Good"},
    }
    with patch(
        "app.services.priority_validation.validate_priority",
        new_callable=AsyncMock,
        return_value=validation_result
    ):
        priority_response = await client.post(
            "/priorities",
            json={
                "title": "Spend evenings with family",
                "why_matters": "Family is important to me and spending time together strengthens our bonds",
                "score": 4,
                "value_ids": [value_id],
            },
        )
    assert priority_response.status_code == 201
    
    with patch(
        "app.api.alignment.LLMService.get_alignment_reflection",
        new_callable=AsyncMock,
        return_value="Your values and priorities are well aligned."
    ):
        response = await client.post("/alignment/check")
    
    assert response.status_code == 200
    data = response.json()
    assert data["alignment_fit"] >= 0.0
    assert data["alignment_fit"] <= 1.0


@pytest.mark.asyncio
async def test_check_alignment_tvd_calculation(client: AsyncClient):
    """Test that total variation distance is calculated correctly."""
    # Create two values with different weights
    await client.post(
        "/values",
        json={"statement": "Value 1", "weight_raw": 70, "origin": "declared"},
    )
    await client.post(
        "/values",
        json={"statement": "Value 2", "weight_raw": 30, "origin": "declared"},
    )
    
    with patch(
        "app.api.alignment.LLMService.get_alignment_reflection",
        new_callable=AsyncMock,
        return_value="Your declared values show a distribution."
    ):
        response = await client.post("/alignment/check")
    
    assert response.status_code == 200
    data = response.json()
    # TVD should be between 0 and 1
    assert 0.0 <= data["total_variation_distance"] <= 1.0
    # alignment_fit = 1 - TVD
    expected_fit = 1.0 - data["total_variation_distance"]
    assert abs(data["alignment_fit"] - expected_fit) < 0.001
