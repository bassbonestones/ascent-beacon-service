"""Tests for value_helpers module."""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi import HTTPException

from app.api.helpers.value_helpers import (
    get_value_or_404,
    reload_value_with_revisions,
    match_value_by_llm,
    rebalance_values_equal_weight,
)
from app.models.value import Value, ValueRevision


@pytest.mark.asyncio
async def test_get_value_or_404_found(db_session, test_user):
    """Test get_value_or_404 returns value when found and owned."""
    # Create a value
    value = Value(user_id=test_user.id)
    db_session.add(value)
    await db_session.flush()
    
    result = await get_value_or_404(db_session, test_user.id, value.id)
    
    assert result.id == value.id
    assert result.user_id == test_user.id


@pytest.mark.asyncio
async def test_get_value_or_404_not_found(db_session, test_user):
    """Test get_value_or_404 raises 404 when value doesn't exist."""
    with pytest.raises(HTTPException) as exc_info:
        await get_value_or_404(db_session, test_user.id, "nonexistent-id")
    
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Value not found"


@pytest.mark.asyncio
async def test_get_value_or_404_wrong_owner(db_session, test_user):
    """Test get_value_or_404 raises 404 when user doesn't own value."""
    # Create a value owned by test_user
    value = Value(user_id=test_user.id)
    db_session.add(value)
    await db_session.flush()
    
    # Try to access with a different user_id
    with pytest.raises(HTTPException) as exc_info:
        await get_value_or_404(db_session, "different-user-id", value.id)
    
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Value not found"


@pytest.mark.asyncio
async def test_reload_value_with_revisions(db_session, test_user):
    """Test reload_value_with_revisions loads value with revisions."""
    # Create a value with revisions
    value = Value(user_id=test_user.id)
    db_session.add(value)
    await db_session.flush()
    
    revision = ValueRevision(
        value_id=value.id,
        statement="Test statement",
        weight_raw=100,
        is_active=True,
    )
    db_session.add(revision)
    await db_session.flush()
    
    value.active_revision_id = revision.id
    await db_session.commit()
    
    result = await reload_value_with_revisions(db_session, value.id)
    
    assert result.id == value.id
    assert len(result.revisions) == 1
    assert result.revisions[0].statement == "Test statement"


@pytest.mark.asyncio
async def test_rebalance_values_equal_weight_empty(db_session, test_user):
    """Test rebalance_values_equal_weight with no existing values."""
    await rebalance_values_equal_weight(db_session, test_user.id)
    # Should complete without error


@pytest.mark.asyncio
async def test_rebalance_values_equal_weight_single_value(db_session, test_user):
    """Test rebalance_values_equal_weight with one existing value."""
    # Create a value
    value = Value(user_id=test_user.id)
    db_session.add(value)
    await db_session.flush()
    
    revision = ValueRevision(
        value_id=value.id,
        statement="Test",
        weight_raw=50,  # Starting weight
        is_active=True,
    )
    db_session.add(revision)
    await db_session.flush()
    
    value.active_revision_id = revision.id
    await db_session.commit()
    
    # Rebalance expecting 1 new value
    await rebalance_values_equal_weight(db_session, test_user.id, new_value_count=1)
    await db_session.commit()
    
    # Reload and check weight is now 50 (100/2)
    await db_session.refresh(revision)
    assert float(revision.weight_raw) == 50.0


@pytest.mark.asyncio
async def test_rebalance_values_equal_weight_multiple_values(db_session, test_user):
    """Test rebalance_values_equal_weight with multiple existing values."""
    # Create two values
    value1 = Value(user_id=test_user.id)
    value2 = Value(user_id=test_user.id)
    db_session.add(value1)
    db_session.add(value2)
    await db_session.flush()
    
    revision1 = ValueRevision(
        value_id=value1.id,
        statement="Test 1",
        weight_raw=70,
        is_active=True,
    )
    revision2 = ValueRevision(
        value_id=value2.id,
        statement="Test 2",
        weight_raw=30,
        is_active=True,
    )
    db_session.add(revision1)
    db_session.add(revision2)
    await db_session.flush()
    
    value1.active_revision_id = revision1.id
    value2.active_revision_id = revision2.id
    await db_session.commit()
    
    # Rebalance with no new values
    await rebalance_values_equal_weight(db_session, test_user.id)
    await db_session.commit()
    
    # Reload and check weights are now 50 each (100/2)
    await db_session.refresh(revision1)
    await db_session.refresh(revision2)
    assert float(revision1.weight_raw) == 50.0
    assert float(revision2.weight_raw) == 50.0


@pytest.mark.asyncio
async def test_match_value_by_llm_no_values(db_session, test_user):
    """Test match_value_by_llm returns None when no values exist."""
    result = await match_value_by_llm(db_session, test_user.id, "test query")
    assert result is None


@pytest.mark.asyncio
async def test_match_value_by_llm_no_active_revisions(db_session, test_user):
    """Test match_value_by_llm returns None when values have no active revisions."""
    # Create a value without active revision
    value = Value(user_id=test_user.id)
    db_session.add(value)
    await db_session.commit()
    
    result = await match_value_by_llm(db_session, test_user.id, "test query")
    assert result is None


@pytest.mark.asyncio
async def test_match_value_by_llm_with_values(db_session, test_user):
    """Test match_value_by_llm returns matched value ID."""
    # Create a value with active revision
    value = Value(user_id=test_user.id)
    db_session.add(value)
    await db_session.flush()
    
    revision = ValueRevision(
        value_id=value.id,
        statement="Being present with family",
        weight_raw=100,
        is_active=True,
    )
    db_session.add(revision)
    await db_session.flush()
    
    value.active_revision_id = revision.id
    await db_session.commit()
    
    # Mock the LLM response
    with patch("app.api.helpers.value_helpers.llm_client") as mock_llm:
        mock_llm.chat_completion = AsyncMock(return_value={
            "choices": [{"message": {"content": f'{{"value_id": "{value.id}"}}'}}]
        })
        
        result = await match_value_by_llm(db_session, test_user.id, "family time")
        assert result == value.id


@pytest.mark.asyncio
async def test_match_value_by_llm_invalid_llm_response(db_session, test_user):
    """Test match_value_by_llm handles invalid LLM response."""
    # Create a value with active revision
    value = Value(user_id=test_user.id)
    db_session.add(value)
    await db_session.flush()
    
    revision = ValueRevision(
        value_id=value.id,
        statement="Test value",
        weight_raw=100,
        is_active=True,
    )
    db_session.add(revision)
    await db_session.flush()
    
    value.active_revision_id = revision.id
    await db_session.commit()
    
    # Mock the LLM response with invalid JSON
    with patch("app.api.helpers.value_helpers.llm_client") as mock_llm:
        mock_llm.chat_completion = AsyncMock(return_value={
            "choices": [{"message": {"content": "not valid json"}}]
        })
        
        result = await match_value_by_llm(db_session, test_user.id, "query")
        assert result is None


@pytest.mark.asyncio  
async def test_match_value_by_llm_no_match(db_session, test_user):
    """Test match_value_by_llm returns None when LLM finds no match."""
    # Create a value with active revision
    value = Value(user_id=test_user.id)
    db_session.add(value)
    await db_session.flush()
    
    revision = ValueRevision(
        value_id=value.id,
        statement="Test value",
        weight_raw=100,
        is_active=True,
    )
    db_session.add(revision)
    await db_session.flush()
    
    value.active_revision_id = revision.id
    await db_session.commit()
    
    # Mock the LLM response with null match
    with patch("app.api.helpers.value_helpers.llm_client") as mock_llm:
        mock_llm.chat_completion = AsyncMock(return_value={
            "choices": [{"message": {"content": '{"value_id": null}'}}]
        })
        
        result = await match_value_by_llm(db_session, test_user.id, "query")
        assert result is None


@pytest.mark.asyncio
async def test_match_value_by_llm_wrong_id(db_session, test_user):
    """Test match_value_by_llm returns None when LLM returns non-existent ID."""
    # Create a value with active revision
    value = Value(user_id=test_user.id)
    db_session.add(value)
    await db_session.flush()
    
    revision = ValueRevision(
        value_id=value.id,
        statement="Test value",
        weight_raw=100,
        is_active=True,
    )
    db_session.add(revision)
    await db_session.flush()
    
    value.active_revision_id = revision.id
    await db_session.commit()
    
    # Mock the LLM response with wrong ID
    with patch("app.api.helpers.value_helpers.llm_client") as mock_llm:
        mock_llm.chat_completion = AsyncMock(return_value={
            "choices": [{"message": {"content": '{"value_id": "wrong-id"}'}}]
        })
        
        result = await match_value_by_llm(db_session, test_user.id, "query")
        assert result is None
