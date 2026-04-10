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
