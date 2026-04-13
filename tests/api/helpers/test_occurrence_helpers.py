"""Unit tests for occurrence_ordering helpers - pure functions extracted."""

import pytest
from datetime import datetime, timezone
from dataclasses import dataclass

from app.api.helpers.occurrence_helpers import (
    classify_tasks_by_recurrence,
    find_position_in_occurrences,
    merge_overrides_and_preferences,
    build_task_ids_from_occurrences,
    validate_all_tasks_exist,
)


# ============================================================================
# Tests for classify_tasks_by_recurrence
# ============================================================================

class TestClassifyTasksByRecurrence:
    """Tests for classify_tasks_by_recurrence function."""

    def test_empty_list_returns_empty(self):
        """Empty input returns empty outputs."""
        recurring, single = classify_tasks_by_recurrence([], {})
        assert recurring == []
        assert single == []

    def test_all_recurring(self):
        """All tasks are recurring."""
        task_ids = ["a", "b", "c"]
        recurring_map = {"a": True, "b": True, "c": True}
        recurring, single = classify_tasks_by_recurrence(task_ids, recurring_map)
        assert recurring == ["a", "b", "c"]
        assert single == []

    def test_all_single(self):
        """All tasks are non-recurring."""
        task_ids = ["a", "b", "c"]
        recurring_map = {"a": False, "b": False, "c": False}
        recurring, single = classify_tasks_by_recurrence(task_ids, recurring_map)
        assert recurring == []
        assert single == ["a", "b", "c"]

    def test_mixed_tasks(self):
        """Mix of recurring and single tasks."""
        task_ids = ["a", "b", "c", "d"]
        recurring_map = {"a": True, "b": False, "c": True, "d": False}
        recurring, single = classify_tasks_by_recurrence(task_ids, recurring_map)
        assert recurring == ["a", "c"]
        assert single == ["b", "d"]

    def test_unknown_task_treated_as_non_recurring(self):
        """Task not in map defaults to non-recurring."""
        task_ids = ["known", "unknown"]
        recurring_map = {"known": True}
        recurring, single = classify_tasks_by_recurrence(task_ids, recurring_map)
        assert recurring == ["known"]
        assert single == ["unknown"]

    def test_preserves_order(self):
        """Order of tasks is preserved in output."""
        task_ids = ["z", "a", "m", "b"]
        recurring_map = {"z": True, "a": True, "m": False, "b": False}
        recurring, single = classify_tasks_by_recurrence(task_ids, recurring_map)
        assert recurring == ["z", "a"]
        assert single == ["m", "b"]


# ============================================================================
# Tests for find_position_in_occurrences
# ============================================================================

@dataclass
class MockOccurrence:
    """Mock occurrence for testing."""
    task_id: str
    occurrence_index: int


class TestFindPositionInOccurrences:
    """Tests for find_position_in_occurrences function."""

    def test_finds_first_position(self):
        """First item has position 1."""
        occs = [MockOccurrence("t1", 0), MockOccurrence("t2", 0)]
        pos = find_position_in_occurrences(occs, "t1", 0)
        assert pos == 1

    def test_finds_last_position(self):
        """Last item has correct position."""
        occs = [MockOccurrence("t1", 0), MockOccurrence("t2", 0), MockOccurrence("t3", 0)]
        pos = find_position_in_occurrences(occs, "t3", 0)
        assert pos == 3

    def test_finds_middle_position(self):
        """Middle item has correct position."""
        occs = [MockOccurrence("t1", 0), MockOccurrence("t2", 0), MockOccurrence("t3", 0)]
        pos = find_position_in_occurrences(occs, "t2", 0)
        assert pos == 2

    def test_matches_occurrence_index(self):
        """Same task with different occurrence_index found correctly."""
        occs = [
            MockOccurrence("t1", 0),
            MockOccurrence("t1", 1),
            MockOccurrence("t1", 2),
        ]
        pos = find_position_in_occurrences(occs, "t1", 1)
        assert pos == 2

    def test_raises_for_not_found(self):
        """ValueError raised when occurrence not found."""
        occs = [MockOccurrence("t1", 0)]
        with pytest.raises(ValueError, match="Occurrence not found"):
            find_position_in_occurrences(occs, "t2", 0)

    def test_raises_for_wrong_index(self):
        """ValueError raised when task exists but index doesn't match."""
        occs = [MockOccurrence("t1", 0)]
        with pytest.raises(ValueError, match="Occurrence not found"):
            find_position_in_occurrences(occs, "t1", 1)


# ============================================================================
# Tests for merge_overrides_and_preferences
# ============================================================================

@dataclass
class MockOverride:
    """Mock daily override for testing."""
    task_id: str
    occurrence_index: int
    sort_position: int


@dataclass
class MockPreference:
    """Mock occurrence preference for testing."""
    task_id: str
    occurrence_index: int
    sequence_number: float


class TestMergeOverridesAndPreferences:
    """Tests for merge_overrides_and_preferences function."""

    def test_empty_inputs_returns_empty(self):
        """Empty inputs return empty results."""
        items, keys = merge_overrides_and_preferences([], [])
        assert items == []
        assert keys == set()

    def test_overrides_only(self):
        """Only overrides - all marked as is_override=True."""
        overrides = [
            MockOverride("t1", 0, 1),
            MockOverride("t2", 0, 2),
        ]
        items, keys = merge_overrides_and_preferences(overrides, [])

        assert len(items) == 2
        assert all(item["is_override"] for item in items)
        assert keys == {("t1", 0), ("t2", 0)}

    def test_preferences_only(self):
        """Only preferences - all marked as is_override=False."""
        prefs = [
            MockPreference("t1", 0, 1.0),
            MockPreference("t2", 0, 2.0),
        ]
        items, keys = merge_overrides_and_preferences([], prefs)

        assert len(items) == 2
        assert all(not item["is_override"] for item in items)
        assert keys == set()

    def test_override_supersedes_preference(self):
        """Override for same task/occurrence excludes preference."""
        overrides = [MockOverride("t1", 0, 5)]
        prefs = [MockPreference("t1", 0, 1.0)]

        items, keys = merge_overrides_and_preferences(overrides, prefs)

        assert len(items) == 1
        assert items[0]["task_id"] == "t1"
        assert items[0]["is_override"] is True
        assert items[0]["sort_value"] == 5.0

    def test_mixed_override_and_preference(self):
        """Mix: override takes precedence, non-conflicting prefs included."""
        overrides = [MockOverride("t1", 0, 1)]
        prefs = [
            MockPreference("t1", 0, 10.0),  # Should be excluded
            MockPreference("t2", 0, 2.0),   # Should be included
        ]

        items, keys = merge_overrides_and_preferences(overrides, prefs)

        assert len(items) == 2
        t1_item = next(i for i in items if i["task_id"] == "t1")
        t2_item = next(i for i in items if i["task_id"] == "t2")

        assert t1_item["is_override"] is True
        assert t2_item["is_override"] is False

    def test_different_occurrence_indices_both_kept(self):
        """Same task with different occurrence_index kept separately."""
        overrides = [MockOverride("t1", 0, 1)]
        prefs = [MockPreference("t1", 1, 2.0)]  # Different index

        items, keys = merge_overrides_and_preferences(overrides, prefs)

        assert len(items) == 2
        assert keys == {("t1", 0)}

    def test_sort_values_preserved(self):
        """Sort values correctly preserved from source objects."""
        overrides = [MockOverride("t1", 0, 42)]
        prefs = [MockPreference("t2", 0, 3.14159)]

        items, keys = merge_overrides_and_preferences(overrides, prefs)

        t1 = next(i for i in items if i["task_id"] == "t1")
        t2 = next(i for i in items if i["task_id"] == "t2")

        assert t1["sort_value"] == 42.0
        assert t2["sort_value"] == 3.14159


# ============================================================================
# Tests for build_task_ids_from_occurrences
# ============================================================================

class TestBuildTaskIdsFromOccurrences:
    """Tests for build_task_ids_from_occurrences function."""

    def test_empty_list_returns_empty(self):
        """Empty input produces empty output."""
        result = build_task_ids_from_occurrences([])
        assert result == []

    def test_extracts_task_ids(self):
        """Task IDs extracted in order."""
        occs = [
            MockOccurrence("t1", 0),
            MockOccurrence("t2", 0),
            MockOccurrence("t3", 1),
        ]
        result = build_task_ids_from_occurrences(occs)
        assert result == ["t1", "t2", "t3"]

    def test_preserves_duplicates(self):
        """Duplicate task IDs preserved (same task, different indices)."""
        occs = [
            MockOccurrence("t1", 0),
            MockOccurrence("t1", 1),
            MockOccurrence("t1", 2),
        ]
        result = build_task_ids_from_occurrences(occs)
        assert result == ["t1", "t1", "t1"]


# ============================================================================
# Tests for validate_all_tasks_exist
# ============================================================================

class TestValidateAllTasksExist:
    """Tests for validate_all_tasks_exist function."""

    def test_all_valid_returns_empty(self):
        """All tasks valid returns empty set."""
        task_ids = ["a", "b", "c"]
        valid = {"a", "b", "c", "d"}
        result = validate_all_tasks_exist(task_ids, valid)
        assert result == set()

    def test_some_invalid(self):
        """Some invalid returns invalid set."""
        task_ids = ["a", "b", "invalid"]
        valid = {"a", "b", "c"}
        result = validate_all_tasks_exist(task_ids, valid)
        assert result == {"invalid"}

    def test_all_invalid(self):
        """All invalid returns all."""
        task_ids = ["x", "y", "z"]
        valid = {"a", "b", "c"}
        result = validate_all_tasks_exist(task_ids, valid)
        assert result == {"x", "y", "z"}

    def test_empty_task_ids(self):
        """Empty task_ids returns empty."""
        result = validate_all_tasks_exist([], {"a", "b"})
        assert result == set()

    def test_empty_valid_set(self):
        """Empty valid set returns all as invalid."""
        task_ids = ["a", "b"]
        result = validate_all_tasks_exist(task_ids, set())
        assert result == {"a", "b"}
