"""Tests for prerequisite recurrence period keys (next_occurrence Rule B)."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.services.dependency_recurrence_period import (
    completion_matches_next_occurrence_period,
    filter_completions_next_occurrence_period,
    prerequisite_recurrence_period_key,
)


def _task(
    *,
    is_recurring: bool,
    recurrence_rule: str | None,
) -> MagicMock:
    t = MagicMock(spec=["is_recurring", "recurrence_rule"])
    t.is_recurring = is_recurring
    t.recurrence_rule = recurrence_rule
    return t


def _completion(
    *,
    scheduled_for: datetime | None,
    completed_at: datetime,
    local_date: str | None = None,
) -> MagicMock:
    c = MagicMock(spec=["scheduled_for", "completed_at", "local_date"])
    c.scheduled_for = scheduled_for
    c.completed_at = completed_at
    c.local_date = local_date
    return c


class TestPrerequisiteRecurrencePeriodKey:
    def test_daily_same_utc_day_matches(self) -> None:
        t = _task(is_recurring=True, recurrence_rule="FREQ=DAILY")
        d = datetime(2026, 4, 7, 8, 0, 0, tzinfo=timezone.utc)
        assert prerequisite_recurrence_period_key(t, d) == prerequisite_recurrence_period_key(
            t, datetime(2026, 4, 7, 22, 0, 0, tzinfo=timezone.utc)
        )

    def test_daily_different_utc_days_differ(self) -> None:
        t = _task(is_recurring=True, recurrence_rule="FREQ=DAILY")
        a = datetime(2026, 4, 7, 23, 0, 0, tzinfo=timezone.utc)
        b = datetime(2026, 4, 8, 1, 0, 0, tzinfo=timezone.utc)
        assert prerequisite_recurrence_period_key(t, a) != prerequisite_recurrence_period_key(t, b)

    def test_daily_uses_local_date_when_provided(self) -> None:
        t = _task(is_recurring=True, recurrence_rule="FREQ=DAILY")
        instant = datetime(2026, 4, 7, 23, 30, 0, tzinfo=timezone.utc)
        with_local = prerequisite_recurrence_period_key(t, instant, local_date="2026-04-08")
        without = prerequisite_recurrence_period_key(t, instant, local_date=None)
        assert with_local == "DAILY:2026-04-08"
        assert without.startswith("DAILY:2026-04-07")

    def test_weekly_iso_week(self) -> None:
        t = _task(is_recurring=True, recurrence_rule="FREQ=WEEKLY;BYDAY=MO")
        w1 = datetime(2026, 4, 6, 12, 0, 0, tzinfo=timezone.utc)  # Monday ISO W15
        w2 = datetime(2026, 4, 13, 12, 0, 0, tzinfo=timezone.utc)  # next Monday W16
        y1, wn1, _ = w1.isocalendar()
        assert prerequisite_recurrence_period_key(t, w1) == f"WEEKLY:{y1}-W{wn1:02d}"
        assert prerequisite_recurrence_period_key(t, w1) != prerequisite_recurrence_period_key(t, w2)

    def test_non_recurring_uses_nday_bucket(self) -> None:
        t = _task(is_recurring=False, recurrence_rule=None)
        d = datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc)
        assert prerequisite_recurrence_period_key(t, d) == "NDAY:2026-05-01"

    def test_non_recurring_prefers_local_date(self) -> None:
        t = _task(is_recurring=False, recurrence_rule=None)
        d = datetime(2026, 5, 1, 23, 0, 0, tzinfo=timezone.utc)
        assert prerequisite_recurrence_period_key(t, d, local_date="2026-05-02") == "NDAY:2026-05-02"

    def test_naive_instant_normalized_to_utc(self) -> None:
        t = _task(is_recurring=True, recurrence_rule="FREQ=DAILY")
        naive = datetime(2026, 6, 1, 15, 0, 0)
        assert prerequisite_recurrence_period_key(t, naive) == "DAILY:2026-06-01"

    def test_monthly_key(self) -> None:
        t = _task(is_recurring=True, recurrence_rule="FREQ=MONTHLY;BYMONTHDAY=1")
        d = datetime(2026, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
        assert prerequisite_recurrence_period_key(t, d) == "MONTHLY:2026-07"

    def test_yearly_key(self) -> None:
        t = _task(is_recurring=True, recurrence_rule="FREQ=YEARLY")
        d = datetime(2026, 12, 31, 23, 0, 0, tzinfo=timezone.utc)
        assert prerequisite_recurrence_period_key(t, d) == "YEARLY:2026"

    def test_hourly_key(self) -> None:
        t = _task(is_recurring=True, recurrence_rule="FREQ=HOURLY")
        d = datetime(2026, 8, 1, 14, 30, 0, tzinfo=timezone.utc)
        assert prerequisite_recurrence_period_key(t, d) == "HOURLY:2026-08-01T14"

    def test_default_bucket_for_unrecognized_freq(self) -> None:
        t = _task(is_recurring=True, recurrence_rule="FREQ=MINUTELY")
        d = datetime(2026, 9, 9, 9, 0, 0, tzinfo=timezone.utc)
        assert prerequisite_recurrence_period_key(t, d) == "DEFAULT:2026-09-09"

    def test_recurring_but_missing_rule_uses_nday(self) -> None:
        t = _task(is_recurring=True, recurrence_rule=None)
        d = datetime(2026, 3, 3, 10, 0, 0, tzinfo=timezone.utc)
        assert prerequisite_recurrence_period_key(t, d) == "NDAY:2026-03-03"


class TestCompletionMatchesNextOccurrencePeriod:
    def test_downstream_local_date_defines_anchor_bucket_for_daily(self) -> None:
        """Anchor must use the same calendar semantics as upstream (client local_date)."""
        t = _task(is_recurring=True, recurrence_rule="FREQ=DAILY")
        gym = _completion(
            scheduled_for=datetime(2026, 4, 11, 6, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 4, 11, 6, 0, 0, tzinfo=timezone.utc),
            local_date="2026-04-10",
        )
        anchor = datetime(2026, 4, 11, 22, 0, 0, tzinfo=timezone.utc)
        assert not completion_matches_next_occurrence_period(
            t, anchor, gym, downstream_local_date="2026-04-11"
        )
        assert completion_matches_next_occurrence_period(
            t, anchor, gym, downstream_local_date="2026-04-10"
        )

    def test_daily_requires_upstream_local_date_when_downstream_sends_calendar_day(
        self,
    ) -> None:
        """Without this, UTC-only completion rows false-positive against client local_date."""
        t = _task(is_recurring=True, recurrence_rule="FREQ=DAILY")
        anchor = datetime(2026, 4, 12, 22, 0, 0, tzinfo=timezone.utc)
        c = _completion(
            scheduled_for=datetime(2026, 4, 12, 7, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 4, 12, 7, 1, 0, tzinfo=timezone.utc),
            local_date=None,
        )
        assert not completion_matches_next_occurrence_period(
            t, anchor, c, downstream_local_date="2026-04-12"
        )

    def test_lawn_weekly_mow_old_week_does_not_match(self) -> None:
        mow = _task(is_recurring=True, recurrence_rule="FREQ=WEEKLY;BYDAY=SA")
        anchor = datetime(2026, 4, 25, 10, 0, 0, tzinfo=timezone.utc)  # seeding week
        old_mow = _completion(
            scheduled_for=datetime(2026, 4, 4, 10, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 4, 4, 10, 5, 0, tzinfo=timezone.utc),
        )
        assert not completion_matches_next_occurrence_period(mow, anchor, old_mow)

    def test_scheduled_for_used_over_completed_at(self) -> None:
        t = _task(is_recurring=True, recurrence_rule="FREQ=DAILY")
        anchor = datetime(2026, 4, 10, 8, 0, 0, tzinfo=timezone.utc)
        c = _completion(
            scheduled_for=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 4, 11, 9, 0, 0, tzinfo=timezone.utc),
        )
        assert completion_matches_next_occurrence_period(t, anchor, c)

    def test_missing_scheduled_for_falls_back_to_completed_at(self) -> None:
        t = _task(is_recurring=True, recurrence_rule="FREQ=DAILY")
        anchor = datetime(2026, 4, 10, 8, 0, 0, tzinfo=timezone.utc)
        c = _completion(
            scheduled_for=None,
            completed_at=datetime(2026, 4, 10, 9, 0, 0, tzinfo=timezone.utc),
        )
        assert completion_matches_next_occurrence_period(t, anchor, c)


class TestFilterCompletionsNextOccurrencePeriod:
    def test_filters_to_matching_period_only(self) -> None:
        t = _task(is_recurring=True, recurrence_rule="FREQ=DAILY")
        anchor = datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc)
        same = _completion(
            scheduled_for=datetime(2026, 4, 12, 7, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 4, 12, 7, 1, 0, tzinfo=timezone.utc),
        )
        other = _completion(
            scheduled_for=datetime(2026, 4, 11, 7, 0, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 4, 11, 7, 1, 0, tzinfo=timezone.utc),
        )
        out = filter_completions_next_occurrence_period(t, anchor, [other, same])
        assert out == [same]

    def test_empty_input(self) -> None:
        t = _task(is_recurring=True, recurrence_rule="FREQ=DAILY")
        anchor = datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc)
        assert filter_completions_next_occurrence_period(t, anchor, []) == []
