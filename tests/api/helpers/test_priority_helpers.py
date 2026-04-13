"""Tests for priority_helpers module."""

import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock
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


@pytest.mark.asyncio
async def test_get_priority_or_404_found(db_session, test_user):
    priority = Priority(user_id=test_user.id)
    db_session.add(priority)
    await db_session.flush()

    result = await get_priority_or_404(db_session, test_user.id, priority.id)
    assert result.id == priority.id
    assert result.user_id == test_user.id


@pytest.mark.asyncio
async def test_get_priority_or_404_not_found(db_session, test_user):
    with pytest.raises(HTTPException) as exc_info:
        await get_priority_or_404(db_session, test_user.id, "nonexistent-id")

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Priority not found"


@pytest.mark.asyncio
async def test_get_priority_or_404_wrong_owner(db_session, test_user):
    priority = Priority(user_id=test_user.id)
    db_session.add(priority)
    await db_session.flush()

    with pytest.raises(HTTPException) as exc_info:
        await get_priority_or_404(db_session, "different-user-id", priority.id)

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Priority not found"


def test_build_priority_response():
    priority = MagicMock(spec=Priority)
    priority.id = "test-id"
    priority.user_id = "user-id"
    priority.active_revision_id = None
    priority.active_revision = None
    priority.is_stashed = False
    priority.created_at = datetime.now(timezone.utc)
    priority.updated_at = datetime.now(timezone.utc)

    response = build_priority_response(priority)
    assert response is not None
    assert response.id == "test-id"


@pytest.mark.asyncio
async def test_create_value_links_empty(db_session):
    await create_value_links(db_session, "revision-id", None)
    await create_value_links(db_session, "revision-id", [])


@pytest.mark.asyncio
async def test_create_value_links_with_values(db_session, test_user):
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

    await create_value_links(db_session, priority_rev.id, [value.id])
    await db_session.flush()

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
    value = Value(user_id=test_user.id)
    db_session.add(value)
    await db_session.flush()

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

    await create_value_links(db_session, priority_rev.id, [value.id, "nonexistent-id"])
    await db_session.flush()

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
    with patch("app.services.priority_validation.validate_priority") as mock:
        async def async_return(*args, **kwargs):
            return {"overall_valid": True}

        mock.side_effect = async_return
        await validate_and_raise("Title", "Why")
        mock.assert_called_once_with("Title", "Why")


@pytest.mark.asyncio
async def test_validate_and_raise_invalid():
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
