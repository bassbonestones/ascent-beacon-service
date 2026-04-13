"""Migrated tests from test_pure_functions.py (slice 1)."""

"""
Pure unit tests for schemas, model methods, and core utilities.
No database or async required - these test pure Python logic.

Target: Branch coverage for non-DB logic.
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock
from uuid import uuid4

from pydantic import ValidationError as PydanticValidationError

# Schema imports
from app.schemas.dependency import (
    CreateDependencyRuleRequest,
    DependencyBlocker,
    DependencyStatusResponse,
    TaskInfo,
)
from app.schemas.values import ValueResponse, ValueRevisionResponse

# Core utility imports
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_random_token,
    generate_verification_code,
    hash_token,
)
from app.core.exceptions import (
    AscentBeaconError,
    ValidationError,
    NotFoundError,
    AuthenticationError,
    TokenExpiredError,
    InvalidTokenError,
    ForbiddenError,
    OwnershipError,
    BadRequestError,
)

class TestDBTypes:
    """Test custom SQLAlchemy types."""

    def test_inet_process_bind(self):
        """INET passes value through on bind."""
        from app.core.db_types import INET
        inet = INET()
        
        assert inet.process_bind_param("192.168.1.1", None) == "192.168.1.1"
        assert inet.process_bind_param(None, None) is None

    def test_inet_process_result(self):
        """INET passes value through on result."""
        from app.core.db_types import INET
        inet = INET()
        
        assert inet.process_result_value("10.0.0.1", None) == "10.0.0.1"
        assert inet.process_result_value(None, None) is None

    def test_compatible_vector_init(self):
        """CompatibleVector initializes with dimensions."""
        from app.core.db_types import CompatibleVector
        vt = CompatibleVector(dimensions=768)
        assert vt.dimensions == 768

    def test_compatible_vector_process_bind_sqlite(self):
        """CompatibleVector converts list to JSON string for SQLite."""
        from app.core.db_types import CompatibleVector
        from unittest.mock import Mock
        import json
        
        vt = CompatibleVector()
        dialect = Mock()
        dialect.name = "sqlite"
        
        result = vt.process_bind_param([1.0, 2.0, 3.0], dialect)
        assert result == json.dumps([1.0, 2.0, 3.0])
        
        assert vt.process_bind_param(None, dialect) is None

    def test_compatible_vector_process_result_sqlite(self):
        """CompatibleVector parses JSON string result for SQLite."""
        from app.core.db_types import CompatibleVector
        from unittest.mock import Mock
        import json
        
        vt = CompatibleVector()
        dialect = Mock()
        dialect.name = "sqlite"
        
        result = vt.process_result_value(json.dumps([1.0, 2.0, 3.0]), dialect)
        assert result == [1.0, 2.0, 3.0]

    def test_compatible_vector_process_result_none(self):
        """CompatibleVector handles None result."""
        from app.core.db_types import CompatibleVector
        from unittest.mock import Mock
        
        vt = CompatibleVector()
        dialect = Mock()
        dialect.name = "sqlite"
        
        assert vt.process_result_value(None, dialect) is None


# =============================================================================
# Recurrence Service Tests
# =============================================================================

class TestDbTypesDialects:
    """Test database types dialect handling."""

    def test_compatible_json_postgresql(self):
        """CompatibleJSON uses JSONB on PostgreSQL."""
        from app.core.db_types import CompatibleJSON
        from unittest.mock import MagicMock
        
        jsonb = CompatibleJSON()
        
        mock_dialect = MagicMock()
        mock_dialect.name = "postgresql"
        mock_dialect.type_descriptor = MagicMock(return_value="PG_JSONB")
        
        result = jsonb.load_dialect_impl(mock_dialect)
        
        mock_dialect.type_descriptor.assert_called_once()

    def test_compatible_json_sqlite(self):
        """CompatibleJSON uses JSON on SQLite."""
        from app.core.db_types import CompatibleJSON
        from unittest.mock import MagicMock
        
        jsonb = CompatibleJSON()
        
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"
        mock_dialect.type_descriptor = MagicMock(return_value="JSON")
        
        result = jsonb.load_dialect_impl(mock_dialect)
        
        mock_dialect.type_descriptor.assert_called_once()

    def test_compatible_vector_postgresql(self):
        """CompatibleVector uses pgvector on PostgreSQL."""
        from app.core.db_types import CompatibleVector
        from unittest.mock import MagicMock, patch
        
        vec = CompatibleVector(dimensions=1536)
        
        mock_dialect = MagicMock()
        mock_dialect.name = "postgresql"
        mock_dialect.type_descriptor = MagicMock(return_value="Vector")
        
        with patch("pgvector.sqlalchemy.Vector") as mock_vector:
            mock_vector.return_value = "Vector(1536)"
            result = vec.load_dialect_impl(mock_dialect)
            
            mock_dialect.type_descriptor.assert_called_once()

    def test_compatible_vector_sqlite(self):
        """CompatibleVector uses Text on SQLite."""
        from app.core.db_types import CompatibleVector
        from unittest.mock import MagicMock
        
        vec = CompatibleVector(dimensions=1536)
        
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"
        mock_dialect.type_descriptor = MagicMock(return_value="Text")
        
        result = vec.load_dialect_impl(mock_dialect)
        
        mock_dialect.type_descriptor.assert_called_once()

    def test_compatible_vector_process_bind_sqlite(self):
        """CompatibleVector serializes to JSON for SQLite bind."""
        from app.core.db_types import CompatibleVector
        from unittest.mock import MagicMock
        import json
        
        vec = CompatibleVector(dimensions=3)
        
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"
        
        value = [0.1, 0.2, 0.3]
        result = vec.process_bind_param(value, mock_dialect)
        
        assert result == json.dumps(value)

    def test_compatible_vector_process_result_sqlite(self):
        """CompatibleVector deserializes from JSON for SQLite result."""
        from app.core.db_types import CompatibleVector
        from unittest.mock import MagicMock
        import json
        
        vec = CompatibleVector(dimensions=3)
        
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"
        
        value = "[0.1, 0.2, 0.3]"
        result = vec.process_result_value(value, mock_dialect)
        
        assert result == [0.1, 0.2, 0.3]

    def test_compatible_vector_process_bind_none(self):
        """CompatibleVector handles None bind value."""
        from app.core.db_types import CompatibleVector
        from unittest.mock import MagicMock
        
        vec = CompatibleVector(dimensions=3)
        
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"
        
        result = vec.process_bind_param(None, mock_dialect)
        
        assert result is None

    def test_compatible_vector_process_result_none(self):
        """CompatibleVector handles None result value."""
        from app.core.db_types import CompatibleVector
        from unittest.mock import MagicMock
        
        vec = CompatibleVector(dimensions=3)
        
        mock_dialect = MagicMock()
        mock_dialect.name = "sqlite"
        
        result = vec.process_result_value(None, mock_dialect)
        
        assert result is None

    def test_compatible_vector_process_bind_postgresql(self):
        """CompatibleVector passes value through for PostgreSQL bind."""
        from app.core.db_types import CompatibleVector
        from unittest.mock import MagicMock
        
        vec = CompatibleVector(dimensions=3)
        
        mock_dialect = MagicMock()
        mock_dialect.name = "postgresql"
        
        value = [0.1, 0.2, 0.3]
        result = vec.process_bind_param(value, mock_dialect)
        
        # PostgreSQL uses pgvector directly, returns value as-is
        assert result == value

    def test_compatible_vector_process_result_postgresql(self):
        """CompatibleVector converts postgres result to list."""
        from app.core.db_types import CompatibleVector
        from unittest.mock import MagicMock
        
        vec = CompatibleVector(dimensions=3)
        
        mock_dialect = MagicMock()
        mock_dialect.name = "postgresql"
        
        # Simulate pgvector returning something iterable
        value = [0.1, 0.2, 0.3]
        result = vec.process_result_value(value, mock_dialect)
        
        assert result == [0.1, 0.2, 0.3]
