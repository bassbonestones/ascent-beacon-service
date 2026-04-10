"""Unit tests for completion_helpers - pure functions with no DB access."""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock

from app.api.helpers.completion_helpers import (
    CompletionDataMaps,
    ensure_timezone_aware,
    determine_date_key,
    process_completion_row,
    process_all_completion_rows,
    count_task_statuses,
)


# ============================================================================
# ensure_timezone_aware
# ============================================================================

class TestEnsureTimezoneAware:
    """Tests for ensure_timezone_aware function."""

    def test_none_returns_none(self):
        """Branch: dt is None -> return None"""
        result = ensure_timezone_aware(None)
        assert result is None

    def test_naive_datetime_gets_utc(self):
        """Branch: dt.tzinfo is None -> add UTC"""
        naive = datetime(2026, 4, 9, 10, 30, 0)
        result = ensure_timezone_aware(naive)
        assert result.tzinfo == timezone.utc
        assert result.hour == 10

    def test_aware_datetime_unchanged(self):
        """Branch: dt already has tzinfo -> return unchanged"""
        aware = datetime(2026, 4, 9, 10, 30, 0, tzinfo=timezone.utc)
        result = ensure_timezone_aware(aware)
        assert result is aware


# ============================================================================
# determine_date_key
# ============================================================================

class TestDetermineDateKey:
    """Tests for determine_date_key function."""

    def test_uses_local_date_when_provided(self):
        """Branch: local_date is not None -> use it"""
        scheduled = datetime(2026, 4, 9, 23, 59, 0, tzinfo=timezone.utc)
        result = determine_date_key(scheduled, "2026-04-10")  # Different from UTC date
        assert result == "2026-04-10"

    def test_uses_utc_date_when_local_date_none(self):
        """Branch: local_date is None -> use scheduled_for date"""
        scheduled = datetime(2026, 4, 9, 10, 30, 0, tzinfo=timezone.utc)
        result = determine_date_key(scheduled, None)
        assert result == "2026-04-09"

    def test_empty_string_local_date_uses_utc(self):
        """Branch: local_date is empty string (falsy) -> use UTC"""
        scheduled = datetime(2026, 4, 9, 10, 30, 0, tzinfo=timezone.utc)
        result = determine_date_key(scheduled, "")
        assert result == "2026-04-09"


# ============================================================================
# process_completion_row - Completions
# ============================================================================

class TestProcessCompletionRowCompleted:
    """Tests for process_completion_row with status='completed'."""

    def test_completion_adds_to_by_date_map(self):
        """Completion should add to completions_by_date_map."""
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 9, 10, 0, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="completed",
            skip_reason=None,
            local_date="2026-04-09",
            today_str="2026-04-09",
            data=data,
        )
        
        assert "task-1" in data.completions_by_date_map
        assert "2026-04-09" in data.completions_by_date_map["task-1"]
        assert len(data.completions_by_date_map["task-1"]["2026-04-09"]) == 1

    def test_completion_today_increments_count(self):
        """Completion on today_str should increment completions_today_count."""
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 9, 10, 0, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="completed",
            skip_reason=None,
            local_date="2026-04-09",
            today_str="2026-04-09",
            data=data,
        )
        
        assert data.completions_today_count["task-1"] == 1

    def test_completion_not_today_no_today_count(self):
        """Completion NOT on today_str should not touch completions_today_count."""
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 8, 10, 0, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="completed",
            skip_reason=None,
            local_date="2026-04-08",
            today_str="2026-04-09",
            data=data,
        )
        
        assert "task-1" not in data.completions_today_count

    def test_multiple_completions_same_day(self):
        """Multiple completions on same day should stack."""
        data = CompletionDataMaps()
        
        for hour in [9, 12, 18]:
            scheduled = datetime(2026, 4, 9, hour, 0, 0, tzinfo=timezone.utc)
            process_completion_row(
                task_id="task-1",
                scheduled_for=scheduled,
                record_status="completed",
                skip_reason=None,
                local_date="2026-04-09",
                today_str="2026-04-09",
                data=data,
            )
        
        assert data.completions_today_count["task-1"] == 3
        assert len(data.completions_today_times["task-1"]) == 3

    def test_completion_records_time(self):
        """Completion should record ISO timestamp."""
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 9, 14, 30, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="completed",
            skip_reason=None,
            local_date="2026-04-09",
            today_str="2026-04-09",
            data=data,
        )
        
        assert data.completions_today_times["task-1"][0] == "2026-04-09T14:30:00+00:00"


# ============================================================================
# process_completion_row - Skips
# ============================================================================

class TestProcessCompletionRowSkipped:
    """Tests for process_completion_row with status='skipped'."""

    def test_skip_adds_to_by_date_map(self):
        """Skip should add to skips_by_date_map."""
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 9, 10, 0, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="skipped",
            skip_reason="Too busy",
            local_date="2026-04-09",
            today_str="2026-04-09",
            data=data,
        )
        
        assert "task-1" in data.skips_by_date_map
        assert "2026-04-09" in data.skips_by_date_map["task-1"]

    def test_skip_records_reason(self):
        """Skip should record skip reason in skip_reasons_by_date_map."""
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 9, 10, 0, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="skipped",
            skip_reason="Feeling sick",
            local_date="2026-04-09",
            today_str="2026-04-09",
            data=data,
        )
        
        assert data.skip_reasons_by_date_map["task-1"]["2026-04-09"] == "Feeling sick"

    def test_skip_today_increments_count(self):
        """Skip on today_str increments skips_today_count."""
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 9, 10, 0, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="skipped",
            skip_reason=None,
            local_date="2026-04-09",
            today_str="2026-04-09",
            data=data,
        )
        
        assert data.skips_today_count["task-1"] == 1

    def test_skip_today_records_reason(self):
        """Skip on today records reason in skip_reason_today_map."""
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 9, 10, 0, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="skipped",
            skip_reason="Vacation",
            local_date="2026-04-09",
            today_str="2026-04-09",
            data=data,
        )
        
        assert data.skip_reason_today_map["task-1"] == "Vacation"

    def test_skip_null_reason_records_none(self):
        """Skip with no reason records None."""
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 9, 10, 0, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="skipped",
            skip_reason=None,
            local_date="2026-04-09",
            today_str="2026-04-09",
            data=data,
        )
        
        assert data.skip_reason_today_map["task-1"] is None

    def test_skip_not_today_no_today_map(self):
        """Skip NOT on today_str should not touch skip_reason_today_map."""
        data = CompletionDataMaps()
        scheduled = datetime(2026, 4, 8, 10, 0, 0, tzinfo=timezone.utc)
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=scheduled,
            record_status="skipped",
            skip_reason="Yesterday skip",
            local_date="2026-04-08",
            today_str="2026-04-09",
            data=data,
        )
        
        assert "task-1" not in data.skip_reason_today_map


# ============================================================================
# process_completion_row - Edge cases
# ============================================================================

class TestProcessCompletionRowEdgeCases:
    """Edge case tests for process_completion_row."""

    def test_none_scheduled_for_does_nothing(self):
        """If scheduled_for is None, function returns early."""
        data = CompletionDataMaps()
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=None,
            record_status="completed",
            skip_reason=None,
            local_date="2026-04-09",
            today_str="2026-04-09",
            data=data,
        )
        
        assert len(data.completions_by_date_map) == 0

    def test_naive_datetime_gets_utc_before_processing(self):
        """Naive datetime should get UTC added."""
        data = CompletionDataMaps()
        naive = datetime(2026, 4, 9, 10, 0, 0)  # No tzinfo
        
        process_completion_row(
            task_id="task-1",
            scheduled_for=naive,
            record_status="completed",
            skip_reason=None,
            local_date="2026-04-09",
            today_str="2026-04-09",
            data=data,
        )
        
        # Should have processed successfully
        assert data.completions_today_count["task-1"] == 1


# ============================================================================
# process_all_completion_rows
# ============================================================================

class TestProcessAllCompletionRows:
    """Tests for process_all_completion_rows batch processing."""

    def test_empty_rows_returns_empty_maps(self):
        """Empty input returns empty data maps."""
        result = process_all_completion_rows([], "2026-04-09")
        
        assert len(result.completions_by_date_map) == 0
        assert len(result.skips_by_date_map) == 0

    def test_multiple_tasks_tracked_separately(self):
        """Different task_ids tracked in separate map entries."""
        rows = [
            ("task-1", datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc), "completed", None, "2026-04-09"),
            ("task-2", datetime(2026, 4, 9, 11, 0, tzinfo=timezone.utc), "completed", None, "2026-04-09"),
        ]
        
        result = process_all_completion_rows(rows, "2026-04-09")
        
        assert "task-1" in result.completions_today_count
        assert "task-2" in result.completions_today_count

    def test_mixed_completions_and_skips(self):
        """Both completions and skips tracked correctly."""
        rows = [
            ("task-1", datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc), "completed", None, "2026-04-09"),
            ("task-1", datetime(2026, 4, 9, 14, 0, tzinfo=timezone.utc), "skipped", "Busy", "2026-04-09"),
        ]
        
        result = process_all_completion_rows(rows, "2026-04-09")
        
        assert result.completions_today_count["task-1"] == 1
        assert result.skips_today_count["task-1"] == 1

    def test_handles_rows_without_local_date(self):
        """Handle rows with only 4 elements (no local_date)."""
        rows = [
            ("task-1", datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc), "completed", None),
        ]
        
        result = process_all_completion_rows(rows, "2026-04-09")
        
        assert result.completions_today_count["task-1"] == 1

    def test_multiple_dates(self):
        """Track completions across multiple dates."""
        rows = [
            ("task-1", datetime(2026, 4, 8, 10, 0, tzinfo=timezone.utc), "completed", None, "2026-04-08"),
            ("task-1", datetime(2026, 4, 9, 10, 0, tzinfo=timezone.utc), "completed", None, "2026-04-09"),
            ("task-1", datetime(2026, 4, 10, 10, 0, tzinfo=timezone.utc), "completed", None, "2026-04-10"),
        ]
        
        result = process_all_completion_rows(rows, "2026-04-09")
        
        assert len(result.completions_by_date_map["task-1"]) == 3
        assert result.completions_today_count["task-1"] == 1  # Only today


# ============================================================================
# count_task_statuses
# ============================================================================

class TestCountTaskStatuses:
    """Tests for count_task_statuses function."""

    def test_empty_list_returns_zeros(self):
        """Empty list returns (0, 0)."""
        pending, completed = count_task_statuses([])
        assert pending == 0
        assert completed == 0

    def test_counts_pending_correctly(self):
        """Counts pending tasks."""
        tasks = [Mock(status="pending"), Mock(status="pending"), Mock(status="completed")]
        pending, completed = count_task_statuses(tasks)
        assert pending == 2

    def test_counts_completed_correctly(self):
        """Counts completed tasks."""
        tasks = [Mock(status="completed"), Mock(status="completed"), Mock(status="pending")]
        pending, completed = count_task_statuses(tasks)
        assert completed == 2

    def test_ignores_other_statuses(self):
        """Other statuses like 'skipped' are not counted."""
        tasks = [Mock(status="pending"), Mock(status="skipped"), Mock(status="completed")]
        pending, completed = count_task_statuses(tasks)
        assert pending == 1
        assert completed == 1

    def test_all_pending(self):
        """All pending tasks."""
        tasks = [Mock(status="pending") for _ in range(5)]
        pending, completed = count_task_statuses(tasks)
        assert pending == 5
        assert completed == 0

    def test_all_completed(self):
        """All completed tasks."""
        tasks = [Mock(status="completed") for _ in range(3)]
        pending, completed = count_task_statuses(tasks)
        assert pending == 0
        assert completed == 3
