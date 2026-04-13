"""Deep mocked tests for external services to maximize coverage."""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta
import json


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



# ============================================================================
# Deeply Mocked Assistant Tests
# ============================================================================

@pytest.mark.asyncio
async def test_alignment_check_with_llm_reflection(client: AsyncClient, mock_validate_priority):
    """Test alignment check that calls LLM for reflection."""
    # Create value
    val = await client.post(
        "/values",
        json={"statement": "I value creativity", "weight_raw": 80, "origin": "declared"},
    )
    val_id = val.json()["id"]

    # Create and anchor priority
    priority = await client.post(
        "/priorities",
        json={
            "title": "Create more art",
            "why_matters": "Art fuels my soul and creativity",
            "score": 5,
            "value_ids": [val_id],
        },
    )
    p_id = priority.json()["id"]
    await client.post(f"/priorities/{p_id}/anchor")

    # Mock LLM reflection
    with patch("app.api.alignment.LLMService.get_alignment_reflection", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "Your values and priorities show strong alignment. Creative expression is central to both."
        
        response = await client.post("/alignment/check")
        
        assert response.status_code == 200
        data = response.json()
        assert "reflection" in data
        assert data["reflection"] == "Your values and priorities show strong alignment. Creative expression is central to both."

@pytest.mark.asyncio
async def test_alignment_check_empty(client: AsyncClient):
    """Test alignment with no values or priorities."""
    with patch("app.api.alignment.LLMService.get_alignment_reflection", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = ""
        
        response = await client.post("/alignment/check")
        
        assert response.status_code == 200
        data = response.json()
        assert data["declared"] == {}
        assert data["implied"] == {}
        assert data["alignment_fit"] == 1.0
        assert data["reflection"] == ""


# ============================================================================
# Deeply Mocked Recommendations Tests
# ============================================================================
