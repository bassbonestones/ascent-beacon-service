"""Tests for /me API endpoint.

Source file: app/api/me.py
"""

import pytest
from httpx import AsyncClient

from app.models.user import User


# ============================================================================
# GET /me Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_me_returns_current_user(client: AsyncClient, test_user: User):
    """Test GET /me returns authenticated user details."""
    response = await client.get("/me")
    
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == test_user.id
    assert "primary_email" in data


@pytest.mark.asyncio
async def test_get_me_returns_user_display_name(client: AsyncClient, test_user: User):
    """Test GET /me includes display_name field."""
    response = await client.get("/me")
    
    assert response.status_code == 200
    data = response.json()
    assert "display_name" in data


@pytest.mark.asyncio
async def test_get_me_returns_user_created_at(client: AsyncClient, test_user: User):
    """Test GET /me includes created_at field."""
    response = await client.get("/me")
    
    assert response.status_code == 200
    data = response.json()
    assert "created_at" in data
    assert data["created_at"] is not None


@pytest.mark.asyncio
async def test_get_me_returns_is_email_verified(client: AsyncClient, test_user: User):
    """Test GET /me includes is_email_verified field."""
    response = await client.get("/me")
    
    assert response.status_code == 200
    data = response.json()
    assert "is_email_verified" in data


@pytest.mark.asyncio
async def test_get_me_without_auth_returns_403(unauthenticated_client: AsyncClient):
    """Test GET /me without authentication returns 403."""
    response = await unauthenticated_client.get("/me")
    
    assert response.status_code == 403


# ---- migrated from tests/mocked/test_services_external_services_migrated.py ----

import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_me_endpoint(client: AsyncClient):
    """Test the /me endpoint."""
    response = await client.get("/me")
    assert response.status_code == 200
    user = response.json()
    assert "id" in user
    # Email field may be named differently
    assert "primary_email" in user or "email" in user


# ============================================================================
# Health Check
# ============================================================================





# ---- migrated from tests/integration/test_api_helpers_me.py ----

"""Integration coverage for /me helper behavior."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_user_info(client: AsyncClient):
    """Test getting user info."""
    response = await client.get("/me")
    assert response.status_code == 200
    user = response.json()
    assert "id" in user
    assert "primary_email" in user or "email" in user


# ---- migrated from tests/integration/test_api_helpers_recommendations.py ----

"""Integration coverage for recommendations helper behavior."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_recommendations_list_by_session(client: AsyncClient):
    """Test getting recommendations for a specific session."""
    session = await client.post(
        "/assistant/sessions",
        json={"context_mode": "general"},
    )
    session_id = session.json()["id"]

    response = await client.get(f"/recommendations/session/{session_id}")
    assert response.status_code == 200


# ---- migrated from tests/integration/test_reopen_one_time_dependency_cleanup.py ----

"""One-time reopen must remove TaskCompletion rows so dependency rules re-apply."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_reopen_chain_after_complete_chain_restores_hard_blocking(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    """Complete A→B→C via chain, reopen each one-time task, then B is blocked by A again."""
    a = await client.post("/tasks", json={"title": "Reopen A"}, headers=auth_headers)
    b = await client.post("/tasks", json={"title": "Reopen B"}, headers=auth_headers)
    c = await client.post("/tasks", json={"title": "Reopen C"}, headers=auth_headers)
    aid, bid, cid = a.json()["id"], b.json()["id"], c.json()["id"]
    for up, down in ((aid, bid), (bid, cid)):
        r = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": up,
                "downstream_task_id": down,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        assert r.status_code == 201

    chain = await client.post(
        f"/tasks/{cid}/complete-chain", json={}, headers=auth_headers
    )
    assert chain.status_code == 200

    for tid in (cid, bid, aid):
        r = await client.post(f"/tasks/{tid}/reopen", json={}, headers=auth_headers)
        assert r.status_code == 200

    st = await client.get(f"/tasks/{cid}/dependency-status", headers=auth_headers)
    assert st.status_code == 200
    body = st.json()
    assert len(body["transitive_unmet_hard_prerequisites"]) == 2

    blocked = await client.post(f"/tasks/{bid}/complete", json={}, headers=auth_headers)
    assert blocked.status_code == 409


# ---- migrated from tests/integration/test_reopen_then_skip_one_time.py ----

"""One-time task: reopen must leave row pending so POST /skip succeeds."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_reopen_skipped_one_time_then_skip_ok(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    r = await client.post("/tasks", json={"title": "Skip after reopen"}, headers=auth_headers)
    assert r.status_code == 201
    tid = r.json()["id"]

    sk = await client.post(
        f"/tasks/{tid}/skip",
        json={"reason": "not today"},
        headers=auth_headers,
    )
    assert sk.status_code == 200
    assert sk.json()["status"] == "skipped"

    reopen = await client.post(f"/tasks/{tid}/reopen", json={}, headers=auth_headers)
    assert reopen.status_code == 200
    assert reopen.json()["status"] == "pending"

    sk2 = await client.post(
        f"/tasks/{tid}/skip",
        json={"reason": "again"},
        headers=auth_headers,
    )
    assert sk2.status_code == 200, sk2.text
    assert sk2.json()["status"] == "skipped"
