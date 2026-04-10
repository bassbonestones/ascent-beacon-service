"""Test fixtures for pytest."""

# === DIRECTORY CHECK (must come before any app imports) ===
import os
import sys
from pathlib import Path

_expected_root = Path(__file__).parent.parent.resolve()
_cwd = Path.cwd().resolve()

# Fail fast with clear error if running from wrong directory
if _cwd != _expected_root:
    raise RuntimeError(
        f"\n\n❌ Tests must be run from the service directory!\n"
        f"   Expected: {_expected_root}\n"
        f"   Got:      {_cwd}\n\n"
        f"   Fix: cd {_expected_root} && pytest\n"
    )

# Ensure app is importable
if str(_expected_root) not in sys.path:
    sys.path.insert(0, str(_expected_root))
# === END DIRECTORY CHECK ===

import asyncio
import gc
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token
from app.main import app
from app.core.db import get_db
from app.models.base import Base
from app.models.user import User


# Use SQLite for tests - fast, no external dependencies
# PostgreSQL-specific types (INET, JSONB, Vector) have compatible implementations
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Use asyncio for all async tests."""
    return "asyncio"


@pytest.fixture
async def test_engine():
    """Create a test database engine with in-memory SQLite."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    # CRITICAL: Explicitly dispose engine to close aiosqlite worker threads
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a test database session with explicit cleanup."""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    session = async_session()
    try:
        yield session
    finally:
        # CRITICAL: Rollback any pending transactions then close session
        await session.rollback()
        await session.close()


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    """Create a test user."""
    user = User(
        id=str(uuid4()),
        display_name="Test User",
        primary_email=f"test-{uuid4().hex[:8]}@example.com",
        is_email_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
def auth_headers(test_user: User) -> dict[str, str]:
    """Create authorization headers for a test user."""
    token = create_access_token(user_id=test_user.id)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client(db_session: AsyncSession, test_user: User) -> AsyncGenerator[AsyncClient, None]:
    """Create an authenticated test client."""
    
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    token = create_access_token(user_id=test_user.id)
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={"Authorization": f"Bearer {token}"},
    ) as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
async def unauthenticated_client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create an unauthenticated test client."""
    
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    
    app.dependency_overrides.clear()


# Helper functions for tests

def make_user_id() -> str:
    """Generate a UUID string for user IDs."""
    return str(uuid4())


def make_value_data(statement: str = "Test value", weight: float = 0.5) -> dict[str, Any]:
    """Create test data for a value."""
    return {
        "statement": statement,
        "origin": "declared",
        "weight_raw": weight,
    }


def make_priority_data(
    title: str = "Test priority",
    score: int = 3,
    scope: str = "ongoing",
) -> dict[str, Any]:
    """Create test data for a priority."""
    return {
        "title": title,
        "why_matters": "This is why it matters",
        "score": score,
        "scope": scope,
    }
