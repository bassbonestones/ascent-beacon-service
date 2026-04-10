"""Tests for LLM service with mocked API calls."""

import pytest
from unittest.mock import patch, AsyncMock

from app.services.llm_service import LLMService, VALUE_TOOLS


# ============================================================================
# get_recommendation Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_recommendation_values_mode():
    """Test get_recommendation with values context mode."""
    mock_response = {
        "choices": [{
            "message": {
                "content": "Let's explore what matters to you.",
                "role": "assistant",
            }
        }]
    }
    
    with patch("app.services.llm_service.llm_client") as mock_client:
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        
        result = await LLMService.get_recommendation(
            messages=[{"role": "user", "content": "Hi"}],
            user_context={"context_mode": "values", "user_id": "user123"},
        )
        
        assert result == mock_response
        mock_client.chat_completion.assert_called_once()
        
        # Verify system message includes values-specific content
        call_args = mock_client.chat_completion.call_args
        messages = call_args[1]["messages"]
        assert any("values" in msg.get("content", "").lower() for msg in messages)


@pytest.mark.asyncio
async def test_get_recommendation_priorities_mode():
    """Test get_recommendation with priorities context mode."""
    mock_response = {
        "choices": [{
            "message": {
                "content": "What would you like to focus on?",
                "role": "assistant",
            }
        }]
    }
    
    with patch("app.services.llm_service.llm_client") as mock_client:
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        
        result = await LLMService.get_recommendation(
            messages=[{"role": "user", "content": "Help me prioritize"}],
            user_context={"context_mode": "priorities", "user_id": "user456"},
        )
        
        assert result == mock_response
        
        # Verify system message includes priorities-specific content
        call_args = mock_client.chat_completion.call_args
        messages = call_args[1]["messages"]
        assert any("priorities" in msg.get("content", "").lower() for msg in messages)


@pytest.mark.asyncio
async def test_get_recommendation_general_mode():
    """Test get_recommendation with general context mode."""
    mock_response = {
        "choices": [{
            "message": {
                "content": "How can I help you today?",
                "role": "assistant",
            }
        }]
    }
    
    with patch("app.services.llm_service.llm_client") as mock_client:
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        
        result = await LLMService.get_recommendation(
            messages=[{"role": "user", "content": "Just chatting"}],
            user_context={"context_mode": "general", "user_id": "user789"},
        )
        
        assert result == mock_response


@pytest.mark.asyncio
async def test_get_recommendation_default_mode():
    """Test get_recommendation defaults to general mode when not specified."""
    mock_response = {
        "choices": [{
            "message": {"content": "Hello!", "role": "assistant"}
        }]
    }
    
    with patch("app.services.llm_service.llm_client") as mock_client:
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        
        result = await LLMService.get_recommendation(
            messages=[{"role": "user", "content": "Hi"}],
            user_context={},  # No context_mode
        )
        
        assert result == mock_response


@pytest.mark.asyncio
async def test_get_recommendation_with_tool_call():
    """Test get_recommendation with tool call response."""
    mock_response = {
        "choices": [{
            "message": {
                "content": None,
                "role": "assistant",
                "tool_calls": [{
                    "id": "call_123",
                    "function": {
                        "name": "propose_value",
                        "arguments": '{"statement": "I value creativity", "rationale": "Based on discussion"}',
                    },
                    "type": "function",
                }]
            }
        }]
    }
    
    with patch("app.services.llm_service.llm_client") as mock_client:
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        
        result = await LLMService.get_recommendation(
            messages=[{"role": "user", "content": "I really enjoy being creative"}],
            user_context={"context_mode": "values", "user_id": "user123"},
        )
        
        assert result["choices"][0]["message"]["tool_calls"] is not None
        
        # Verify tools are passed to API
        call_args = mock_client.chat_completion.call_args
        assert call_args[1].get("tools") == VALUE_TOOLS


@pytest.mark.asyncio
async def test_get_recommendation_conversation_history():
    """Test that conversation history is preserved."""
    mock_response = {
        "choices": [{
            "message": {"content": "I understand. Tell me more.", "role": "assistant"}
        }]
    }
    
    messages = [
        {"role": "user", "content": "First message"},
        {"role": "assistant", "content": "First response"},
        {"role": "user", "content": "Second message"},
    ]
    
    with patch("app.services.llm_service.llm_client") as mock_client:
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        
        result = await LLMService.get_recommendation(
            messages=messages,
            user_context={"context_mode": "values", "user_id": "user123"},
        )
        
        # Verify all messages are passed (plus system message)
        call_args = mock_client.chat_completion.call_args
        api_messages = call_args[1]["messages"]
        assert len(api_messages) == 4  # 1 system + 3 conversation


# ============================================================================
# VALUE_TOOLS Tests
# ============================================================================


def test_value_tools_structure():
    """Test that VALUE_TOOLS has correct structure."""
    assert isinstance(VALUE_TOOLS, list)
    assert len(VALUE_TOOLS) > 0
    
    tool = VALUE_TOOLS[0]
    assert tool["type"] == "function"
    assert "function" in tool
    assert tool["function"]["name"] == "propose_value"
    assert "parameters" in tool["function"]


def test_value_tools_required_fields():
    """Test that propose_value requires statement and rationale."""
    tool = VALUE_TOOLS[0]
    required = tool["function"]["parameters"].get("required", [])
    assert "statement" in required
    assert "rationale" in required
