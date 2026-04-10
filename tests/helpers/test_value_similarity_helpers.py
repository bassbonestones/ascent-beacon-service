"""Tests for value similarity and impact helpers."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal

from app.api.helpers.value_similarity_helpers import (
    build_similarity_insight,
    build_value_response_with_insight,
)
from app.schemas.values import ValueResponse


@pytest.mark.asyncio
async def test_build_similarity_insight():
    """Test building a similarity insight response."""
    similar_statement = "I value learning"
    match_info = {
        "similar_value_id": "value-123",
        "similar_value_revision_id": "rev-456",
        "similarity_score": 0.85,
    }
    
    insight = build_similarity_insight(similar_statement, match_info)
    
    assert insight is not None
    assert insight.similar_value_revision_id == "rev-456"
    assert insight.similarity_score == 0.85
    assert insight.type == "similar_value"


@pytest.mark.asyncio
async def test_build_value_response_with_insight_no_revision():
    """Test building response when value has no active revision."""
    mock_value = MagicMock()
    mock_value.active_revision_id = None
    mock_value.revisions = []
    mock_value.id = "value-123"
    mock_value.user_id = "user-456"
    mock_value.created_at = None
    mock_value.updated_at = None
    
    with patch("app.api.helpers.value_similarity_helpers.ValueResponse.model_validate") as mock:
        mock.return_value = MagicMock(model_copy=lambda update: MagicMock())
        
        response = build_value_response_with_insight(mock_value, {})
        
        # Should return without insights when no active revision
        mock.assert_called_once()


@pytest.mark.asyncio
async def test_build_value_response_with_insight_acknowledged():
    """Test building response when similarity is already acknowledged."""
    mock_revision = MagicMock()
    mock_revision.id = "rev-123"
    mock_revision.similar_value_revision_id = "similar-rev-456"
    mock_revision.similarity_acknowledged = True
    mock_revision.similarity_score = 0.9
    
    mock_value = MagicMock()
    mock_value.active_revision_id = "rev-123"
    mock_value.revisions = [mock_revision]
    mock_value.id = "value-123"
    mock_value.user_id = "user-456"
    mock_value.created_at = None
    mock_value.updated_at = None
    
    with patch("app.api.helpers.value_similarity_helpers.ValueResponse.model_validate") as mock:
        mock.return_value = MagicMock(model_copy=lambda update: MagicMock())
        
        response = build_value_response_with_insight(mock_value, {})
        
        # Should return without insights when acknowledged
        mock.assert_called_once()
