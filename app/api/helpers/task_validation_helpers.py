"""Task validation helper functions - extracted for unit testing.

Each validation is a pure function returning (is_valid, error_message).
This allows focused unit testing of each branch.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass
class ValidationResult:
    """Result of a validation check."""
    is_valid: bool
    error_message: str | None = None


def validate_recurring_needs_scheduling_mode(
    is_recurring: bool,
    scheduled_at: bool,  # True if scheduled_at is set
    scheduling_mode: str | None,
) -> ValidationResult:
    """
    Validate: Recurring tasks with scheduled times need scheduling_mode.
    
    Branch: is_recurring AND scheduled_at AND NOT scheduling_mode
    """
    if is_recurring and scheduled_at and not scheduling_mode:
        return ValidationResult(
            is_valid=False,
            error_message="scheduling_mode is required for recurring tasks with scheduled times",
        )
    return ValidationResult(is_valid=True)


def validate_anytime_not_recurring(
    scheduling_mode: str | None,
    is_recurring: bool,
) -> ValidationResult:
    """
    Validate: Anytime tasks cannot be recurring.
    
    Branch: scheduling_mode == "anytime" AND is_recurring
    """
    if scheduling_mode == "anytime" and is_recurring:
        return ValidationResult(
            is_valid=False,
            error_message="Anytime tasks cannot be recurring",
        )
    return ValidationResult(is_valid=True)


def validate_recurring_needs_behavior(
    is_recurring: bool,
    recurrence_behavior: str | None,
) -> ValidationResult:
    """
    Validate: Recurring tasks must have recurrence_behavior set.
    
    Branch: is_recurring AND NOT recurrence_behavior
    """
    if is_recurring and not recurrence_behavior:
        return ValidationResult(
            is_valid=False,
            error_message="recurrence_behavior is required for recurring tasks",
        )
    return ValidationResult(is_valid=True)


def validate_non_recurring_no_behavior(
    is_recurring: bool,
    recurrence_behavior: str | None,
) -> ValidationResult:
    """
    Validate: Non-recurring tasks should not have recurrence_behavior.
    
    Branch: NOT is_recurring AND recurrence_behavior
    """
    if not is_recurring and recurrence_behavior:
        return ValidationResult(
            is_valid=False,
            error_message="recurrence_behavior should only be set for recurring tasks",
        )
    return ValidationResult(is_valid=True)


def determine_scheduling_mode(
    explicit_mode: str | None,
    scheduled_date: str | None,
    scheduled_at: bool,  # True if scheduled_at is set
) -> str | None:
    """
    Determine scheduling_mode if not explicitly provided.
    
    Branch: explicit_mode is None AND scheduled_date AND NOT scheduled_at
    """
    if explicit_mode is not None:
        return explicit_mode
    
    if scheduled_date and not scheduled_at:
        return "date_only"
    
    return None


def should_auto_set_date_only_mode(
    scheduled_date_changed: bool,
    scheduled_at_changed: bool,
    has_scheduled_date: bool,
    has_scheduled_at: bool,
) -> bool:
    """
    Determine if scheduling_mode should auto-set to date_only on update.
    
    Branch: (scheduled_date_changed OR scheduled_at_changed) AND has_scheduled_date AND NOT has_scheduled_at
    """
    if not (scheduled_date_changed or scheduled_at_changed):
        return False
    
    return has_scheduled_date and not has_scheduled_at


def validate_reopen_recurring_needs_scheduled_for(
    is_recurring: bool,
    scheduled_for_provided: bool,
) -> ValidationResult:
    """
    Validate: Reopening recurring task needs scheduled_for.
    
    Branch: is_recurring AND NOT scheduled_for_provided
    """
    if is_recurring and not scheduled_for_provided:
        return ValidationResult(
            is_valid=False,
            error_message="scheduled_for is required to reopen a recurring task occurrence",
        )
    return ValidationResult(is_valid=True)


def validate_task_not_already_pending(
    is_recurring: bool,
    current_status: str,
) -> ValidationResult:
    """
    Validate: One-time task not already pending for reopen.
    
    Branch: NOT is_recurring AND status == "pending"
    """
    if not is_recurring and current_status == "pending":
        return ValidationResult(
            is_valid=False,
            error_message="Task is already pending",
        )
    return ValidationResult(is_valid=True)


# ============================================================================
# Stats Calculation Helpers
# ============================================================================


def calculate_expected_occurrences(
    is_recurring: bool,
    has_recurrence_rule: bool,
    occurrences_count: int,
    has_scheduled_at: bool,
) -> int:
    """
    Calculate expected occurrences for stats.
    
    Branch 1: is_recurring AND has_recurrence_rule -> use occurrences_count
    Branch 2: NOT (is_recurring AND has_recurrence_rule) -> return 1
    """
    if is_recurring and has_recurrence_rule:
        return occurrences_count
    return 1


def determine_day_status(
    expected: int,
    completed: int,
    skipped: int,
) -> Literal["completed", "skipped", "missed", "partial"]:
    """
    Determine daily status for history.
    
    Branch 1: expected == 0 -> "completed" if completed > 0 else "skipped"
    Branch 2: completed >= expected -> "completed"
    Branch 3: completed > 0 OR skipped > 0 -> "partial"
    Branch 4: default -> "missed"
    """
    if expected == 0:
        # Extra completion on non-expected day
        return "completed" if completed > 0 else "skipped"
    
    if completed >= expected:
        return "completed"
    
    if completed > 0 or skipped > 0:
        return "partial"
    
    return "missed"


def calculate_completion_rate(
    total_completed: int,
    total_expected: int,
) -> float:
    """
    Calculate completion rate.
    
    Branch: total_expected > 0 -> rate else 0.0
    """
    if total_expected > 0:
        return total_completed / total_expected
    return 0.0
