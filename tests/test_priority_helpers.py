"""Tests for priority_helpers module."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi import HTTPException

from app.api.helpers.priority_helpers import (
    get_priority_or_404,
    build_priority_response,
    get_linked_values_for_revision,
    create_value_links,
    validate_and_raise,
)
from app.models.priority import Priority, PriorityRevision
from app.models.priority_value_link import PriorityValueLink
from app.models.value import Value, ValueRevision
from app.schemas.priorities import PriorityResponse


@pytest.mark.asyncio
async def test_get_priority_or_404_found(db_session, test_user):
    """Test get_priority_or_404 returns priority when found and owned."""
    # Create a priority
    priority = Priority(user_id=test_user.id)
    db_session.add(priority)
    await db_session.flush()
    
    result = await get_priority_or_404(db_session, test_user.id, priority.id)
    
    assert result.id == priority.id
    assert result.user_id == test_user.id


@pytest.mark.asyncio
async def test_get_priority_or_404_not_found(db_session, test_user):
    """Test get_priority_or_404 raises 404 when priority doesn't exist."""
    with pytest.raises(HTTPException) as exc_info:
        await get_priority_or_404(db_session, test_user.id, "nonexistent-id")
    
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Priority not found"


@pytest.mark.asyncio
async def test_get_priority_or_404_wrong_owner(db_session, test_user):
    """Test get_priority_or_404 raises 404 when user doesn't own priority."""
    # Create a priority owned by test_user
    priority = Priority(user_id=test_user.id)
    db_session.add(priority)
    await db_session.flush()
    
    # Try to access with a different user_id
    with pytest.raises(HTTPException) as exc_info:
        await get_priority_or_404(db_session, "different-user-id", priority.id)
    
    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Priority not found"


def test_build_priority_response():
    """Test build_priority_response creates correct response."""
    # Create mock priority with required attributes
    priority = MagicMock(spec=Priority)
    priority.id = "test-id"
    priority.user_id = "user-id"
    priority.active_revision_id = None
    priority.active_revision = None
    priority.is_stashed = False
    priority.created_at = datetime.now(timezone.utc)
    priority.updated_at = datetime.now(timezone.utc)
    
    # Should not raise
    response = build_priority_response(priority)
    assert response is not None
    assert response.id == "test-id"


@pytest.mark.asyncio
async def test_create_value_links_empty(db_session):
    """Test create_value_links does nothing with empty list."""
    await create_value_links(db_session, "revision-id", None)
    await create_value_links(db_session, "revision-id", [])
    # Should complete without error


@pytest.mark.asyncio
async def test_create_value_links_with_values(db_session, test_user):
    """Test create_value_links creates links for valid values."""
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
    
    # Create a priority revision
    priority = Priority(user_id=test_user.id)
    db_session.add(priority)
    await db_session.flush()
    
    priority_rev = PriorityRevision(
        priority_id=priority.id,
        title="Test",
        why_matters="Test why",
        is_active=True,
    )
    db_session.add(priority_rev)
    await db_session.flush()
    
    # Create value links
    await create_value_links(db_session, priority_rev.id, [value.id])
    await db_session.flush()
    
    # Verify link was created
    from sqlalchemy import select
    result = await db_session.execute(
        select(PriorityValueLink).where(
            PriorityValueLink.priority_revision_id == priority_rev.id
        )
    )
    links = result.scalars().all()
    assert len(links) == 1
    assert links[0].value_revision_id == revision.id


@pytest.mark.asyncio
async def test_create_value_links_skips_invalid_values(db_session, test_user):
    """Test create_value_links skips values without active revision."""
    # Create a value without active revision
    value = Value(user_id=test_user.id)
    db_session.add(value)
    await db_session.flush()
    
    # Create a priority revision
    priority = Priority(user_id=test_user.id)
    db_session.add(priority)
    await db_session.flush()
    
    priority_rev = PriorityRevision(
        priority_id=priority.id,
        title="Test",
        why_matters="Test why",
        is_active=True,
    )
    db_session.add(priority_rev)
    await db_session.flush()
    
    # Try to create value links (should skip since no active revision)
    await create_value_links(db_session, priority_rev.id, [value.id, "nonexistent-id"])
    await db_session.flush()
    
    # Verify no links created
    from sqlalchemy import select
    result = await db_session.execute(
        select(PriorityValueLink).where(
            PriorityValueLink.priority_revision_id == priority_rev.id
        )
    )
    links = result.scalars().all()
    assert len(links) == 0


@pytest.mark.asyncio
async def test_validate_and_raise_valid():
    """Test validate_and_raise passes for valid input."""
    with patch("app.services.priority_validation.validate_priority") as mock:
        async def async_return(*args, **kwargs):
            return {"overall_valid": True}
        mock.side_effect = async_return
        await validate_and_raise("Title", "Why")
        mock.assert_called_once_with("Title", "Why")


@pytest.mark.asyncio
async def test_validate_and_raise_invalid():
    """Test validate_and_raise raises HTTPException for invalid input."""
    with patch("app.services.priority_validation.validate_priority") as mock:
        async def async_return(*args, **kwargs):
            return {
                "overall_valid": False,
                "name_feedback": ["Name too short"],
                "why_feedback": ["Why not meaningful"],
            }
        mock.side_effect = async_return
        
        with pytest.raises(HTTPException) as exc_info:
            await validate_and_raise("X", "Y")
        
        assert exc_info.value.status_code == 400
        assert "Priority validation failed" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_linked_values_for_revision_empty(db_session, test_user):
    """Test get_linked_values_for_revision with no links."""
    # Create a priority revision
    priority = Priority(user_id=test_user.id)
    db_session.add(priority)
    await db_session.flush()
    
    priority_rev = PriorityRevision(
        priority_id=priority.id,
        title="Test",
        why_matters="Test why",
        is_active=True,
    )
    db_session.add(priority_rev)
    await db_session.flush()
    
    result = await get_linked_values_for_revision(db_session, priority_rev.id)
    assert result == []


@pytest.mark.asyncio
async def test_get_linked_values_for_revision_with_links(db_session, test_user):
    """Test get_linked_values_for_revision returns linked values."""
    # Create a value with active revision
    value = Value(user_id=test_user.id)
    db_session.add(value)
    await db_session.flush()
    
    value_rev = ValueRevision(
        value_id=value.id,
        statement="Test value statement",
        weight_raw=100,
        is_active=True,
    )
    db_session.add(value_rev)
    await db_session.flush()
    
    value.active_revision_id = value_rev.id
    
    # Create a priority with revision
    priority = Priority(user_id=test_user.id)
    db_session.add(priority)
    await db_session.flush()
    
    priority_rev = PriorityRevision(
        priority_id=priority.id,
        title="Test",
        why_matters="Test why",
        is_active=True,
    )
    db_session.add(priority_rev)
    await db_session.flush()
    
    # Create link
    link = PriorityValueLink(
        priority_revision_id=priority_rev.id,
        value_revision_id=value_rev.id,
        link_weight=1.0,
    )
    db_session.add(link)
    await db_session.flush()
    
    result = await get_linked_values_for_revision(db_session, priority_rev.id)
    
    assert len(result) == 1
    assert result[0].value_id == value.id
    assert result[0].value_statement == "Test value statement"
    assert result[0].link_weight == 1.0
