"""
Pure helper functions for occurrence ordering.

These functions extract complex logic from occurrence_ordering.py for easier unit testing.
All functions are pure - no async, no DB access.
"""
from dataclasses import dataclass
from typing import Any


def classify_tasks_by_recurrence(
    task_ids: list[str],
    task_recurring_map: dict[str, bool],
) -> tuple[list[str], list[str]]:
    """
    Separate task IDs into recurring and single (non-recurring) lists.
    
    Args:
        task_ids: List of task IDs to classify
        task_recurring_map: Dict mapping task_id -> is_recurring bool
    
    Returns:
        (recurring_task_ids, single_task_ids)
    """
    recurring = []
    single = []
    for tid in task_ids:
        if task_recurring_map.get(tid, False):
            recurring.append(tid)
        else:
            single.append(tid)
    return recurring, single


def find_position_in_occurrences(
    occurrences: list[Any],
    task_id: str,
    occurrence_index: int,
) -> int:
    """
    Find 1-based position of a task/occurrence in the list.
    
    Args:
        occurrences: List of occurrence objects with task_id and occurrence_index
        task_id: Task ID to find
        occurrence_index: Occurrence index to find
    
    Returns:
        1-based position in list
    
    Raises:
        ValueError: If occurrence not found
    """
    for i, occ in enumerate(occurrences, start=1):
        if occ.task_id == task_id and occ.occurrence_index == occurrence_index:
            return i
    raise ValueError(f"Occurrence not found: {task_id}/{occurrence_index}")


@dataclass
class MergedOrderItem:
    """Represents a merged order item from overrides and preferences."""
    task_id: str
    occurrence_index: int
    sort_value: float
    is_override: bool


def merge_overrides_and_preferences(
    overrides: list[Any],
    prefs: list[Any],
) -> tuple[list[dict[str, Any]], set[tuple[str, int]]]:
    """
    Merge daily overrides with permanent preferences.
    
    Overrides take precedence - preferences with matching task/occurrence
    are excluded.
    
    Args:
        overrides: List of DailySortOverride-like objects
        prefs: List of OccurrencePreference-like objects
    
    Returns:
        (merged_items_as_dicts, override_keys_set)
    """
    override_keys: set[tuple[str, int]] = set()
    items: list[dict[str, Any]] = []
    
    # Add all overrides
    for override in overrides:
        key = (override.task_id, override.occurrence_index)
        override_keys.add(key)
        items.append({
            "task_id": override.task_id,
            "occurrence_index": override.occurrence_index,
            "sort_value": float(override.sort_position),
            "is_override": True,
        })
    
    # Add preferences that don't have overrides
    for pref in prefs:
        key = (pref.task_id, pref.occurrence_index)
        if key not in override_keys:
            items.append({
                "task_id": pref.task_id,
                "occurrence_index": pref.occurrence_index,
                "sort_value": pref.sequence_number,
                "is_override": False,
            })
    
    return items, override_keys


def build_task_ids_from_occurrences(occurrences: list[Any]) -> list[str]:
    """Extract task IDs from occurrence objects."""
    return [occ.task_id for occ in occurrences]


def validate_all_tasks_exist(
    task_ids: list[str],
    valid_task_ids: set[str],
) -> set[str]:
    """
    Find task IDs that are not in the valid set.
    
    Returns:
        Set of invalid task IDs
    """
    return set(task_ids) - valid_task_ids
