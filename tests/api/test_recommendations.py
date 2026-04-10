"""Tests for recommendations API endpoints."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import User
from app.models.assistant_session import AssistantSession
from app.models.assistant_recommendation import AssistantRecommendation


# ============================================================================
# Helper to create session and recommendation
# ============================================================================


async def create_test_session_and_recommendation(
    db_session, user_id: str, status: str = "proposed"
) -> tuple[AssistantSession, AssistantRecommendation]:
    """Create a test session and recommendation."""
    session = AssistantSession(
        user_id=user_id,
        context_mode="values",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    
    recommendation = AssistantRecommendation(
        session_id=session.id,
        proposed_action="create_value",
        payload={"statement": "I value creativity"},
        status=status,
        llm_provider="openai",
        llm_model="gpt-4",
    )
    db_session.add(recommendation)
    await db_session.commit()
    await db_session.refresh(recommendation)
    
    return session, recommendation


# ============================================================================
# Get Session Recommendations Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_session_recommendations_not_found(client: AsyncClient):
    """Test getting recommendations for non-existent session."""
    response = await client.get("/recommendations/session/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_session_recommendations_empty(client: AsyncClient, db_session, test_user: User):
    """Test getting recommendations for a session with none."""
    # Create a session without recommendations
    session = AssistantSession(
        user_id=test_user.id,
        context_mode="values",
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)
    
    response = await client.get(f"/recommendations/session/{session.id}")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_session_recommendations_with_data(client: AsyncClient, db_session, test_user: User):
    """Test getting recommendations for a session."""
    session, recommendation = await create_test_session_and_recommendation(
        db_session, test_user.id
    )
    
    response = await client.get(f"/recommendations/session/{session.id}")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["id"] == recommendation.id


# ============================================================================
# Get Pending Recommendations Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_pending_recommendations_empty(client: AsyncClient):
    """Test getting pending recommendations when none exist."""
    response = await client.get("/recommendations/pending")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_pending_recommendations_with_data(client: AsyncClient, db_session, test_user: User):
    """Test getting pending recommendations."""
    _, recommendation = await create_test_session_and_recommendation(
        db_session, test_user.id, status="proposed"
    )
    
    response = await client.get("/recommendations/pending")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(r["id"] == recommendation.id for r in data)


# ============================================================================
# Accept Recommendation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_accept_recommendation_not_found(client: AsyncClient):
    """Test accepting non-existent recommendation."""
    response = await client.post(
        "/recommendations/00000000-0000-0000-0000-000000000000/accept",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_accept_recommendation_create_value(client: AsyncClient, db_session, test_user: User):
    """Test accepting a create_value recommendation."""
    _, recommendation = await create_test_session_and_recommendation(
        db_session, test_user.id, status="proposed"
    )
    
    response = await client.post(
        f"/recommendations/{recommendation.id}/accept",
        json={},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "accepted"


@pytest.mark.asyncio
async def test_accept_recommendation_already_processed(client: AsyncClient, db_session, test_user: User):
    """Test accepting an already processed recommendation fails."""
    _, recommendation = await create_test_session_and_recommendation(
        db_session, test_user.id, status="accepted"
    )
    
    response = await client.post(
        f"/recommendations/{recommendation.id}/accept",
        json={},
    )
    assert response.status_code == 400
    assert "already" in response.json()["detail"].lower()


# ============================================================================
# Reject Recommendation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_reject_recommendation_not_found(client: AsyncClient):
    """Test rejecting non-existent recommendation."""
    response = await client.post(
        "/recommendations/00000000-0000-0000-0000-000000000000/reject",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reject_recommendation_success(client: AsyncClient, db_session, test_user: User):
    """Test rejecting a recommendation."""
    _, recommendation = await create_test_session_and_recommendation(
        db_session, test_user.id, status="proposed"
    )
    
    response = await client.post(
        f"/recommendations/{recommendation.id}/reject",
        json={},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "rejected"


@pytest.mark.asyncio
async def test_reject_recommendation_already_processed(client: AsyncClient, db_session, test_user: User):
    """Test rejecting an already processed recommendation fails."""
    _, recommendation = await create_test_session_and_recommendation(
        db_session, test_user.id, status="rejected"
    )
    
    response = await client.post(
        f"/recommendations/{recommendation.id}/reject",
        json={},
    )
    assert response.status_code == 400
