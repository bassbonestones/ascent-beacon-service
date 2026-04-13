"""Unit tests for task validation helpers - one branch per test.

Tests are structured to verify each specific branch is entered.
Each test name explicitly states which branch condition is being tested.
"""

import pytest
from app.api.helpers.task_validation_helpers import (
    validate_recurring_needs_scheduling_mode,
    validate_anytime_not_recurring,
    validate_recurring_needs_behavior,
    validate_non_recurring_no_behavior,
    determine_scheduling_mode,
    should_auto_set_date_only_mode,
    validate_reopen_recurring_needs_scheduled_for,
    validate_task_not_already_pending,
    calculate_expected_occurrences,
    determine_day_status,
    calculate_completion_rate,
)


class TestValidateRecurringNeedsSchedulingMode:
    def test_branch_all_true_fails(self):
        result = validate_recurring_needs_scheduling_mode(
            is_recurring=True,
            scheduled_at=True,
            scheduling_mode=None,
        )
        assert result.is_valid is False
        assert "scheduling_mode is required" in result.error_message

    def test_branch_not_recurring_passes(self):
        result = validate_recurring_needs_scheduling_mode(
            is_recurring=False,
            scheduled_at=True,
            scheduling_mode=None,
        )
        assert result.is_valid is True

    def test_branch_no_scheduled_at_passes(self):
        result = validate_recurring_needs_scheduling_mode(
            is_recurring=True,
            scheduled_at=False,
            scheduling_mode=None,
        )
        assert result.is_valid is True

    def test_branch_has_scheduling_mode_passes(self):
        result = validate_recurring_needs_scheduling_mode(
            is_recurring=True,
            scheduled_at=True,
            scheduling_mode="floating",
        )
        assert result.is_valid is True


class TestValidateAnytimeNotRecurring:
    def test_branch_anytime_and_recurring_fails(self):
        result = validate_anytime_not_recurring(
            scheduling_mode="anytime",
            is_recurring=True,
        )
        assert result.is_valid is False
        assert "Anytime tasks cannot be recurring" in result.error_message

    def test_branch_not_anytime_passes(self):
        result = validate_anytime_not_recurring(
            scheduling_mode="floating",
            is_recurring=True,
        )
        assert result.is_valid is True

    def test_branch_not_recurring_passes(self):
        result = validate_anytime_not_recurring(
            scheduling_mode="anytime",
            is_recurring=False,
        )
        assert result.is_valid is True

    def test_branch_scheduling_mode_none_passes(self):
        result = validate_anytime_not_recurring(
            scheduling_mode=None,
            is_recurring=True,
        )
        assert result.is_valid is True


class TestValidateRecurringNeedsBehavior:
    def test_branch_recurring_no_behavior_fails(self):
        result = validate_recurring_needs_behavior(
            is_recurring=True,
            recurrence_behavior=None,
        )
        assert result.is_valid is False
        assert "recurrence_behavior is required" in result.error_message

    def test_branch_not_recurring_passes(self):
        result = validate_recurring_needs_behavior(
            is_recurring=False,
            recurrence_behavior=None,
        )
        assert result.is_valid is True

    def test_branch_has_behavior_passes(self):
        result = validate_recurring_needs_behavior(
            is_recurring=True,
            recurrence_behavior="habitual",
        )
        assert result.is_valid is True


class TestValidateNonRecurringNoBehavior:
    def test_branch_non_recurring_with_behavior_fails(self):
        result = validate_non_recurring_no_behavior(
            is_recurring=False,
            recurrence_behavior="habitual",
        )
        assert result.is_valid is False
        assert "should only be set for recurring" in result.error_message

    def test_branch_recurring_with_behavior_passes(self):
        result = validate_non_recurring_no_behavior(
            is_recurring=True,
            recurrence_behavior="habitual",
        )
        assert result.is_valid is True

    def test_branch_non_recurring_no_behavior_passes(self):
        result = validate_non_recurring_no_behavior(
            is_recurring=False,
            recurrence_behavior=None,
        )
        assert result.is_valid is True


class TestDetermineSchedulingMode:
    def test_branch_explicit_mode_returns_explicit(self):
        result = determine_scheduling_mode(
            explicit_mode="floating",
            scheduled_date="2026-04-09",
            scheduled_at=False,
        )
        assert result == "floating"

    def test_branch_date_only_condition_met(self):
        result = determine_scheduling_mode(
            explicit_mode=None,
            scheduled_date="2026-04-09",
            scheduled_at=False,
        )
        assert result == "date_only"

    def test_branch_no_scheduled_date_returns_none(self):
        result = determine_scheduling_mode(
            explicit_mode=None,
            scheduled_date=None,
            scheduled_at=False,
        )
        assert result is None

    def test_branch_has_scheduled_at_returns_none(self):
        result = determine_scheduling_mode(
            explicit_mode=None,
            scheduled_date="2026-04-09",
            scheduled_at=True,
        )
        assert result is None


class TestShouldAutoSetDateOnlyMode:
    def test_branch_no_changes_returns_false(self):
        result = should_auto_set_date_only_mode(
            scheduled_date_changed=False,
            scheduled_at_changed=False,
            has_scheduled_date=True,
            has_scheduled_at=False,
        )
        assert result is False

    def test_branch_date_changed_and_conditions_met(self):
        result = should_auto_set_date_only_mode(
            scheduled_date_changed=True,
            scheduled_at_changed=False,
            has_scheduled_date=True,
            has_scheduled_at=False,
        )
        assert result is True

    def test_branch_at_changed_and_conditions_met(self):
        result = should_auto_set_date_only_mode(
            scheduled_date_changed=False,
            scheduled_at_changed=True,
            has_scheduled_date=True,
            has_scheduled_at=False,
        )
        assert result is True

    def test_branch_has_scheduled_at_returns_false(self):
        result = should_auto_set_date_only_mode(
            scheduled_date_changed=True,
            scheduled_at_changed=False,
            has_scheduled_date=True,
            has_scheduled_at=True,
        )
        assert result is False

    def test_branch_no_scheduled_date_returns_false(self):
        result = should_auto_set_date_only_mode(
            scheduled_date_changed=True,
            scheduled_at_changed=False,
            has_scheduled_date=False,
            has_scheduled_at=False,
        )
        assert result is False


class TestValidateReopenRecurringNeedsScheduledFor:
    def test_branch_recurring_no_scheduled_for_fails(self):
        result = validate_reopen_recurring_needs_scheduled_for(
            is_recurring=True,
            scheduled_for_provided=False,
        )
        assert result.is_valid is False
        assert "scheduled_for is required" in result.error_message

    def test_branch_not_recurring_passes(self):
        result = validate_reopen_recurring_needs_scheduled_for(
            is_recurring=False,
            scheduled_for_provided=False,
        )
        assert result.is_valid is True

    def test_branch_has_scheduled_for_passes(self):
        result = validate_reopen_recurring_needs_scheduled_for(
            is_recurring=True,
            scheduled_for_provided=True,
        )
        assert result.is_valid is True


class TestValidateTaskNotAlreadyPending:
    def test_branch_non_recurring_pending_fails(self):
        result = validate_task_not_already_pending(
            is_recurring=False,
            current_status="pending",
        )
        assert result.is_valid is False
        assert "already pending" in result.error_message

    def test_branch_recurring_passes(self):
        result = validate_task_not_already_pending(
            is_recurring=True,
            current_status="pending",
        )
        assert result.is_valid is True

    def test_branch_not_pending_passes(self):
        result = validate_task_not_already_pending(
            is_recurring=False,
            current_status="completed",
        )
        assert result.is_valid is True


class TestCalculateExpectedOccurrences:
    def test_branch_recurring_with_rule_uses_count(self):
        result = calculate_expected_occurrences(
            is_recurring=True,
            has_recurrence_rule=True,
            occurrences_count=7,
            has_scheduled_at=True,
        )
        assert result == 7

    def test_branch_not_recurring_returns_one(self):
        result = calculate_expected_occurrences(
            is_recurring=False,
            has_recurrence_rule=False,
            occurrences_count=0,
            has_scheduled_at=True,
        )
        assert result == 1

    def test_branch_no_rule_returns_one(self):
        result = calculate_expected_occurrences(
            is_recurring=True,
            has_recurrence_rule=False,
            occurrences_count=0,
            has_scheduled_at=True,
        )
        assert result == 1


class TestDetermineDayStatus:
    def test_branch_expected_zero_completed(self):
        result = determine_day_status(expected=0, completed=1, skipped=0)
        assert result == "completed"

    def test_branch_expected_zero_skipped(self):
        result = determine_day_status(expected=0, completed=0, skipped=0)
        assert result == "skipped"

    def test_branch_completed_meets_expected(self):
        result = determine_day_status(expected=1, completed=1, skipped=0)
        assert result == "completed"

    def test_branch_completed_exceeds_expected(self):
        result = determine_day_status(expected=1, completed=2, skipped=0)
        assert result == "completed"

    def test_branch_partial_some_completed(self):
        result = determine_day_status(expected=2, completed=1, skipped=0)
        assert result == "partial"

    def test_branch_partial_some_skipped(self):
        result = determine_day_status(expected=2, completed=0, skipped=1)
        assert result == "partial"

    def test_branch_missed(self):
        result = determine_day_status(expected=1, completed=0, skipped=0)
        assert result == "missed"


class TestCalculateCompletionRate:
    def test_branch_expected_positive(self):
        result = calculate_completion_rate(total_completed=5, total_expected=10)
        assert result == 0.5

    def test_branch_expected_zero(self):
        result = calculate_completion_rate(total_completed=0, total_expected=0)
        assert result == 0.0

    def test_branch_all_completed(self):
        result = calculate_completion_rate(total_completed=5, total_expected=5)
        assert result == 1.0

    def test_branch_none_completed(self):
        result = calculate_completion_rate(total_completed=0, total_expected=5)
        assert result == 0.0
