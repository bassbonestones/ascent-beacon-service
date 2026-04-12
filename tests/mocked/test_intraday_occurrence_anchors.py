"""Unit tests for intraday_occurrence_anchors (dependency summary slots)."""
from __future__ import annotations

from datetime import date, datetime, time, timezone

import pytest

from app.services import intraday_occurrence_anchors as ioa_mod
from app.services.intraday_occurrence_anchors import (
    _dependency_scheduled_anchor,
    _generate_interval_times,
    _occurrence_scheduled_for,
    _safe_zone,
    get_intraday_occurrence_specs,
    list_dependency_anchors_for_day,
    parse_intraday_rrule,
    slot_key_from_suffix,
    uses_expanded_intraday_slots,
)


class _TRec:
    is_recurring = True
    scheduled_at: datetime | None = None
    scheduled_date: str | None = None
    recurrence_rule: str | None = None


class _TOne:
    is_recurring = False
    scheduled_at: datetime | None = None
    scheduled_date: str | None = None
    recurrence_rule: str | None = None


def test_slot_key_from_suffix() -> None:
    assert slot_key_from_suffix("") == ""
    assert slot_key_from_suffix("__0730") == "0730"
    assert slot_key_from_suffix("__occ2") == "occ2"
    assert slot_key_from_suffix("plain") == "plain"


def test_specific_times_three_slots() -> None:
    rule = "FREQ=DAILY;X-INTRADAY=specific_times;X-TIMES=08:00,12:00,18:00"
    parsed = parse_intraday_rrule(rule)
    specs = get_intraday_occurrence_specs(parsed)
    assert uses_expanded_intraday_slots(specs) is True
    assert [slot_key_from_suffix(s.suffix) for s in specs] == ["0800", "1200", "1800"]


def test_list_dependency_anchors_specific_times_utc() -> None:
    t = _TRec()
    t.scheduled_at = datetime(2030, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
    t.recurrence_rule = (
        "FREQ=DAILY;X-INTRADAY=specific_times;X-TIMES=08:00,12:00,18:00"
    )

    day = date(2030, 6, 10)
    anchors = list_dependency_anchors_for_day(t, day, None)
    assert len(anchors) == 3
    keys = [a[0] for a in anchors]
    assert keys == ["0800", "1200", "1800"]
    assert anchors[0][1].date() == day
    assert anchors[0][1].hour == 8


def test_anytime_specs_and_anchors() -> None:
    parsed = parse_intraday_rrule(
        "FREQ=DAILY;X-INTRADAY=anytime;X-DAILYOCC=2",
    )
    specs = get_intraday_occurrence_specs(parsed)
    assert len(specs) == 2
    assert uses_expanded_intraday_slots(specs) is True
    t = _TRec()
    t.recurrence_rule = "FREQ=DAILY;X-INTRADAY=anytime;X-DAILYOCC=2"
    t.scheduled_at = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    day = date(2030, 8, 1)
    anchors = list_dependency_anchors_for_day(t, day, "UTC")
    assert [a[0] for a in anchors] == ["occ1", "occ2"]
    assert anchors[0][1].hour == 23


def test_interval_mode_specs() -> None:
    parsed = parse_intraday_rrule(
        "FREQ=DAILY;X-INTRADAY=interval;X-WINSTART=10:00;X-WINEND=10:30;"
        "X-INTERVALMIN=15;X-DAILYOCC=2",
    )
    specs = get_intraday_occurrence_specs(parsed)
    assert len(specs) == 2
    assert specs[0].wall_time_hhmm == "10:00"


def test_window_mode_not_expanded() -> None:
    parsed = parse_intraday_rrule(
        "FREQ=DAILY;X-INTRADAY=window;X-WINSTART=09:00;X-WINEND=17:00",
    )
    specs = get_intraday_occurrence_specs(parsed)
    assert uses_expanded_intraday_slots(specs) is False


def test_specific_times_empty_uses_single_slot() -> None:
    parsed = parse_intraday_rrule("FREQ=DAILY;X-INTRADAY=specific_times")
    specs = get_intraday_occurrence_specs(parsed)
    assert len(specs) == 1 and specs[0].suffix == ""


def test_unknown_intraday_mode_fallback() -> None:
    parsed = parse_intraday_rrule("FREQ=DAILY;X-INTRADAY=weird")
    specs = get_intraday_occurrence_specs(parsed)
    assert len(specs) == 1 and specs[0].suffix == ""


def test_occurrence_recurring_with_client_timezone() -> None:
    t = _TRec()
    t.scheduled_at = datetime(2030, 1, 1, 15, 30, 0, tzinfo=timezone.utc)
    t.recurrence_rule = "FREQ=DAILY"
    out = _occurrence_scheduled_for(t, date(2030, 5, 5), "America/New_York")
    assert out is not None
    assert out.tzinfo is not None


def test_recurring_no_scheduled_at_utc_timezone() -> None:
    t = _TRec()
    t.scheduled_at = None
    t.recurrence_rule = "FREQ=DAILY"
    out = _occurrence_scheduled_for(t, date(2030, 5, 5), "UTC")
    assert out is not None
    assert out.hour == 23


def test_one_shot_scheduled_date_with_tz() -> None:
    t = _TOne()
    t.scheduled_date = "2030-05-05"
    out = _occurrence_scheduled_for(t, date(2030, 5, 5), "Europe/London")
    assert out is not None
    assert out.hour == 23


def test_safe_zone_invalid_falls_back() -> None:
    z = _safe_zone("Not/A/Real/Zone/Name")
    assert z is timezone.utc


def test_dependency_anchor_midnight() -> None:
    dt = datetime(2030, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    out = _dependency_scheduled_anchor(dt)
    assert out.hour == 23 and out.minute == 59


def test_list_anchors_invalid_tz_uses_utc_for_slots() -> None:
    t = _TRec()
    t.recurrence_rule = "FREQ=DAILY;X-INTRADAY=specific_times;X-TIMES=11:00"
    t.scheduled_at = datetime(2030, 1, 1, 8, 0, 0, tzinfo=timezone.utc)
    anchors = list_dependency_anchors_for_day(t, date(2030, 9, 9), "bogus-tz")
    assert len(anchors) == 1
    assert anchors[0][0] == "1100"


def test_non_recurring_wrong_day_empty_anchors() -> None:
    t = _TOne()
    t.scheduled_at = datetime(2030, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert list_dependency_anchors_for_day(t, date(2030, 1, 2), None) == []


def test_parse_skips_parts_without_equals() -> None:
    parsed = parse_intraday_rrule("FREQ=DAILY;orphan;X-INTRADAY=single")
    assert parsed.intraday_mode == "single"


def test_interval_empty_window_returns_single_untimed_spec() -> None:
    parsed = parse_intraday_rrule(
        "FREQ=DAILY;X-INTRADAY=interval;X-WINSTART=12:00;X-WINEND=11:00;X-INTERVALMIN=30",
    )
    specs = get_intraday_occurrence_specs(parsed)
    assert len(specs) == 1 and specs[0].wall_time_hhmm is None


def test_one_shot_no_schedule_end_of_day() -> None:
    t = _TOne()
    t.scheduled_at = None
    t.scheduled_date = None
    out = _occurrence_scheduled_for(t, date(2030, 3, 3), None)
    assert out is not None and out.hour == 23


def test_one_shot_no_schedule_invalid_client_tz() -> None:
    t = _TOne()
    t.scheduled_at = None
    t.scheduled_date = None
    out = _occurrence_scheduled_for(t, date(2030, 3, 3), "bad/tz")
    assert out is not None and out.tzinfo == timezone.utc


def test_get_specs_default_single_mode() -> None:
    parsed = parse_intraday_rrule("FREQ=DAILY")
    specs = get_intraday_occurrence_specs(parsed)
    assert len(specs) == 1 and specs[0].suffix == ""


def test_list_recurring_collapsed_when_anchor_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ioa_mod,
        "_occurrence_scheduled_for",
        lambda *args, **kwargs: None,
    )
    t = _TRec()
    t.recurrence_rule = "FREQ=DAILY"
    t.scheduled_at = datetime(2030, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    assert list_dependency_anchors_for_day(t, date(2030, 2, 2), None) == []


def test_recurring_scheduled_at_invalid_tz_falls_back_to_template_tz() -> None:
    t = _TRec()
    t.scheduled_at = datetime(2030, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
    t.recurrence_rule = "FREQ=DAILY"
    out = _occurrence_scheduled_for(t, date(2030, 4, 4), "Not/A/Tz")
    assert out is not None
    assert out.hour == 14


def test_interval_max_occurrences_break_in_generate() -> None:
    times = _generate_interval_times("09:00", "12:00", 60, 2)
    assert len(times) == 2
