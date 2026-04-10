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
