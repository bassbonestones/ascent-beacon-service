"""Tests for priority validation service functions."""

import pytest
from unittest.mock import patch, MagicMock

from app.services.priority_validation import (
    validate_priority_name,
    validate_why_statement,
    validate_priority,
)


@pytest.mark.asyncio
async def test_validate_name_generic_term():
    """Test that generic terms are rejected."""
    result = await validate_priority_name("Health")
    
    assert result["is_valid"] is False
    assert result["passed_rules"].get("not_generic") is False
    assert len(result["feedback"]) > 0


@pytest.mark.asyncio
async def test_validate_name_generic_term_case_insensitive():
    """Test that generic terms are rejected regardless of case."""
    result = await validate_priority_name("WORK")
    
    assert result["is_valid"] is False


@pytest.mark.asyncio
async def test_validate_name_with_llm_specific():
    """Test LLM validation for specific name."""
    with patch("app.services.priority_validation.llm_client") as mock_llm:
        mock_llm.chat_completion.return_value = {
            "choices": [{"message": {"content": '{"is_specific": true}'}}]
        }
        
        result = await validate_priority_name("Daily meditation practice")
        
        assert result["is_valid"] is True
        assert result["passed_rules"].get("not_generic") is True


@pytest.mark.asyncio
async def test_validate_name_with_llm_not_specific():
    """Test LLM validation for generic name."""
    with patch("app.services.priority_validation.llm_client") as mock_llm:
        mock_llm.chat_completion.return_value = {
            "choices": [{"message": {"content": '{"is_specific": false}'}}]
        }
        
        result = await validate_priority_name("Be better")
        
        assert result["is_valid"] is False
        assert len(result["feedback"]) > 0  # Has some feedback


@pytest.mark.asyncio
async def test_validate_name_llm_error_long_name():
    """Test fallback when LLM fails but name is long enough."""
    with patch("app.services.priority_validation.llm_client") as mock_llm:
        mock_llm.chat_completion.side_effect = Exception("LLM Error")
        
        result = await validate_priority_name("This is a long specific name for testing")
        
        # Should pass due to length fallback
        assert result["is_valid"] is True


@pytest.mark.asyncio
async def test_validate_name_llm_error_short_name():
    """Test fallback when LLM fails and name is short."""
    with patch("app.services.priority_validation.llm_client") as mock_llm:
        mock_llm.chat_completion.side_effect = Exception("LLM Error")
        
        result = await validate_priority_name("Short")
        
        # Should fail due to short length
        assert result["is_valid"] is False


@pytest.mark.asyncio
async def test_validate_why_with_llm_valid():
    """Test LLM validation for valid why statement."""
    with patch("app.services.priority_validation.llm_client") as mock_llm:
        mock_llm.chat_completion.return_value = {
            "choices": [{
                "message": {
                    "content": """{
                        "personal": true,
                        "meaning_based": true,
                        "implies_protection": true,
                        "concrete": true
                    }"""
                }
            }]
        }
        
        result = await validate_why_statement(
            "Because maintaining my health allows me to be present for my family"
        )
        
        assert result["is_valid"] is True
        assert all(result["passed_rules"].values())


@pytest.mark.asyncio
async def test_validate_why_with_llm_fails_rules():
    """Test LLM validation when rules fail."""
    with patch("app.services.priority_validation.llm_client") as mock_llm:
        mock_llm.chat_completion.return_value = {
            "choices": [{
                "message": {
                    "content": """{
                        "personal": false,
                        "meaning_based": false,
                        "implies_protection": false,
                        "concrete": false
                    }"""
                }
            }]
        }
        
        result = await validate_why_statement("Just because")
        
        assert result["is_valid"] is False
        assert len(result["feedback"]) > 0


@pytest.mark.asyncio
async def test_validate_why_llm_error_good_fallback():
    """Test fallback when LLM fails but statement looks good."""
    with patch("app.services.priority_validation.llm_client") as mock_llm:
        mock_llm.chat_completion.side_effect = Exception("LLM Error")
        
        result = await validate_why_statement(
            "Because this is my reason for doing something meaningful"
        )
        
        # Should pass due to "because" keyword and length
        assert result["is_valid"] is True


@pytest.mark.asyncio
async def test_validate_why_llm_error_bad_fallback():
    """Test fallback when LLM fails and statement is poor."""
    with patch("app.services.priority_validation.llm_client") as mock_llm:
        mock_llm.chat_completion.side_effect = Exception("LLM Error")
        
        result = await validate_why_statement("Just want to")
        
        # Should fail due to no "because" and short length
        assert result["is_valid"] is False


@pytest.mark.asyncio
async def test_validate_priority_overall():
    """Test the combined validation function."""
    with patch("app.services.priority_validation.llm_client") as mock_llm:
        # First call for name, second for why
        mock_llm.chat_completion.side_effect = [
            {"choices": [{"message": {"content": '{"is_specific": true}'}}]},
            {"choices": [{"message": {"content": '{"personal": true, "meaning_based": true, "implies_protection": true, "concrete": true}'}}]},
        ]
        
        result = await validate_priority("Learn Spanish", "Because speaking Spanish connects me to my heritage")
        
        assert result["overall_valid"] is True
        assert result["name_valid"] is True
        assert result["why_valid"] is True
