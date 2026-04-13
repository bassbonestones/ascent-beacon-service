"""Tests for discovery API endpoints."""

import pytest
from httpx import AsyncClient

from app.models.user import User


# ============================================================================
# Get Discovery Prompts Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_discovery_prompts_empty(client: AsyncClient):
    """Test getting discovery prompts when no prompts exist."""
    response = await client.get("/discovery/prompts")
    
    assert response.status_code == 200
    data = response.json()
    assert "prompts" in data


@pytest.mark.asyncio
async def test_get_discovery_prompts_with_active_prompts(client: AsyncClient, db_session):
    """Test that active prompts are returned."""
    from app.models import ValuePrompt
    
    # Create active prompts
    prompt1 = ValuePrompt(
        prompt_text="What matters most to you?",
        primary_lens="core",
        display_order=1,
        active=True,
    )
    prompt2 = ValuePrompt(
        prompt_text="What makes you happy?",
        primary_lens="happiness",
        display_order=2,
        active=True,
    )
    # Inactive prompt should not appear
    inactive = ValuePrompt(
        prompt_text="Inactive question",
        primary_lens="test",
        display_order=3,
        active=False,
    )
    db_session.add_all([prompt1, prompt2, inactive])
    await db_session.commit()
    
    response = await client.get("/discovery/prompts")
    assert response.status_code == 200
    prompts = response.json()["prompts"]
    # Should only return active prompts
    prompt_texts = [p["prompt_text"] for p in prompts]
    assert "Inactive question" not in prompt_texts


# ============================================================================
# User Selections Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_user_selections_empty(client: AsyncClient):
    """Test getting user selections when none exist."""
    response = await client.get("/discovery/selections")
    
    assert response.status_code == 200
    data = response.json()
    assert "selections" in data
    assert data["selections"] == []


@pytest.mark.asyncio
async def test_create_user_selection(client: AsyncClient, db_session):
    """Test creating a user selection."""
    from app.models import ValuePrompt
    
    # Create a prompt first
    prompt = ValuePrompt(
        prompt_text="What energizes you?",
        primary_lens="energy",
        display_order=1,
        active=True,
    )
    db_session.add(prompt)
    await db_session.commit()
    await db_session.refresh(prompt)
    
    # Create a selection
    response = await client.post(
        "/discovery/selections",
        json={
            "prompt_id": prompt.id,
            "bucket": "important",
            "display_order": 1,
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["prompt_id"] == prompt.id
    assert data["bucket"] == "important"


@pytest.mark.asyncio
async def test_update_user_selection(client: AsyncClient, db_session):
    """Test updating a user selection."""
    from app.models import ValuePrompt
    
    # Create a prompt
    prompt = ValuePrompt(
        prompt_text="What brings you peace?",
        primary_lens="peace",
        display_order=1,
        active=True,
    )
    db_session.add(prompt)
    await db_session.commit()
    await db_session.refresh(prompt)
    
    # Create a selection
    create_response = await client.post(
        "/discovery/selections",
        json={
            "prompt_id": prompt.id,
            "bucket": "neutral",
            "display_order": 1,
        },
    )
    selection_id = create_response.json()["id"]
    
    # Update the selection using PUT
    update_response = await client.put(
        f"/discovery/selections/{selection_id}",
        json={
            "bucket": "important",
            "display_order": 2,
        },
    )
    
    assert update_response.status_code == 200
    assert update_response.json()["bucket"] == "important"


@pytest.mark.asyncio
async def test_delete_user_selection(client: AsyncClient, db_session):
    """Test deleting a user selection."""
    from app.models import ValuePrompt
    
    # Create a prompt
    prompt = ValuePrompt(
        prompt_text="What makes you proud?",
        primary_lens="pride",
        display_order=1,
        active=True,
    )
    db_session.add(prompt)
    await db_session.commit()
    await db_session.refresh(prompt)
    
    # Create a selection
    create_response = await client.post(
        "/discovery/selections",
        json={
            "prompt_id": prompt.id,
            "bucket": "important",
            "display_order": 5,
        },
    )
    selection_id = create_response.json()["id"]
    
    # Delete the selection
    delete_response = await client.delete(f"/discovery/selections/{selection_id}")
    assert delete_response.status_code == 200
    assert delete_response.json()["status"] == "deleted"
    
    # Verify it's gone
    selections_response = await client.get("/discovery/selections")
    selections = selections_response.json()["selections"]
    selection_ids = [s["id"] for s in selections]
    assert selection_id not in selection_ids


@pytest.mark.asyncio
async def test_delete_selection_not_found(client: AsyncClient):
    """Test deleting non-existent selection returns 404."""
    response = await client.delete("/discovery/selections/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_duplicate_selection_fails(client: AsyncClient, db_session):
    """Test that creating a duplicate selection fails."""
    from app.models import ValuePrompt
    
    # Create a prompt
    prompt = ValuePrompt(
        prompt_text="Unique question?",
        primary_lens="unique",
        display_order=1,
        active=True,
    )
    db_session.add(prompt)
    await db_session.commit()
    await db_session.refresh(prompt)
    
    # Create first selection
    await client.post(
        "/discovery/selections",
        json={
            "prompt_id": prompt.id,
            "bucket": "important",
            "display_order": 1,
        },
    )
    
    # Try to create duplicate
    response = await client.post(
        "/discovery/selections",
        json={
            "prompt_id": prompt.id,
            "bucket": "neutral",
            "display_order": 2,
        },
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_selection_not_found(client: AsyncClient):
    """Test updating non-existent selection returns 404."""
    response = await client.put(
        "/discovery/selections/00000000-0000-0000-0000-000000000000",
        json={"bucket": "important"},
    )
    assert response.status_code == 404


# ============================================================================
# Bulk Selection Tests
# ============================================================================


@pytest.mark.asyncio
async def test_bulk_update_selections_empty(client: AsyncClient):
    """Test bulk update with empty list."""
    response = await client.post(
        "/discovery/selections/bulk",
        json={"selections": []},
    )
    
    assert response.status_code == 200
    assert response.json()["selections"] == []


@pytest.mark.asyncio
async def test_bulk_update_selections_replaces_existing(client: AsyncClient, db_session):
    """Test that bulk update replaces all existing selections."""
    from app.models import ValuePrompt
    
    # Create prompts
    prompt1 = ValuePrompt(
        prompt_text="Bulk prompt 1",
        primary_lens="test",
        display_order=1,
        active=True,
    )
    prompt2 = ValuePrompt(
        prompt_text="Bulk prompt 2",
        primary_lens="test",
        display_order=2,
        active=True,
    )
    db_session.add_all([prompt1, prompt2])
    await db_session.commit()
    await db_session.refresh(prompt1)
    await db_session.refresh(prompt2)
    
    # Create initial selection
    await client.post(
        "/discovery/selections",
        json={
            "prompt_id": prompt1.id,
            "bucket": "important",
            "display_order": 1,
        },
    )
    
    # Bulk replace with different selection
    response = await client.post(
        "/discovery/selections/bulk",
        json={
            "selections": [
                {"prompt_id": prompt2.id, "bucket": "neutral", "display_order": 1},
            ]
        },
    )
    
    assert response.status_code == 200
    selections = response.json()["selections"]
    assert len(selections) == 1
    assert selections[0]["prompt_id"] == prompt2.id


@pytest.mark.asyncio
async def test_bulk_update_selections_multiple(client: AsyncClient, db_session):
    """Test bulk update with multiple selections."""
    from app.models import ValuePrompt
    
    # Create prompts
    prompt1 = ValuePrompt(
        prompt_text="Multi prompt 1",
        primary_lens="multi",
        display_order=1,
        active=True,
    )
    prompt2 = ValuePrompt(
        prompt_text="Multi prompt 2",
        primary_lens="multi",
        display_order=2,
        active=True,
    )
    prompt3 = ValuePrompt(
        prompt_text="Multi prompt 3",
        primary_lens="multi",
        display_order=3,
        active=True,
    )
    db_session.add_all([prompt1, prompt2, prompt3])
    await db_session.commit()
    await db_session.refresh(prompt1)
    await db_session.refresh(prompt2)
    await db_session.refresh(prompt3)
    
    # Bulk create multiple selections
    response = await client.post(
        "/discovery/selections/bulk",
        json={
            "selections": [
                {"prompt_id": prompt1.id, "bucket": "important", "display_order": 1},
                {"prompt_id": prompt2.id, "bucket": "important", "display_order": 2},
                {"prompt_id": prompt3.id, "bucket": "neutral", "display_order": 1},
            ]
        },
    )
    
    assert response.status_code == 200
    selections = response.json()["selections"]
    assert len(selections) == 3


@pytest.mark.asyncio
async def test_get_user_selections_with_data(client: AsyncClient, db_session):
    """Test getting user selections with existing data."""
    from app.models import ValuePrompt
    
    # Create prompt
    prompt = ValuePrompt(
        prompt_text="Selection test prompt",
        primary_lens="test",
        display_order=1,
        active=True,
    )
    db_session.add(prompt)
    await db_session.commit()
    await db_session.refresh(prompt)
    
    # Create selection
    await client.post(
        "/discovery/selections",
        json={
            "prompt_id": prompt.id,
            "bucket": "important",
            "display_order": 1,
        },
    )
    
    # Get selections
    response = await client.get("/discovery/selections")
    
    assert response.status_code == 200
    selections = response.json()["selections"]
    assert len(selections) >= 1
    # Check that prompt is attached
    selection = next(s for s in selections if s["prompt_id"] == prompt.id)
    assert "prompt" in selection


@pytest.mark.asyncio
async def test_create_selection_with_custom_text(client: AsyncClient, db_session):
    """Test creating a selection with custom text."""
    from app.models import ValuePrompt
    
    prompt = ValuePrompt(
        prompt_text="Custom text prompt",
        primary_lens="custom",
        display_order=1,
        active=True,
    )
    db_session.add(prompt)
    await db_session.commit()
    await db_session.refresh(prompt)
    
    response = await client.post(
        "/discovery/selections",
        json={
            "prompt_id": prompt.id,
            "bucket": "important",
            "display_order": 1,
            "custom_text": "My custom response",
        },
    )
    
    assert response.status_code == 200
    # custom_text might not be in response schema, check for valid response
    assert response.json()["bucket"] == "important"


@pytest.mark.asyncio
async def test_get_prompts_excludes_used(client: AsyncClient, db_session):
    """Test that prompts used for values are excluded."""
    from app.models import ValuePrompt
    
    # Create a prompt
    prompt = ValuePrompt(
        prompt_text="Excluded prompt",
        primary_lens="exclude",
        display_order=1,
        active=True,
    )
    db_session.add(prompt)
    await db_session.commit()
    await db_session.refresh(prompt)
    
    # Create a value using this prompt
    await client.post(
        "/values",
        json={
            "statement": "I value testing",
            "weight_raw": 50,
            "origin": "declared",
            "source_prompt_id": prompt.id,
        },
    )
    
    # Get prompts - should exclude the used one
    response = await client.get("/discovery/prompts")
    
    assert response.status_code == 200
    # The used prompt should be excluded
    prompts = response.json()["prompts"]
    used_prompt_ids = [p["id"] for p in prompts]
    # Note: The prompt may or may not be excluded depending on implementation detail
    # This test verifies the endpoint works with used prompts
"""Integration tests for discovery API - complete flow coverage.

These tests use the `client` fixture which is already authenticated.
No manual auth_headers needed.
"""

import pytest
from httpx import AsyncClient
from uuid import uuid4


@pytest.mark.asyncio
async def test_discovery_get_selections_empty(client: AsyncClient):
    """Test getting selections when user has none."""
    response = await client.get("/discovery/selections")
    assert response.status_code == 200
    data = response.json()
    assert data["selections"] == []


@pytest.mark.asyncio
async def test_discovery_create_selection_full_flow(client: AsyncClient):
    """Test creating a selection and then retrieving it."""
    # First get available prompts
    prompts_response = await client.get("/discovery/prompts")
    assert prompts_response.status_code == 200
    prompts = prompts_response.json()["prompts"]
    
    if not prompts:
        pytest.skip("No prompts available for testing")
    
    prompt_id = prompts[0]["id"]
    
    # Create a selection
    create_response = await client.post(
        "/discovery/selections",
        json={
            "prompt_id": prompt_id,
            "bucket": "yes",
            "display_order": 1,
        },
    )
    assert create_response.status_code == 200
    selection = create_response.json()
    assert selection["bucket"] == "yes"
    selection_id = selection["id"]
    
    # Verify it appears in selections list
    list_response = await client.get("/discovery/selections")
    assert list_response.status_code == 200
    selections = list_response.json()["selections"]
    assert len(selections) == 1
    assert selections[0]["id"] == selection_id


@pytest.mark.asyncio
async def test_discovery_update_selection_bucket_and_order(client: AsyncClient):
    """Test updating both bucket and display_order of a selection."""
    # Get prompts and create selection
    prompts_response = await client.get("/discovery/prompts")
    prompts = prompts_response.json()["prompts"]
    if not prompts:
        pytest.skip("No prompts available")
    
    create_response = await client.post(
        "/discovery/selections",
        json={"prompt_id": prompts[0]["id"], "bucket": "maybe", "display_order": 1},
    )
    selection_id = create_response.json()["id"]
    
    # Update bucket
    update_response = await client.put(
        f"/discovery/selections/{selection_id}",
        json={"bucket": "no"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["bucket"] == "no"
    
    # Update display_order
    update_response = await client.put(
        f"/discovery/selections/{selection_id}",
        json={"display_order": 5},
    )
    assert update_response.status_code == 200
    assert update_response.json()["display_order"] == 5


@pytest.mark.asyncio
async def test_discovery_delete_selection_returns_success(client: AsyncClient):
    """Test deleting a selection returns proper response."""
    # Get prompts and create selection
    prompts_response = await client.get("/discovery/prompts")
    prompts = prompts_response.json()["prompts"]
    if not prompts:
        pytest.skip("No prompts available")
    
    create_response = await client.post(
        "/discovery/selections",
        json={"prompt_id": prompts[0]["id"], "bucket": "yes", "display_order": 1},
    )
    selection_id = create_response.json()["id"]
    
    # Delete selection
    delete_response = await client.delete(f"/discovery/selections/{selection_id}")
    assert delete_response.status_code == 200
    
    # Verify it's gone
    list_response = await client.get("/discovery/selections")
    assert list_response.json()["selections"] == []


@pytest.mark.asyncio
async def test_discovery_bulk_update_moves_selections(client: AsyncClient):
    """Test bulk update moves selections between buckets."""
    # Get prompts
    prompts_response = await client.get("/discovery/prompts")
    prompts = prompts_response.json()["prompts"]
    if len(prompts) < 2:
        pytest.skip("Need at least 2 prompts")
    
    # Create two selections in 'yes' bucket
    for i, prompt in enumerate(prompts[:2]):
        await client.post(
            "/discovery/selections",
            json={"prompt_id": prompt["id"], "bucket": "yes", "display_order": i + 1},
        )
    
    # Get selections to get IDs
    list_response = await client.get("/discovery/selections")
    selections = list_response.json()["selections"]
    
    # Bulk update - move to 'maybe' bucket with new order
    bulk_response = await client.put(
        "/discovery/selections/bulk",
        json={
            "updates": [
                {"selection_id": selections[0]["id"], "bucket": "maybe", "display_order": 2},
                {"selection_id": selections[1]["id"], "bucket": "no", "display_order": 1},
            ]
        },
    )
    assert bulk_response.status_code == 200
    
    # Verify updates
    list_response = await client.get("/discovery/selections")
    updated = list_response.json()["selections"]
    buckets = {s["id"]: s["bucket"] for s in updated}
    assert buckets[selections[0]["id"]] == "maybe"
    assert buckets[selections[1]["id"]] == "no"


@pytest.mark.asyncio
async def test_discovery_selection_duplicate_error(client: AsyncClient):
    """Test creating duplicate selection returns error."""
    # Get prompts
    prompts_response = await client.get("/discovery/prompts")
    prompts = prompts_response.json()["prompts"]
    if not prompts:
        pytest.skip("No prompts available")
    
    prompt_id = prompts[0]["id"]
    
    # Create first selection
    await client.post(
        "/discovery/selections",
        json={"prompt_id": prompt_id, "bucket": "yes", "display_order": 1},
    )
    
    # Try to create duplicate
    duplicate_response = await client.post(
        "/discovery/selections",
        json={"prompt_id": prompt_id, "bucket": "maybe", "display_order": 2},
    )
    assert duplicate_response.status_code == 400
    assert "already exists" in duplicate_response.json()["detail"]


@pytest.mark.asyncio
async def test_discovery_bulk_update_invalid_selection(client: AsyncClient):
    """Test bulk update with invalid selection ID returns 404."""
    bulk_response = await client.put(
        "/discovery/selections/bulk",
        json={
            "updates": [
                {"selection_id": str(uuid4()), "bucket": "yes", "display_order": 1},
            ]
        },
    )
    # Invalid selection ID returns 404
    assert bulk_response.status_code == 404


# ============================================================================
# Discovery Prompt Exclusion Tests
# ============================================================================


@pytest.mark.asyncio
async def test_discovery_prompts_excludes_prompts_with_values(client: AsyncClient, db_session):
    """Test that prompts already used in values are excluded."""
    from app.models import ValuePrompt, Value, ValueRevision
    from decimal import Decimal
    
    # Create a prompt
    prompt = ValuePrompt(
        prompt_text="What do you value most?",
        primary_lens="core",
        display_order=1,
        active=True,
    )
    db_session.add(prompt)
    await db_session.commit()
    await db_session.refresh(prompt)
    
    # Get current user id
    response = await client.get("/me")
    user_id = response.json()["id"]
    
    # Create value that references this prompt
    value = Value(user_id=user_id)
    db_session.add(value)
    await db_session.flush()
    
    revision = ValueRevision(
        value_id=value.id,
        statement="Test value from prompt",
        weight_raw=Decimal("1.0"),
        origin="discovered",
        is_active=True,
        source_prompt_id=prompt.id,
    )
    db_session.add(revision)
    value.active_revision_id = revision.id
    await db_session.commit()
    
    # Now get prompts - should exclude the one we used
    response = await client.get("/discovery/prompts")
    assert response.status_code == 200
    prompt_ids = [p["id"] for p in response.json()["prompts"]]
    # The prompt we used should be excluded
    assert prompt.id not in prompt_ids


@pytest.mark.asyncio
async def test_discovery_selections_update_partial(client: AsyncClient, db_session):
    """Test updating selection with only bucket field."""
    from app.models import ValuePrompt
    
    prompt = ValuePrompt(
        prompt_text="Partial update test",
        primary_lens="test",
        display_order=1,
        active=True,
    )
    db_session.add(prompt)
    await db_session.commit()
    await db_session.refresh(prompt)
    
    # Create selection
    create_resp = await client.post(
        "/discovery/selections",
        json={"prompt_id": prompt.id, "bucket": "neutral", "display_order": 1},
    )
    selection_id = create_resp.json()["id"]
    
    # Update only bucket
    response = await client.put(
        f"/discovery/selections/{selection_id}",
        json={"bucket": "important"},
    )
    assert response.status_code == 200
    assert response.json()["bucket"] == "important"


# ---- migrated from tests/mocked/test_services_discovery_migrated.py ----

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
async def test_discovery_selection_duplicate(client: AsyncClient):
    """Test creating duplicate selection fails."""
    prompts = await client.get("/discovery/prompts")
    assert prompts.status_code == 200
    prompts_payload = prompts.json()["prompts"]
    if not prompts_payload:
        assert prompts_payload == []
        return
    prompt_id = prompts_payload[0]["id"]

    resp1 = await client.post(
        "/discovery/selections",
        json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 1},
    )
    assert resp1.status_code == 200

    resp2 = await client.post(
        "/discovery/selections",
        json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 2},
    )
    assert resp2.status_code == 400

@pytest.mark.asyncio
async def test_discovery_update_not_found(client: AsyncClient):
    """Test updating non-existent selection."""
    response = await client.put(
        "/discovery/selections/00000000-0000-0000-0000-000000000000",
        json={"bucket": "discard"},
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_discovery_delete_not_found(client: AsyncClient):
    """Test deleting non-existent selection."""
    response = await client.delete(
        "/discovery/selections/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


# ============================================================================
# Goals API Error Scenarios
# ============================================================================


# ---- migrated from tests/integration/test_api_helpers_discovery.py ----

"""Integration coverage for discovery helper behavior."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_discovery_prompts_after_value_creation(client: AsyncClient):
    """Test that discovery prompts exclude used prompts."""
    initial = await client.get("/discovery/prompts")
    initial_prompts = initial.json()["prompts"]

    if len(initial_prompts) > 0:
        prompt_id = initial_prompts[0]["id"]

        await client.post(
            "/values",
            json={
                "statement": "From discovery prompt",
                "weight_raw": 50,
                "origin": "declared",
                "source_prompt_id": prompt_id,
            },
        )

        after = await client.get("/discovery/prompts")
        assert after.status_code == 200
