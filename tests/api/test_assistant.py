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
