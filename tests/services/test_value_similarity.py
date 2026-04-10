"""Tests for value_similarity service."""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import numpy as np

from app.services.value_similarity import (
    llm_overlap_check,
    SIMILARITY_THRESHOLD,
    LLM_FALLBACK_THRESHOLD,
)


# ============================================================================
# Local cosine_similarity for testing
# ============================================================================


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))


# ============================================================================
# cosine_similarity Tests
# ============================================================================


def test_cosine_similarity_identical_vectors():
    """Test that identical vectors have similarity of 1.0."""
    vec = np.array([1.0, 2.0, 3.0])
    result = cosine_similarity(vec, vec)
    assert abs(result - 1.0) < 0.0001


def test_cosine_similarity_orthogonal_vectors():
    """Test that orthogonal vectors have similarity of 0.0."""
    vec1 = np.array([1.0, 0.0, 0.0])
    vec2 = np.array([0.0, 1.0, 0.0])
    result = cosine_similarity(vec1, vec2)
    assert abs(result) < 0.0001


def test_cosine_similarity_opposite_vectors():
    """Test that opposite vectors have similarity of -1.0."""
    vec1 = np.array([1.0, 0.0, 0.0])
    vec2 = np.array([-1.0, 0.0, 0.0])
    result = cosine_similarity(vec1, vec2)
    assert abs(result - (-1.0)) < 0.0001


def test_cosine_similarity_similar_vectors():
    """Test similarity of similar vectors."""
    vec1 = np.array([1.0, 2.0, 3.0])
    vec2 = np.array([1.1, 2.1, 3.1])
    result = cosine_similarity(vec1, vec2)
    # Should be very high (close to 1.0)
    assert result > 0.99


def test_cosine_similarity_partial_overlap():
    """Test similarity of partially overlapping vectors."""
    vec1 = np.array([1.0, 0.0, 0.0, 0.0])
    vec2 = np.array([1.0, 1.0, 0.0, 0.0])
    result = cosine_similarity(vec1, vec2)
    # cos(45 degrees) = 0.707...
    assert 0.7 < result < 0.72


# ============================================================================
# llm_overlap_check Tests
# ============================================================================


@pytest.mark.asyncio
async def test_llm_overlap_check_empty_existing():
    """Test LLM overlap check with no existing statements."""
    result = await llm_overlap_check("I value honesty", [])
    assert result is None


@pytest.mark.asyncio
async def test_llm_overlap_check_overlap_detected():
    """Test LLM overlap check when overlap is detected."""
    mock_response = {
        "choices": [{
            "message": {
                "content": '{"overlap": true, "most_similar": "I value being honest"}'
            }
        }]
    }
    
    with patch(
        "app.services.value_similarity.llm_client.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await llm_overlap_check(
            "I value honesty",
            ["I value being honest", "I value creativity"]
        )
    
    assert result is not None
    assert result["overlap"] is True
    assert result["most_similar"] == "I value being honest"


@pytest.mark.asyncio
async def test_llm_overlap_check_no_overlap():
    """Test LLM overlap check when no overlap is detected."""
    mock_response = {
        "choices": [{
            "message": {
                "content": '{"overlap": false, "most_similar": null}'
            }
        }]
    }
    
    with patch(
        "app.services.value_similarity.llm_client.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await llm_overlap_check(
            "I value adventure",
            ["I value stability", "I value routine"]
        )
    
    assert result is None


@pytest.mark.asyncio
async def test_llm_overlap_check_invalid_json_response():
    """Test LLM overlap check when response is invalid JSON."""
    mock_response = {
        "choices": [{
            "message": {
                "content": "This is not JSON"
            }
        }]
    }
    
    with patch(
        "app.services.value_similarity.llm_client.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await llm_overlap_check(
            "I value honesty",
            ["I value being honest"]
        )
    
    assert result is None


@pytest.mark.asyncio
async def test_llm_overlap_check_empty_content():
    """Test LLM overlap check when response content is empty."""
    mock_response = {
        "choices": [{
            "message": {
                "content": None
            }
        }]
    }
    
    with patch(
        "app.services.value_similarity.llm_client.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await llm_overlap_check(
            "I value honesty",
            ["I value being honest"]
        )
    
    # Empty content defaults to "{}" which has no overlap
    assert result is None


# ============================================================================
# Threshold Constants Tests
# ============================================================================


def test_similarity_threshold_is_reasonable():
    """Test that similarity threshold is a reasonable value."""
    assert 0.5 < SIMILARITY_THRESHOLD < 1.0


def test_llm_fallback_threshold_is_lower():
    """Test that LLM fallback threshold is lower than similarity threshold."""
    assert LLM_FALLBACK_THRESHOLD < SIMILARITY_THRESHOLD
    assert LLM_FALLBACK_THRESHOLD > 0.0
