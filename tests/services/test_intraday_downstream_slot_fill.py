from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.intraday_downstream_slot_fill import (
    _anchors_share_identical_scheduled_for,
    _normalize,
    _safe_zone,
    _same_wall_minute,
    first_pending_slot_index,
    unfilled_anchor_indices,
)


def _c(
    scheduled_for: datetime | None = None,
    completed_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(scheduled_for=scheduled_for, completed_at=completed_at)


def test_safe_zone_handles_missing_and_invalid_names() -> None:
    assert _safe_zone(None) is timezone.utc
    assert _safe_zone("bad/tz") is timezone.utc


def test_normalize_adds_utc_to_naive_datetime() -> None:
    naive = datetime(2030, 1, 1, 9, 0, 0)
    aware = _normalize(naive)
    assert aware.tzinfo is timezone.utc


def test_anchors_share_identical_scheduled_for_checks_two_second_tolerance() -> None:
    base = datetime(2030, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
    close = datetime(2030, 1, 1, 9, 0, 1, tzinfo=timezone.utc)
    far = datetime(2030, 1, 1, 9, 0, 3, tzinfo=timezone.utc)
    assert _anchors_share_identical_scheduled_for([("a", base), ("b", close)]) is True
    assert _anchors_share_identical_scheduled_for([("a", base), ("b", far)]) is False


def test_same_wall_minute_compares_in_client_timezone() -> None:
    a = datetime(2030, 1, 1, 15, 30, 0, tzinfo=timezone.utc)
    b = datetime(2030, 1, 1, 15, 30, 30, tzinfo=timezone.utc)
    c = datetime(2030, 1, 1, 15, 31, 0, tzinfo=timezone.utc)
    assert _same_wall_minute(a, b, "America/New_York") is True
    assert _same_wall_minute(a, b, "bad/tz") is True
    assert _same_wall_minute(a, c, "bad/tz") is False


def test_first_pending_slot_index_returns_none_for_single_anchor() -> None:
    anchors = [("a", datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc))]
    assert first_pending_slot_index(anchors, [], "UTC") is None


def test_first_pending_slot_index_for_identical_anchor_times_uses_completion_count() -> None:
    dt = datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc)
    anchors = [("a", dt), ("b", dt), ("c", dt)]
    completions = [_c(completed_at=dt), _c(completed_at=dt)]
    assert first_pending_slot_index(anchors, completions, "UTC") == 2


def test_first_pending_slot_index_matches_non_identical_slots_by_wall_minute() -> None:
    anchors = [
        ("a", datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc)),
        ("b", datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)),
        ("c", datetime(2030, 1, 1, 11, 0, tzinfo=timezone.utc)),
    ]
    completions = [
        _c(scheduled_for=datetime(2030, 1, 1, 9, 0, 30, tzinfo=timezone.utc)),
        _c(completed_at=datetime(2030, 1, 1, 10, 0, 59, tzinfo=timezone.utc)),
        _c(scheduled_for=None, completed_at=None),
    ]
    assert first_pending_slot_index(anchors, completions, "UTC") == 2


def test_first_pending_slot_index_returns_none_when_all_slots_filled() -> None:
    anchors = [
        ("a", datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc)),
        ("b", datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)),
    ]
    completions = [
        _c(scheduled_for=datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc)),
        _c(completed_at=datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)),
    ]
    assert first_pending_slot_index(anchors, completions, "UTC") is None


def test_unfilled_anchor_indices_handles_empty_and_identical_anchor_times() -> None:
    assert unfilled_anchor_indices([], [], "UTC") == []
    dt = datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc)
    anchors = [("a", dt), ("b", dt), ("c", dt)]
    completions = [_c(completed_at=dt)]
    assert unfilled_anchor_indices(anchors, completions, "UTC") == [1, 2]


def test_unfilled_anchor_indices_non_identical_times_respects_single_use_matching() -> None:
    anchors = [
        ("a", datetime(2030, 1, 1, 9, 0, tzinfo=timezone.utc)),
        ("b", datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)),
        ("c", datetime(2030, 1, 1, 11, 0, tzinfo=timezone.utc)),
    ]
    completions = [
        _c(scheduled_for=datetime(2030, 1, 1, 9, 0, 15, tzinfo=timezone.utc)),
        _c(completed_at=datetime(2030, 1, 1, 9, 0, 45, tzinfo=timezone.utc)),
    ]
    # second completion targets same slot, so only index 0 is filled
    assert unfilled_anchor_indices(anchors, completions, "UTC") == [1, 2]
