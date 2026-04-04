"""Tests for user model and database fixtures."""

import pytest
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


@pytest.mark.asyncio
async def test_create_user(db_session: AsyncSession):
    """Test creating a user in the database."""
    user = User(
        id=str(uuid4()),
        display_name="Test User",
        primary_email="testuser@example.com",
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    
    # Query back
    result = await db_session.execute(
        select(User).where(User.id == user.id)
    )
    found = result.scalar_one()
    
    assert found.display_name == "Test User"
    assert found.primary_email == "testuser@example.com"


@pytest.mark.asyncio
async def test_user_fixture(test_user: User):
    """Test that the test_user fixture works."""
    assert test_user.id is not None
    assert test_user.display_name == "Test User"
    assert test_user.is_email_verified is True
