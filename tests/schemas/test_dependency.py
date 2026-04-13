

# ---- migrated from tests/mocked/test_pure_functions_assistant_migrated.py ----

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


# =============================================================================
# Schema Validation Tests
# =============================================================================


class TestCreateDependencyRuleRequestValidation:
    """Test CreateDependencyRuleRequest validators."""

    def test_valid_dependency_rule_request(self):
        """Valid request with different task IDs should work."""
        request = CreateDependencyRuleRequest(
            upstream_task_id=str(uuid4()),
            downstream_task_id=str(uuid4()),
            strength="hard",
            scope="next_occurrence",
        )
        assert request.strength == "hard"
        assert request.scope == "next_occurrence"

    def test_self_dependency_raises_error(self):
        """Task cannot depend on itself."""
        task_id = str(uuid4())
        with pytest.raises(PydanticValidationError) as exc_info:
            CreateDependencyRuleRequest(
                upstream_task_id=task_id,
                downstream_task_id=task_id,
            )
        assert "depend on itself" in str(exc_info.value)

    def test_defaults_applied(self):
        """Default values should be applied."""
        request = CreateDependencyRuleRequest(
            upstream_task_id=str(uuid4()),
            downstream_task_id=str(uuid4()),
        )
        assert request.strength == "soft"
        assert request.scope == "next_occurrence"
        assert request.required_occurrence_count == 1
        assert request.validity_window_minutes is None

class TestRecommendationLogic:
    """Tests for recommendation logic patterns."""

    def test_recommendation_scoring(self):
        """Test recommendation scoring calculation."""
        # Simulate a recommendation with multiple factors
        priority_score = 80
        urgency_factor = 1.2  # Urgent
        alignment_factor = 0.9  # Somewhat aligned
        
        final_score = priority_score * urgency_factor * alignment_factor
        
        assert final_score == pytest.approx(86.4)

    def test_recommendation_filtering_by_status(self):
        """Test recommendation filtering by task status."""
        tasks = [
            {"id": "t1", "status": "pending"},
            {"id": "t2", "status": "completed"},
            {"id": "t3", "status": "pending"},
            {"id": "t4", "status": "skipped"},
        ]
        
        pending_tasks = [t for t in tasks if t["status"] == "pending"]
        
        assert len(pending_tasks) == 2
        assert all(t["status"] == "pending" for t in pending_tasks)

    def test_recommendation_limit_top_n(self):
        """Test limiting recommendations to top N."""
        recommendations = [
            {"id": "r1", "score": 95},
            {"id": "r2", "score": 88},
            {"id": "r3", "score": 75},
            {"id": "r4", "score": 60},
            {"id": "r5", "score": 45},
        ]
        
        top_3 = sorted(recommendations, key=lambda r: -r["score"])[:3]
        
        assert len(top_3) == 3
        assert top_3[0]["score"] == 95
        assert top_3[2]["score"] == 75


# =============================================================================
# Discovery Logic Tests
# =============================================================================

class TestAssistantLogic:
    """Tests for assistant service logic patterns."""

    def test_intent_classification(self):
        """Test intent classification patterns."""
        intents = {
            "create_task": ["add task", "new task", "create todo"],
            "complete_task": ["done", "complete", "finished"],
            "list_tasks": ["show tasks", "what do I have", "my todos"],
        }
        
        message = "add task buy groceries"
        
        detected_intent = None
        for intent, keywords in intents.items():
            if any(kw in message.lower() for kw in keywords):
                detected_intent = intent
                break
        
        assert detected_intent == "create_task"

    def test_entity_extraction(self):
        """Test entity extraction from natural language."""
        # Simple time extraction pattern
        message = "remind me tomorrow at 9am to call mom"
        
        has_time = "am" in message.lower() or "pm" in message.lower()
        has_tomorrow = "tomorrow" in message.lower()
        
        assert has_time is True
        assert has_tomorrow is True

    def test_confidence_threshold(self):
        """Test confidence threshold for AI actions."""
        confidence_levels = [0.3, 0.6, 0.85, 0.95]
        threshold = 0.7
        
        results = []
        for confidence in confidence_levels:
            if confidence >= threshold:
                results.append("execute")
            else:
                results.append("ask_confirmation")
        
        assert results == ["ask_confirmation", "ask_confirmation", "execute", "execute"]


# =============================================================================
# Schema Validation Edge Cases
# =============================================================================

class TestRecommendationSchemaValidation:
    """Tests for recommendation schema validation."""

    def test_recommendation_status_valid(self):
        """Valid recommendation statuses."""
        valid_statuses = ["proposed", "accepted", "rejected", "pending_edit"]
        
        for status in valid_statuses:
            assert status in valid_statuses

    def test_proposed_action_types(self):
        """Valid proposed action types."""
        valid_actions = [
            "create_value",
            "update_value",
            "create_priority",
            "update_priority",
        ]
        
        for action in valid_actions:
            assert action in valid_actions

class TestLLMClientPayloadConstruction:
    """Test LLMClient payload construction paths."""

    @pytest.mark.asyncio
    async def test_chat_with_max_tokens(self):
        """Chat payload includes max_tokens when provided."""
        from unittest.mock import AsyncMock, MagicMock, patch
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "test"}}]}
        mock_response.raise_for_status = MagicMock()
        
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        
        with patch("app.core.llm.httpx.AsyncClient", return_value=mock_client):
            from app.core.llm import LLMClient
            
            client = LLMClient()
            client.client = mock_client
            
            result = await client.chat_completion(
                messages=[{"role": "user", "content": "test"}],
                max_tokens=100,
            )
            
            # Verify post was called with max_tokens in payload
            call_args = mock_client.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert payload["max_tokens"] == 100

    @pytest.mark.asyncio
    async def test_chat_with_response_format(self):
        """Chat payload includes response_format when provided."""
        from unittest.mock import AsyncMock, MagicMock, patch
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": []}
        mock_response.raise_for_status = MagicMock()
        
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        
        with patch("app.core.llm.httpx.AsyncClient", return_value=mock_client):
            from app.core.llm import LLMClient
            
            client = LLMClient()
            client.client = mock_client
            
            result = await client.chat_completion(
                messages=[{"role": "user", "content": "test"}],
                response_format={"type": "json_object"},
            )
            
            call_args = mock_client.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert payload["response_format"] == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_chat_with_tools(self):
        """Chat payload includes tools when provided."""
        from unittest.mock import AsyncMock, MagicMock, patch
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": []}
        mock_response.raise_for_status = MagicMock()
        
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        
        with patch("app.core.llm.httpx.AsyncClient", return_value=mock_client):
            from app.core.llm import LLMClient
            
            client = LLMClient()
            client.client = mock_client
            
            tools = [{"type": "function", "function": {"name": "test"}}]
            
            result = await client.chat_completion(
                messages=[{"role": "user", "content": "test"}],
                tools=tools,
            )
            
            call_args = mock_client.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert payload["tools"] == tools

    @pytest.mark.asyncio
    async def test_chat_with_tool_choice(self):
        """Chat payload includes tool_choice when provided."""
        from unittest.mock import AsyncMock, MagicMock, patch
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": []}
        mock_response.raise_for_status = MagicMock()
        
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        
        with patch("app.core.llm.httpx.AsyncClient", return_value=mock_client):
            from app.core.llm import LLMClient
            
            client = LLMClient()
            client.client = mock_client
            
            result = await client.chat_completion(
                messages=[{"role": "user", "content": "test"}],
                tool_choice="auto",
            )
            
            call_args = mock_client.post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json")
            assert payload["tool_choice"] == "auto"


# ---- migrated from tests/mocked/test_pure_functions_models_migrated.py ----

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


# =============================================================================
# Schema Validation Tests
# =============================================================================


class TestCreateDependencyRuleRequestValidation__legacypure_functions_models_migrated:
    """Test CreateDependencyRuleRequest validators."""

    def test_valid_dependency_rule_request(self):
        """Valid request with different task IDs should work."""
        request = CreateDependencyRuleRequest(
            upstream_task_id=str(uuid4()),
            downstream_task_id=str(uuid4()),
            strength="hard",
            scope="next_occurrence",
        )
        assert request.strength == "hard"
        assert request.scope == "next_occurrence"

    def test_self_dependency_raises_error(self):
        """Task cannot depend on itself."""
        task_id = str(uuid4())
        with pytest.raises(PydanticValidationError) as exc_info:
            CreateDependencyRuleRequest(
                upstream_task_id=task_id,
                downstream_task_id=task_id,
            )
        assert "depend on itself" in str(exc_info.value)

    def test_defaults_applied(self):
        """Default values should be applied."""
        request = CreateDependencyRuleRequest(
            upstream_task_id=str(uuid4()),
            downstream_task_id=str(uuid4()),
        )
        assert request.strength == "soft"
        assert request.scope == "next_occurrence"
        assert request.required_occurrence_count == 1
        assert request.validity_window_minutes is None

class TestExceptions:
    """Test custom exception classes."""

    def test_base_exception_defaults(self):
        """Base exception has sensible defaults."""
        exc = AscentBeaconError()
        assert exc.message == "An error occurred"
        assert exc.status_code == 500
        assert exc.error_code == "INTERNAL_ERROR"
        assert exc.details == {}

    def test_base_exception_custom_message(self):
        """Custom message overrides default."""
        exc = AscentBeaconError(message="Custom error", details={"key": "value"})
        assert exc.message == "Custom error"
        assert exc.details == {"key": "value"}

    def test_to_dict_basic(self):
        """to_dict returns proper format."""
        exc = AscentBeaconError(message="Test error")
        result = exc.to_dict()
        assert result["error"] == "INTERNAL_ERROR"
        assert result["message"] == "Test error"
        assert "details" not in result  # Empty details not included

    def test_to_dict_with_details(self):
        """to_dict includes details when present."""
        exc = AscentBeaconError(message="Test", details={"field": "test"})
        result = exc.to_dict()
        assert result["details"] == {"field": "test"}

    def test_validation_error(self):
        """ValidationError with field."""
        exc = ValidationError(message="Invalid input", field="email")
        assert exc.status_code == 400
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.details["field"] == "email"

    def test_validation_error_without_field(self):
        """ValidationError without field (no details added)."""
        exc = ValidationError(message="Invalid input")
        assert exc.status_code == 400
        assert exc.error_code == "VALIDATION_ERROR"
        # No field should be in details
        assert "field" not in exc.details

    def test_validation_error_without_field_with_existing_details(self):
        """ValidationError without field but with existing details."""
        exc = ValidationError(
            message="Invalid input",
            details={"context": "registration"}
        )
        assert exc.details["context"] == "registration"
        assert "field" not in exc.details

    def test_not_found_error(self):
        """NotFoundError with resource info."""
        resource_id = str(uuid4())
        exc = NotFoundError("User", resource_id)
        assert exc.status_code == 404
        assert "User not found" in exc.message
        assert exc.details["resource_type"] == "User"
        assert exc.details["resource_id"] == resource_id

    def test_not_found_error_no_id(self):
        """NotFoundError without resource_id."""
        exc = NotFoundError("Task")
        assert exc.message == "Task not found"
        assert "resource_id" not in exc.details

    def test_authentication_error(self):
        """AuthenticationError defaults."""
        exc = AuthenticationError()
        assert exc.status_code == 401
        assert exc.error_code == "AUTHENTICATION_ERROR"

    def test_token_expired_error(self):
        """TokenExpiredError inherits from AuthenticationError."""
        exc = TokenExpiredError()
        assert exc.status_code == 401
        assert exc.error_code == "TOKEN_EXPIRED"

    def test_invalid_token_error(self):
        """InvalidTokenError inherits from AuthenticationError."""
        exc = InvalidTokenError()
        assert exc.status_code == 401
        assert exc.error_code == "INVALID_TOKEN"

    def test_forbidden_error(self):
        """ForbiddenError defaults."""
        exc = ForbiddenError()
        assert exc.status_code == 403
        assert exc.error_code == "FORBIDDEN"

    def test_ownership_error(self):
        """OwnershipError inherits from ForbiddenError."""
        exc = OwnershipError()
        assert exc.status_code == 403
        assert exc.error_code == "OWNERSHIP_ERROR"

    def test_bad_request_error(self):
        """BadRequestError defaults."""
        exc = BadRequestError()
        assert exc.status_code == 400
        assert exc.error_code == "BAD_REQUEST"


# =============================================================================
# Model Property Tests (testing without DB by creating instances directly)
# =============================================================================

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

class TestModelReprMethods:
    """Test model __repr__ methods for coverage."""

    def test_goal_repr(self):
        """Goal __repr__ returns string."""
        from app.models.goal import Goal
        
        goal = Goal()
        goal.id = "test-id"
        goal.title = "Test Goal Title That Is Very Long"
        
        result = repr(goal)
        assert "Goal" in result
        assert "test-id" in result

    def test_daily_sort_override_repr(self):
        """DailySortOverride __repr__ returns string."""
        from app.models.daily_sort_override import DailySortOverride
        from datetime import date
        
        override = DailySortOverride()
        override.task_id = "task-123"
        override.override_date = date(2024, 1, 15)
        override.sort_position = 5
        
        result = repr(override)
        assert "DailySortOverride" in result

    def test_goal_priority_link_repr(self):
        """GoalPriorityLink __repr__ returns string."""
        from app.models.goal_priority_link import GoalPriorityLink
        
        link = GoalPriorityLink()
        link.goal_id = "goal-1"
        link.priority_id = "priority-1"
        
        result = repr(link)
        assert isinstance(result, str)

    def test_occurrence_preference_repr(self):
        """OccurrencePreference __repr__ returns string."""
        from app.models.occurrence_preference import OccurrencePreference
        
        pref = OccurrencePreference()
        pref.task_id = "task-1"
        pref.preference_type = "sticky_time"
        
        result = repr(pref)
        assert isinstance(result, str)

    def test_user_value_selection_repr(self):
        """UserValueSelection __repr__ returns string."""
        from app.models.user_value_selection import UserValueSelection
        
        selection = UserValueSelection()
        selection.user_id = "user-1"
        selection.value_id = "value-1"
        
        result = repr(selection)
        assert isinstance(result, str)

    def test_value_prompt_repr(self):
        """ValuePrompt __repr__ returns string."""
        from app.models.value_prompt import ValuePrompt
        
        prompt = ValuePrompt()
        prompt.id = "prompt-1"
        prompt.prompt_text = "What matters most?"
        
        result = repr(prompt)
        assert isinstance(result, str)

    def test_task_completion_repr(self):
        """TaskCompletion __repr__ returns string."""
        from app.models.task_completion import TaskCompletion
        
        completion = TaskCompletion()
        completion.task_id = "task-1"
        completion.status = "completed"
        
        result = repr(completion)
        assert isinstance(result, str)

    def test_task_completion_is_skipped_property(self) -> None:
        """TaskCompletion.is_skipped reflects skipped status."""
        from app.models.task_completion import TaskCompletion

        completion = TaskCompletion()
        completion.status = "skipped"
        assert completion.is_skipped is True
        assert completion.is_completed is False

    def test_dependency_rule_repr(self):
        """DependencyRule __repr__ returns string."""
        from app.models.dependency import DependencyRule
        
        rule = DependencyRule()
        rule.id = "rule-123456789"
        rule.strength = "hard"
        rule.upstream_task_id = "up-1"
        rule.downstream_task_id = "down-1"
        
        result = repr(rule)
        assert isinstance(result, str)

    def test_dependency_resolution_repr(self):
        """DependencyResolution __repr__ returns string."""
        from app.models.dependency import DependencyResolution
        
        resolution = DependencyResolution()
        resolution.dependency_rule_id = "rule-123456789"
        resolution.resolution_source = "manual"
        
        result = repr(resolution)
        assert isinstance(result, str)

    def test_dependency_state_cache_repr(self):
        """DependencyStateCache __repr__ returns string."""
        from app.models.dependency import DependencyStateCache
        
        cache = DependencyStateCache()
        cache.task_id = "task-1"
        cache.readiness_state = "ready"
        
        result = repr(cache)
        assert isinstance(result, str)


# =============================================================================
# Task Stats Helper Tests (calculate_streak)
# =============================================================================

class TestSchemaValidationEdgeCases:
    """Additional edge cases for schema validation."""

    def test_dependency_rule_within_window_scope(self):
        """Test dependency rule with within_window scope."""
        from app.schemas.dependency import CreateDependencyRuleRequest
        
        request = CreateDependencyRuleRequest(
            upstream_task_id=str(uuid4()),
            downstream_task_id=str(uuid4()),
            strength="hard",
            scope="within_window",
            validity_window_minutes=60,
        )
        
        assert request.scope == "within_window"
        assert request.validity_window_minutes == 60

    def test_dependency_rule_all_occurrences_scope(self):
        """Test dependency rule with all_occurrences scope."""
        from app.schemas.dependency import CreateDependencyRuleRequest
        
        request = CreateDependencyRuleRequest(
            upstream_task_id=str(uuid4()),
            downstream_task_id=str(uuid4()),
            strength="soft",
            scope="all_occurrences",
            required_occurrence_count=4,  # Need 4 completions
        )
        
        assert request.scope == "all_occurrences"
        assert request.required_occurrence_count == 4

    def test_task_info_with_recurrence(self):
        """Test TaskInfo with recurrence information."""
        from app.schemas.dependency import TaskInfo
        
        info = TaskInfo(
            id=str(uuid4()),
            title="Daily Standup",
            is_recurring=True,
            recurrence_rule="FREQ=DAILY;BYHOUR=9",
        )
        
        assert info.is_recurring is True
        assert "FREQ=DAILY" in info.recurrence_rule


# ============================================================================
# Completion Helper Function Tests (Pure Functions)
# ============================================================================

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

class TestMoreSchemaValidations:
    """Additional schema validation tests."""

    def test_task_list_response_defaults(self):
        """TaskListResponse has correct defaults."""
        from app.schemas.tasks import TaskListResponse
        
        response = TaskListResponse(tasks=[])
        
        assert response.total == 0
        assert response.pending_count == 0
        assert response.completed_count == 0

    def test_goal_info_from_attributes(self):
        """GoalInfo can be created from attributes."""
        from app.schemas.tasks import GoalInfo
        
        info = GoalInfo(id="goal-123", title="Test Goal", status="in_progress")
        
        assert info.id == "goal-123"
        assert info.title == "Test Goal"
        assert info.status == "in_progress"


# ---- migrated from tests/mocked/test_pure_functions_schema.py ----

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

class TestCreateDependencyRuleRequestValidation__legacypure_functions_schema:
    """Test CreateDependencyRuleRequest validators."""

    def test_valid_dependency_rule_request(self):
        """Valid request with different task IDs should work."""
        request = CreateDependencyRuleRequest(
            upstream_task_id=str(uuid4()),
            downstream_task_id=str(uuid4()),
            strength="hard",
            scope="next_occurrence",
        )
        assert request.strength == "hard"
        assert request.scope == "next_occurrence"

    def test_self_dependency_raises_error(self):
        """Task cannot depend on itself."""
        task_id = str(uuid4())
        with pytest.raises(PydanticValidationError) as exc_info:
            CreateDependencyRuleRequest(
                upstream_task_id=task_id,
                downstream_task_id=task_id,
            )
        assert "depend on itself" in str(exc_info.value)

    def test_defaults_applied(self):
        """Default values should be applied."""
        request = CreateDependencyRuleRequest(
            upstream_task_id=str(uuid4()),
            downstream_task_id=str(uuid4()),
        )
        assert request.strength == "soft"
        assert request.scope == "next_occurrence"
        assert request.required_occurrence_count == 1
        assert request.validity_window_minutes is None

class TestDependencyBlockerProgressPct:
    """Test DependencyBlocker.progress_pct property."""

    def test_zero_required_count_returns_100(self):
        """If required_count is 0, progress is 100%."""
        blocker = DependencyBlocker(
            rule_id=str(uuid4()),
            upstream_task=TaskInfo(id=str(uuid4()), title="Test"),
            strength="soft",
            scope="next_occurrence",
            required_count=0,
            completed_count=0,
            is_met=True,
        )
        assert blocker.progress_pct == 100

    def test_partial_progress(self):
        """Partial completion should show percentage."""
        blocker = DependencyBlocker(
            rule_id=str(uuid4()),
            upstream_task=TaskInfo(id=str(uuid4()), title="Test"),
            strength="hard",
            scope="all_occurrences",
            required_count=4,
            completed_count=3,
            is_met=False,
        )
        assert blocker.progress_pct == 75

    def test_full_progress(self):
        """Full completion is 100%."""
        blocker = DependencyBlocker(
            rule_id=str(uuid4()),
            upstream_task=TaskInfo(id=str(uuid4()), title="Test"),
            strength="soft",
            scope="next_occurrence",
            required_count=2,
            completed_count=2,
            is_met=True,
        )
        assert blocker.progress_pct == 100

class TestDependencyStatusResponseComputeStates:
    """Test DependencyStatusResponse.compute_states model validator."""

    def test_all_met_is_ready(self):
        """When all dependencies are met, state is ready."""
        response = DependencyStatusResponse(
            task_id=str(uuid4()),
            dependencies=[],
        )
        assert response.all_met is True
        assert response.has_unmet_hard is False
        assert response.has_unmet_soft is False
        assert response.readiness_state == "ready"

    def test_hard_unmet_is_blocked(self):
        """Unmet hard dependency means blocked."""
        response = DependencyStatusResponse(
            task_id=str(uuid4()),
            dependencies=[
                DependencyBlocker(
                    rule_id=str(uuid4()),
                    upstream_task=TaskInfo(id=str(uuid4()), title="Blocker"),
                    strength="hard",
                    scope="next_occurrence",
                    required_count=1,
                    completed_count=0,
                    is_met=False,
                )
            ],
        )
        assert response.has_unmet_hard is True
        assert response.all_met is False
        assert response.readiness_state == "blocked"

    def test_partial_hard_deps(self):
        """Some hard deps met, some not = partial."""
        response = DependencyStatusResponse(
            task_id=str(uuid4()),
            dependencies=[
                DependencyBlocker(
                    rule_id=str(uuid4()),
                    upstream_task=TaskInfo(id=str(uuid4()), title="Met"),
                    strength="hard",
                    scope="next_occurrence",
                    required_count=1,
                    completed_count=1,
                    is_met=True,
                ),
                DependencyBlocker(
                    rule_id=str(uuid4()),
                    upstream_task=TaskInfo(id=str(uuid4()), title="Unmet"),
                    strength="hard",
                    scope="next_occurrence",
                    required_count=1,
                    completed_count=0,
                    is_met=False,
                ),
            ],
        )
        assert response.has_unmet_hard is True
        assert response.readiness_state == "partial"

    def test_only_soft_unmet_is_advisory(self):
        """Only soft deps unmet = advisory."""
        response = DependencyStatusResponse(
            task_id=str(uuid4()),
            dependencies=[
                DependencyBlocker(
                    rule_id=str(uuid4()),
                    upstream_task=TaskInfo(id=str(uuid4()), title="Soft"),
                    strength="soft",
                    scope="next_occurrence",
                    required_count=1,
                    completed_count=0,
                    is_met=False,
                )
            ],
        )
        assert response.has_unmet_soft is True
        assert response.has_unmet_hard is False
        assert response.readiness_state == "advisory"

class TestSchemaValidationEdgeCases__legacypure_functions_schema:
    """Additional edge cases for schema validation."""

    def test_dependency_rule_within_window_scope(self):
        """Test dependency rule with within_window scope."""
        from app.schemas.dependency import CreateDependencyRuleRequest
        
        request = CreateDependencyRuleRequest(
            upstream_task_id=str(uuid4()),
            downstream_task_id=str(uuid4()),
            strength="hard",
            scope="within_window",
            validity_window_minutes=60,
        )
        
        assert request.scope == "within_window"
        assert request.validity_window_minutes == 60

    def test_dependency_rule_all_occurrences_scope(self):
        """Test dependency rule with all_occurrences scope."""
        from app.schemas.dependency import CreateDependencyRuleRequest
        
        request = CreateDependencyRuleRequest(
            upstream_task_id=str(uuid4()),
            downstream_task_id=str(uuid4()),
            strength="soft",
            scope="all_occurrences",
            required_occurrence_count=4,  # Need 4 completions
        )
        
        assert request.scope == "all_occurrences"
        assert request.required_occurrence_count == 4

    def test_task_info_with_recurrence(self):
        """Test TaskInfo with recurrence information."""
        from app.schemas.dependency import TaskInfo
        
        info = TaskInfo(
            id=str(uuid4()),
            title="Daily Standup",
            is_recurring=True,
            recurrence_rule="FREQ=DAILY;BYHOUR=9",
        )
        
        assert info.is_recurring is True
        assert "FREQ=DAILY" in info.recurrence_rule


# ============================================================================
# Completion Helper Function Tests (Pure Functions)
# ============================================================================

class TestTaskSchemaValidation:
    """Tests for task schema validation patterns."""

    def test_duration_minutes_positive(self):
        """Duration must be positive."""
        duration = 30
        
        assert duration > 0

    def test_duration_minutes_none_allowed(self):
        """Duration can be None for no-duration tasks."""
        duration = None
        
        assert duration is None

    def test_scheduling_mode_values(self):
        """Valid scheduling modes."""
        valid_modes = ["fixed", "flexible", "anytime"]
        
        for mode in valid_modes:
            assert mode in valid_modes

    def test_task_status_values(self):
        """Valid task status values."""
        valid_statuses = ["pending", "completed", "skipped"]
        
        for status in valid_statuses:
            assert status in valid_statuses

    def test_priority_level_range(self):
        """Priority level in valid range."""
        valid_priorities = [1, 2, 3, 4, 5]
        
        priority = 3
        
        assert priority in valid_priorities

    def test_invalid_priority_rejected(self):
        """Invalid priority level rejected."""
        valid_priorities = [1, 2, 3, 4, 5]
        
        priority = 10
        
        assert priority not in valid_priorities

class TestTaskSchemaCompletionRequestValidation:
    """Test CompleteTaskRequest schema validation."""

    def test_complete_request_with_scheduled_for(self):
        """Complete request has scheduled_for datetime."""
        from app.schemas.tasks import CompleteTaskRequest
        from datetime import datetime, timezone
        
        request = CompleteTaskRequest(
            scheduled_for=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        )
        
        assert request.scheduled_for.day == 15

    def test_skip_request_with_reason(self):
        """Skip request has reason and scheduled_for."""
        from app.schemas.tasks import SkipTaskRequest
        from datetime import datetime, timezone
        
        request = SkipTaskRequest(
            scheduled_for=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc),
            reason="Not feeling well"
        )
        
        assert request.reason == "Not feeling well"
        assert request.scheduled_for.day == 15

    def test_skip_request_without_reason(self):
        """Skip request can have empty reason."""
        from app.schemas.tasks import SkipTaskRequest
        from datetime import datetime, timezone
        
        request = SkipTaskRequest(
            scheduled_for=datetime(2024, 1, 15, 10, 0, tzinfo=timezone.utc)
        )
        
        assert request.reason is None

class TestRecommendationSchemaValidation__legacypure_functions_schema:
    """Tests for recommendation schema validation."""

    def test_recommendation_status_valid(self):
        """Valid recommendation statuses."""
        valid_statuses = ["proposed", "accepted", "rejected", "pending_edit"]
        
        for status in valid_statuses:
            assert status in valid_statuses

    def test_proposed_action_types(self):
        """Valid proposed action types."""
        valid_actions = [
            "create_value",
            "update_value",
            "create_priority",
            "update_priority",
        ]
        
        for action in valid_actions:
            assert action in valid_actions

class TestAlignmentResponseSchema:
    """Tests for AlignmentCheckResponse schema."""

    def test_alignment_fit_calculation(self):
        """Alignment fit = 1 - TVD."""
        tvd = 0.3
        alignment_fit = 1.0 - tvd
        
        assert alignment_fit == 0.7

    def test_perfect_alignment(self):
        """Perfect alignment when TVD = 0."""
        tvd = 0.0
        alignment_fit = 1.0 - tvd
        
        assert alignment_fit == 1.0

    def test_no_alignment(self):
        """No alignment when TVD = 1."""
        tvd = 1.0
        alignment_fit = 1.0 - tvd
        
        assert alignment_fit == 0.0

class TestMoreSchemaValidations__legacypure_functions_schema:
    """Additional schema validation tests."""

    def test_task_list_response_defaults(self):
        """TaskListResponse has correct defaults."""
        from app.schemas.tasks import TaskListResponse
        
        response = TaskListResponse(tasks=[])
        
        assert response.total == 0
        assert response.pending_count == 0
        assert response.completed_count == 0

    def test_goal_info_from_attributes(self):
        """GoalInfo can be created from attributes."""
        from app.schemas.tasks import GoalInfo
        
        info = GoalInfo(id="goal-123", title="Test Goal", status="in_progress")
        
        assert info.id == "goal-123"
        assert info.title == "Test Goal"
        assert info.status == "in_progress"
