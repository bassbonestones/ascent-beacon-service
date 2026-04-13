"""Tests for recommendations API endpoints."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.models.user import User
from app.models.assistant_session import AssistantSession
from app.models.assistant_recommendation import AssistantRecommendation
from app.models.value import Value, ValueRevision


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


@pytest.mark.asyncio
async def test_accept_recommendation_session_wrong_user(client: AsyncClient, db_session, test_user: User):
    """Session must belong to the authenticated user."""
    other = User(
        id=str(uuid4()),
        display_name="Other",
        primary_email=f"other-{uuid4().hex[:8]}@example.com",
        is_email_verified=True,
    )
    db_session.add(other)
    await db_session.flush()

    session = AssistantSession(user_id=other.id, context_mode="values")
    db_session.add(session)
    await db_session.flush()

    recommendation = AssistantRecommendation(
        session_id=session.id,
        proposed_action="create_value",
        payload={"statement": "X"},
        status="proposed",
        llm_provider="openai",
        llm_model="gpt-4",
    )
    db_session.add(recommendation)
    await db_session.commit()

    response = await client.post(
        f"/recommendations/{recommendation.id}/accept",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_accept_recommendation_missing_statement(client: AsyncClient, db_session, test_user: User):
    session = AssistantSession(user_id=test_user.id, context_mode="values")
    db_session.add(session)
    await db_session.flush()
    recommendation = AssistantRecommendation(
        session_id=session.id,
        proposed_action="create_value",
        payload={},
        status="proposed",
        llm_provider="openai",
        llm_model="gpt-4",
    )
    db_session.add(recommendation)
    await db_session.commit()

    response = await client.post(
        f"/recommendations/{recommendation.id}/accept",
        json={},
    )
    assert response.status_code == 400
    assert "statement" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_accept_recommendation_rebalances_five_existing_values(
    client: AsyncClient, db_session, test_user: User,
) -> None:
    """Fifth value accept updates weight_raw on each existing active revision."""
    for i in range(5):
        v = Value(user_id=test_user.id)
        db_session.add(v)
        await db_session.flush()
        rev = ValueRevision(
            value_id=v.id,
            statement=f"V{i}",
            weight_raw=100,
            is_active=True,
        )
        db_session.add(rev)
        await db_session.flush()
        v.active_revision_id = rev.id
    await db_session.commit()

    session = AssistantSession(user_id=test_user.id, context_mode="values")
    db_session.add(session)
    await db_session.flush()
    recommendation = AssistantRecommendation(
        session_id=session.id,
        proposed_action="create_value",
        payload={"statement": "Sixth value"},
        status="proposed",
        llm_provider="openai",
        llm_model="gpt-4",
    )
    db_session.add(recommendation)
    await db_session.commit()

    with patch(
        "app.api.recommendations.compute_value_similarity",
        new_callable=AsyncMock,
        return_value=(None, []),
    ):
        response = await client.post(
            f"/recommendations/{recommendation.id}/accept",
            json={},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_accept_recommendation_max_six_values(client: AsyncClient, db_session, test_user: User):
    for i in range(6):
        v = Value(user_id=test_user.id)
        db_session.add(v)
        await db_session.flush()
        rev = ValueRevision(
            value_id=v.id,
            statement=f"V{i}",
            weight_raw=100,
            is_active=True,
        )
        db_session.add(rev)
        await db_session.flush()
        v.active_revision_id = rev.id
    await db_session.commit()

    session = AssistantSession(user_id=test_user.id, context_mode="values")
    db_session.add(session)
    await db_session.flush()
    recommendation = AssistantRecommendation(
        session_id=session.id,
        proposed_action="create_value",
        payload={"statement": "Seventh value"},
        status="proposed",
        llm_provider="openai",
        llm_model="gpt-4",
    )
    db_session.add(recommendation)
    await db_session.commit()

    response = await client.post(
        f"/recommendations/{recommendation.id}/accept",
        json={},
    )
    assert response.status_code == 400
    assert "maximum" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_accept_recommendation_unsupported_action(client: AsyncClient, db_session, test_user: User):
    session = AssistantSession(user_id=test_user.id, context_mode="values")
    db_session.add(session)
    await db_session.flush()
    recommendation = AssistantRecommendation(
        session_id=session.id,
        proposed_action="unknown_action",
        payload={"statement": "X"},
        status="proposed",
        llm_provider="openai",
        llm_model="gpt-4",
    )
    db_session.add(recommendation)
    await db_session.commit()

    response = await client.post(
        f"/recommendations/{recommendation.id}/accept",
        json={},
    )
    assert response.status_code == 400
    assert "unsupported" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_accept_recommendation_similarity_and_embedding(
    client: AsyncClient, db_session, test_user: User,
) -> None:
    """Covers similarity match + embedding write when compute_value_similarity succeeds."""
    session = AssistantSession(user_id=test_user.id, context_mode="values")
    db_session.add(session)
    await db_session.flush()
    recommendation = AssistantRecommendation(
        session_id=session.id,
        proposed_action="create_value",
        payload={"statement": "New explored value"},
        status="proposed",
        llm_provider="openai",
        llm_model="gpt-4",
    )
    db_session.add(recommendation)
    await db_session.commit()

    match = {
        "similar_value_id": str(uuid4()),
        "similar_value_revision_id": str(uuid4()),
        "similarity_score": 0.91,
        "similar_statement": "Existing",
    }
    emb = [0.01] * 64
    with patch(
        "app.api.recommendations.compute_value_similarity",
        new_callable=AsyncMock,
        return_value=(match, emb),
    ):
        response = await client.post(
            f"/recommendations/{recommendation.id}/accept",
            json={},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_accept_recommendation_internal_error_wraps_exception(
    client: AsyncClient, db_session, test_user: User,
) -> None:
    _, recommendation = await create_test_session_and_recommendation(
        db_session, test_user.id, status="proposed"
    )
    with patch(
        "app.api.recommendations.normalize_value_weights",
        new_callable=AsyncMock,
        side_effect=RuntimeError("normalize failed"),
    ):
        response = await client.post(
            f"/recommendations/{recommendation.id}/accept",
            json={},
        )
    assert response.status_code == 500
    assert "failed" in response.json()["detail"].lower()


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


@pytest.mark.asyncio
async def test_reject_recommendation_session_wrong_user(client: AsyncClient, db_session, test_user: User):
    other = User(
        id=str(uuid4()),
        display_name="Other",
        primary_email=f"other-{uuid4().hex[:8]}@example.com",
        is_email_verified=True,
    )
    db_session.add(other)
    await db_session.flush()

    session = AssistantSession(user_id=other.id, context_mode="values")
    db_session.add(session)
    await db_session.flush()

    recommendation = AssistantRecommendation(
        session_id=session.id,
        proposed_action="create_value",
        payload={"statement": "X"},
        status="proposed",
        llm_provider="openai",
        llm_model="gpt-4",
    )
    db_session.add(recommendation)
    await db_session.commit()

    response = await client.post(
        f"/recommendations/{recommendation.id}/reject",
        json={},
    )
    assert response.status_code == 404


# ---- migrated from tests/mocked/test_services_recommendations.py ----

"""Recommendations API tests."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_recommendations_list_empty(client: AsyncClient):
    """Test listing pending recommendations when none exist."""
    response = await client.get("/recommendations/pending")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_recommendations_session_not_found(client: AsyncClient):
    """Test getting recommendations for non-existent session."""
    response = await client.get("/recommendations/session/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_accept_recommendation_not_found__legacyservices_recommendations(client: AsyncClient):
    """Test accepting non-existent recommendation."""
    response = await client.post(
        "/recommendations/00000000-0000-0000-0000-000000000000/accept",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reject_recommendation_not_found__legacyservices_recommendations(client: AsyncClient):
    """Test rejecting non-existent recommendation."""
    response = await client.post(
        "/recommendations/00000000-0000-0000-0000-000000000000/reject",
        json={},
    )
    assert response.status_code == 404
