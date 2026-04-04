"""Database type compatibility for PostgreSQL and SQLite.

This module provides type aliases that work with both PostgreSQL and SQLite,
allowing tests to run on SQLite while production uses PostgreSQL.
"""

from typing import Any

from sqlalchemy import String, Text, JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB as PG_JSONB
from sqlalchemy.types import TypeDecorator


class INET(TypeDecorator[str]):
    """IP address type that works with both PostgreSQL and SQLite.
    
    In PostgreSQL, this would ideally use the native INET type,
    but we use String for portability. IP validation should happen
    at the application layer.
    """
    
    impl = String(45)  # Max length for IPv6
    cache_ok = True
    
    def process_bind_param(self, value: str | None, dialect: Any) -> str | None:
        return value
    
    def process_result_value(self, value: str | None, dialect: Any) -> str | None:
        return value


class CompatibleJSON(TypeDecorator[dict[str, Any]]):
    """JSON type that uses JSONB on PostgreSQL and JSON on SQLite.
    
    PostgreSQL's JSONB provides better indexing and query performance,
    but standard JSON works fine for SQLite testing.
    """
    
    impl = JSON
    cache_ok = True
    
    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(PG_JSONB())  # type: ignore[no-untyped-call]
        return dialect.type_descriptor(JSON())


# Re-export UUID for convenience (works with both via as_uuid=False)
UUID = PG_UUID


# For embeddings - store as JSON array in SQLite, use pgvector in PostgreSQL
class CompatibleVector(TypeDecorator[list[float]]):
    """Vector type that uses pgvector on PostgreSQL and JSON on SQLite.
    
    This allows running tests on SQLite while using the efficient pgvector
    extension in production PostgreSQL.
    """
    
    impl = Text
    cache_ok = True
    
    def __init__(self, dimensions: int = 1536):
        super().__init__()
        self.dimensions = dimensions
    
    def load_dialect_impl(self, dialect: Any) -> Any:
        if dialect.name == "postgresql":
            # Import here to avoid issues when pgvector isn't installed
            from pgvector.sqlalchemy import Vector
            return dialect.type_descriptor(Vector(self.dimensions))
        return dialect.type_descriptor(Text())
    
    def process_bind_param(self, value: list[float] | None, dialect: Any) -> Any:
        if value is None:
            return None
        if dialect.name != "postgresql":
            # Store as JSON string for SQLite
            import json
            return json.dumps(value)
        return value
    
    def process_result_value(self, value: Any, dialect: Any) -> list[float] | None:
        if value is None:
            return None
        if dialect.name != "postgresql" and isinstance(value, str):
            import json
            result: list[float] = json.loads(value)
            return result
        return list(value) if value is not None else None
