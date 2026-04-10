"""Unit tests for task_stats pure functions.

Tests the calculate_streak function with various branch scenarios.
"""

import pytest
from datetime import date, datetime
from unittest.mock import Mock

from app.api.task_stats import calculate_streak


def mock_completion(completed_at: datetime, status: str = "completed") -> Mock:
    """Create a mock TaskCompletion for testing."""
    c = Mock()
    c.completed_at = completed_at
    c.status = status
    return c


# ============================================================================
# calculate_streak - Main branches
# ============================================================================


class TestCalculateStreakEmpty:
    """Empty/edge case tests for calculate_streak"""

    def test_branch_no_completions_returns_zeros(self):
        """Branch: completions is empty -> (0, 0)"""
        result = calculate_streak(
            completions=[],
            end_date=date(2026, 4, 9),
            expected_dates={date(2026, 4, 8), date(2026, 4, 9)},
        )
        assert result == (0, 0)

    def test_branch_no_expected_dates_returns_zeros(self):
        """Branch: expected_dates is empty -> (0, 0)"""
        completion = mock_completion(datetime(2026, 4, 9))
        result = calculate_streak(
            completions=[completion],
            end_date=date(2026, 4, 9),
            expected_dates=set(),
        )
        assert result == (0, 0)

    def test_branch_both_empty_returns_zeros(self):
        """Branch: both empty -> (0, 0)"""
        result = calculate_streak(
            completions=[],
            end_date=date(2026, 4, 9),
            expected_dates=set(),
        )
        assert result == (0, 0)


class TestCalculateStreakLongest:
    """Tests for longest streak calculation"""

    def test_branch_single_completion_streak_of_one(self):
        """Branch: single expected and completed -> longest = 1"""
        completion = mock_completion(datetime(2026, 4, 9))
        result = calculate_streak(
            completions=[completion],
            end_date=date(2026, 4, 9),
            expected_dates={date(2026, 4, 9)},
        )
        current, longest = result
        assert longest == 1

    def test_branch_consecutive_completions_streak_increases(self):
        """Branch: consecutive completions -> longest increases each day"""
        completions = [
            mock_completion(datetime(2026, 4, 7)),
            mock_completion(datetime(2026, 4, 8)),
            mock_completion(datetime(2026, 4, 9)),
        ]
        expected = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert longest == 3

    def test_branch_broken_streak_resets_current(self):
        """Branch: missing day resets current streak counter"""
        # Complete day 7, skip day 8, complete day 9
        completions = [
            mock_completion(datetime(2026, 4, 7)),
            mock_completion(datetime(2026, 4, 9)),
        ]
        expected = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert longest == 1  # Only day 7 streak, then reset

    def test_branch_multiple_streaks_keeps_longest(self):
        """Branch: longest is kept even when current streak resets"""
        # Streak of 3, then gap, then streak of 2
        completions = [
            mock_completion(datetime(2026, 4, 1)),
            mock_completion(datetime(2026, 4, 2)),
            mock_completion(datetime(2026, 4, 3)),
            # Gap on day 4
            mock_completion(datetime(2026, 4, 5)),
            mock_completion(datetime(2026, 4, 6)),
        ]
        expected = {
            date(2026, 4, 1),
            date(2026, 4, 2),
            date(2026, 4, 3),
            date(2026, 4, 4),
            date(2026, 4, 5),
            date(2026, 4, 6),
        }
        current, longest = calculate_streak(completions, date(2026, 4, 6), expected)
        assert longest == 3  # First streak was longer


class TestCalculateStreakCurrent:
    """Tests for current streak calculation (from end_date backwards)"""

    def test_branch_current_streak_from_end(self):
        """Branch: current streak counts backwards from end_date"""
        completions = [
            mock_completion(datetime(2026, 4, 7)),
            mock_completion(datetime(2026, 4, 8)),
            mock_completion(datetime(2026, 4, 9)),
        ]
        expected = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert current == 3

    def test_branch_current_streak_breaks_on_miss(self):
        """Branch: current streak stops at first missed day going backwards"""
        completions = [
            mock_completion(datetime(2026, 4, 7)),
            # Skip day 8
            mock_completion(datetime(2026, 4, 9)),
        ]
        expected = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert current == 1  # Only day 9

    def test_branch_no_recent_completions_zero_current(self):
        """Branch: most recent expected dates not completed -> current = 0"""
        completions = [
            mock_completion(datetime(2026, 4, 7)),
        ]
        expected = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert current == 0  # Days 8 and 9 not completed

    def test_branch_expected_dates_after_end_date_skipped(self):
        """Branch: expected dates > end_date are skipped"""
        completions = [
            mock_completion(datetime(2026, 4, 8)),
            mock_completion(datetime(2026, 4, 9)),
        ]
        expected = {date(2026, 4, 8), date(2026, 4, 9), date(2026, 4, 10)}
        # end_date is day 9, so day 10 should be skipped
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert current == 2  # Days 8 and 9


class TestCalculateStreakSkippedStatus:
    """Tests for handling skipped (not completed) status"""

    def test_branch_skipped_status_not_counted(self):
        """Branch: completions with status='skipped' don't count"""
        completions = [
            mock_completion(datetime(2026, 4, 7), status="completed"),
            mock_completion(datetime(2026, 4, 8), status="skipped"),  # Not counted
            mock_completion(datetime(2026, 4, 9), status="completed"),
        ]
        expected = {date(2026, 4, 7), date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        # Since day 8 is skipped (not completed), streaks break
        assert longest == 1  # Day 7 alone, then day 9 alone
        assert current == 1  # Only day 9

    def test_branch_all_skipped_returns_zeros(self):
        """Branch: all completions are skipped -> no streaks"""
        completions = [
            mock_completion(datetime(2026, 4, 8), status="skipped"),
            mock_completion(datetime(2026, 4, 9), status="skipped"),
        ]
        expected = {date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert current == 0
        assert longest == 0


class TestCalculateStreakEdgeCases:
    """Edge case tests for calculate_streak"""

    def test_branch_completion_not_on_expected_date_ignored(self):
        """Branch: completions on non-expected dates affect nothing"""
        completions = [
            mock_completion(datetime(2026, 4, 5)),  # Not an expected date
            mock_completion(datetime(2026, 4, 9)),
        ]
        expected = {date(2026, 4, 8), date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        # Day 8 not completed, so current streak = 1 (only day 9)
        assert current == 1
        assert longest == 1

    def test_branch_single_expected_single_completed(self):
        """Branch: single expected, completed -> streaks = 1"""
        completions = [mock_completion(datetime(2026, 4, 9))]
        expected = {date(2026, 4, 9)}
        current, longest = calculate_streak(completions, date(2026, 4, 9), expected)
        assert current == 1
        assert longest == 1

    def test_branch_end_date_before_all_expected(self):
        """Branch: end_date before all expected dates -> current = 0"""
        completions = [
            mock_completion(datetime(2026, 4, 10)),
            mock_completion(datetime(2026, 4, 11)),
        ]
        expected = {date(2026, 4, 10), date(2026, 4, 11)}
        # end_date is before expected dates
        current, longest = calculate_streak(completions, date(2026, 4, 5), expected)
        assert current == 0  # No dates <= end_date
        assert longest == 2  # Still calculates longest from all dates
