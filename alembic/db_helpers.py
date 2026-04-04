"""
Database-agnostic helper functions for Alembic migrations.
Supports both PostgreSQL and SQLite.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


def is_postgresql():
    """Check if we're running against PostgreSQL."""
    return op.get_bind().dialect.name == 'postgresql'


def is_sqlite():
    """Check if we're running against SQLite."""
    return op.get_bind().dialect.name == 'sqlite'


def uuid_column():
    """Return appropriate UUID column type for the database."""
    if is_postgresql():
        return postgresql.UUID(as_uuid=False)
    return sa.String(36)


def now_default():
    """Return appropriate NOW() default for the database."""
    if is_postgresql():
        return sa.text('now()')
    return sa.text("(datetime('now'))")


def inet_column():
    """Return appropriate INET column type for the database."""
    if is_postgresql():
        return postgresql.INET()
    return sa.String(45)  # IPv6 max length


def jsonb_column():
    """Return appropriate JSON column type for the database."""
    if is_postgresql():
        return postgresql.JSONB()
    return sa.JSON()
