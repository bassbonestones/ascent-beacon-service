"""Tests for assistant API endpoints."""

import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient

from app.models.user import User


# ============================================================================
# Create Session Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_session_values_mode(client: AsyncClient):
    """Test creating a session in values context mode."""
    response = await client.post(
        "/assistant/sessions",
        json={"context_mode": "values"},
    )
    
    assert response.status_code == 201
    data = response.json()
    assert data["context_mode"] == "values"
    assert data["is_active"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_create_session_priorities_mode(client: AsyncClient):
    """Test creating a session in priorities context mode."""
    response = await client.post(
        "/assistant/sessions",
        json={"context_mode": "priorities"},
    )
    
    assert response.status_code == 201
    assert response.json()["context_mode"] == "priorities"


@pytest.mark.asyncio
async def test_create_session_general_mode(client: AsyncClient):
    """Test creating a session in general context mode."""
    response = await client.post(
        "/assistant/sessions",
        json={"context_mode": "general"},
    )
    
    assert response.status_code == 201
    assert response.json()["context_mode"] == "general"


# ============================================================================
# Get Session Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_session_success(client: AsyncClient):
    """Test getting an existing session."""
    # Create session first
    create_response = await client.post(
        "/assistant/sessions",
        json={"context_mode": "values"},
    )
    session_id = create_response.json()["id"]
    
    # Get session
    response = await client.get(f"/assistant/sessions/{session_id}")
    
    assert response.status_code == 200
    assert response.json()["id"] == session_id


@pytest.mark.asyncio
async def test_get_session_not_found(client: AsyncClient):
    """Test getting a non-existent session."""
    response = await client.get("/assistant/sessions/00000000-0000-0000-0000-000000000000")
    
    assert response.status_code == 404


# ============================================================================
# Send Message Tests
# ============================================================================


@pytest.mark.asyncio
async def test_send_message_success(client: AsyncClient):
    """Test sending a message to a session."""
    # Create session
    create_response = await client.post(
        "/assistant/sessions",
        json={"context_mode": "values"},
    )
    session_id = create_response.json()["id"]
    
    # Mock LLM response in the format the API expects
    mock_llm_response = {
        "choices": [{
            "message": {
                "content": "Let's explore what matters most to you.",
                "role": "assistant",
            }
        }],
    }
    
    with patch(
        "app.api.assistant.LLMService.get_recommendation",
        new_callable=AsyncMock,
        return_value=mock_llm_response,
    ):
        response = await client.post(
            f"/assistant/sessions/{session_id}/message",
            json={"content": "I want to explore my values"},
        )
    
    assert response.status_code == 200
    data = response.json()
    assert "response" in data
    assert data["response"] == "Let's explore what matters most to you."


@pytest.mark.asyncio
async def test_send_message_session_not_found(client: AsyncClient):
    """Test sending message to non-existent session."""
    response = await client.post(
        "/assistant/sessions/00000000-0000-0000-0000-000000000000/message",
        json={"content": "Hello"},
    )
    
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_send_message_with_recommendations(client: AsyncClient):
    """Test that LLM tool calls create recommendations."""
    # Create session
    create_response = await client.post(
        "/assistant/sessions",
        json={"context_mode": "values"},
    )
    session_id = create_response.json()["id"]
    
    # Mock LLM response with tool call for propose_value
    mock_llm_response = {
        "choices": [{
            "message": {
                "content": None,
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_123",
                    "function": {
                        "name": "propose_value",
                        "arguments": '{"statement": "I value creativity", "rationale": "Based on our conversation"}',
                    },
                    "type": "function",
                }]
            }
        }],
    }
    
    with patch(
        "app.api.assistant.LLMService.get_recommendation",
        new_callable=AsyncMock,
        return_value=mock_llm_response,
    ):
        response = await client.post(
            f"/assistant/sessions/{session_id}/message",
            json={"content": "I really enjoy creative work"},
        )
    
    assert response.status_code == 200
    data = response.json()
    assert data["recommendation_id"] is not None
    assert "proposed value" in data["response"].lower()


@pytest.mark.asyncio
async def test_send_message_llm_error_returns_500(client: AsyncClient):
    """Test that LLM errors return 500 status code."""
    # Create session
    create_response = await client.post(
        "/assistant/sessions",
        json={"context_mode": "values"},
    )
    session_id = create_response.json()["id"]
    
    # Mock LLM to raise exception
    with patch(
        "app.api.assistant.LLMService.get_recommendation",
        new_callable=AsyncMock,
        side_effect=Exception("API connection failed"),
    ):
        response = await client.post(
            f"/assistant/sessions/{session_id}/message",
            json={"content": "Hello"},
        )
    
    assert response.status_code == 500
    assert "Failed to get LLM response" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_session_with_turns(client: AsyncClient):
    """Test retrieving session shows conversation history."""
    # Create session
    create_response = await client.post(
        "/assistant/sessions",
        json={"context_mode": "values"},
    )
    session_id = create_response.json()["id"]
    
    # Send a message
    mock_llm_response = {
        "choices": [{
            "message": {"content": "Hello!", "role": "assistant"}
        }],
    }
    with patch(
        "app.api.assistant.LLMService.get_recommendation",
        new_callable=AsyncMock,
        return_value=mock_llm_response,
    ):
        await client.post(
            f"/assistant/sessions/{session_id}/message",
            json={"content": "Hi there"},
        )
    
    # Get session - should include turns
    response = await client.get(f"/assistant/sessions/{session_id}")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data["turns"]) == 2  # User message + assistant response


@pytest.mark.asyncio
async def test_send_message_with_voice_modality(client: AsyncClient):
    """Test sending message with voice input modality."""
    create_response = await client.post(
        "/assistant/sessions",
        json={"context_mode": "values"},
    )
    session_id = create_response.json()["id"]
    
    mock_llm_response = {
        "choices": [{
            "message": {"content": "I understand.", "role": "assistant"}
        }],
    }
    with patch(
        "app.api.assistant.LLMService.get_recommendation",
        new_callable=AsyncMock,
        return_value=mock_llm_response,
    ):
        response = await client.post(
            f"/assistant/sessions/{session_id}/message",
            json={"content": "Voice transcribed text", "input_modality": "voice"},
        )
    
    assert response.status_code == 200


# ---- migrated from tests/mocked/test_services_assistant_migrated.py ----

"""Unit tests with mocked external services and error scenarios."""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta
from uuid import UUID
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
async def test_assistant_send_message_mocked(client: AsyncClient):
    """Test sending message to assistant with mocked LLM."""
    # Create session
    create_resp = await client.post(
        "/assistant/sessions",
        json={"context_mode": "general"},
    )
    session_id = create_resp.json()["id"]

    # Mock LLM response
    with patch("app.api.assistant.LLMService.get_recommendation") as mock_llm:
        async def mock_response(*args, **kwargs):
            return {
                "choices": [{
                    "message": {
                        "content": "I can help you explore your values.",
                        "tool_calls": None,
                    }
                }]
            }
        mock_llm.side_effect = mock_response

        response = await client.post(
            f"/assistant/sessions/{session_id}/message",
            json={"content": "Help me find my values", "input_modality": "text"},
        )
        assert response.status_code == 200
        assert "response" in response.json()

@pytest.mark.asyncio
async def test_assistant_message_with_tool_call_mocked(client: AsyncClient):
    """Test assistant message that triggers a tool call."""
    create_resp = await client.post(
        "/assistant/sessions",
        json={"context_mode": "values"},
    )
    session_id = create_resp.json()["id"]

    with patch("app.api.assistant.LLMService.get_recommendation") as mock_llm:
        async def mock_response(*args, **kwargs):
            return {
                "choices": [{
                    "message": {
                        "content": None,
                        "tool_calls": [{
                            "function": {
                                "name": "propose_value",
                                "arguments": json.dumps({
                                    "statement": "I value creativity",
                                    "rationale": "You mentioned enjoying creative work",
                                }),
                            }
                        }],
                    }
                }]
            }
        mock_llm.side_effect = mock_response

        response = await client.post(
            f"/assistant/sessions/{session_id}/message",
            json={"content": "I really enjoy creative work", "input_modality": "text"},
        )
        assert response.status_code == 200
        data = response.json()
        recommendation_id = data.get("recommendation_id")
        assert isinstance(recommendation_id, str)
        assert recommendation_id
        assert str(UUID(recommendation_id)) == recommendation_id

@pytest.mark.asyncio
async def test_assistant_session_not_found(client: AsyncClient):
    """Test getting non-existent session returns 404."""
    response = await client.get("/assistant/sessions/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_assistant_message_session_not_found(client: AsyncClient):
    """Test sending message to non-existent session returns 404."""
    response = await client.post(
        "/assistant/sessions/00000000-0000-0000-0000-000000000000/message",
        json={"content": "test", "input_modality": "text"},
    )
    assert response.status_code == 404


# ============================================================================
# Recommendations API Tests
# ============================================================================

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
async def test_accept_recommendation_not_found(client: AsyncClient):
    """Test accepting non-existent recommendation."""
    response = await client.post(
        "/recommendations/00000000-0000-0000-0000-000000000000/accept",
        json={},
    )
    assert response.status_code == 404

@pytest.mark.asyncio
async def test_reject_recommendation_not_found(client: AsyncClient):
    """Test rejecting non-existent recommendation."""
    response = await client.post(
        "/recommendations/00000000-0000-0000-0000-000000000000/reject",
        json={},
    )
    assert response.status_code == 404


# ============================================================================
# Discovery API Error Scenarios
# ============================================================================
