"""
Intraday occurrence anchors for dependency summaries (align with mobile taskSorting).

Mobile keys virtual rows by suffix after the calendar date: "", "0730", "occ1", etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

if TYPE_CHECKING:
    from app.models import Task

_END_OF_DAY = time(23, 59, 59, 999999)


@dataclass(frozen=True)
class IntradayOccurrenceSpec:
    """One row within a calendar day (matches mobile getIntradayOccurrences)."""

    wall_time_hhmm: str | None  # "HH:MM" or None for anytime / window / single untimed
    suffix: str  # "", "__0730", "__occ1"


@dataclass(frozen=True)
class ParsedIntradayRRule:
    intraday_mode: str
    specific_times: tuple[str, ...]
    interval_minutes: int
    window_start: str
    window_end: str
    daily_occurrences: int


def slot_key_from_suffix(suffix: str) -> str:
    if not suffix:
        return ""
    if suffix.startswith("__"):
        return suffix[2:]
    return suffix


def parse_intraday_rrule(recurrence_rule: str) -> ParsedIntradayRRule:
    parts: dict[str, str] = {}
    for part in recurrence_rule.split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            parts[k] = v
    mode = parts.get("X-INTRADAY", "single")
    times = (
        tuple(t for t in parts["X-TIMES"].split(",") if t)
        if parts.get("X-TIMES")
        else ()
    )
    interval_minutes = int(parts.get("X-INTERVALMIN", "30"))
    window_start = parts.get("X-WINSTART", "09:00")
    window_end = parts.get("X-WINEND", "21:00")
    daily_occurrences = int(parts["X-DAILYOCC"]) if parts.get("X-DAILYOCC") else 0
    return ParsedIntradayRRule(
        intraday_mode=mode,
        specific_times=times,
        interval_minutes=interval_minutes,
        window_start=window_start,
        window_end=window_end,
        daily_occurrences=daily_occurrences,
    )


def _generate_interval_times(
    window_start: str,
    window_end: str,
    interval_minutes: int,
    max_occurrences: int | None,
) -> list[str]:
    sh, sm = (int(x) for x in window_start.split(":")[:2])
    eh, em = (int(x) for x in window_end.split(":")[:2])
    start_minutes = sh * 60 + sm
    end_minutes = eh * 60 + em
    times: list[str] = []
    cur = start_minutes
    while cur <= end_minutes:
        if max_occurrences is not None and len(times) >= max_occurrences:
            break
        h, m = divmod(cur, 60)
        times.append(f"{h:02d}:{m:02d}")
        cur += interval_minutes
    return times


def get_intraday_occurrence_specs(parsed: ParsedIntradayRRule) -> list[IntradayOccurrenceSpec]:
    mode = parsed.intraday_mode
    if mode == "single":
        return [IntradayOccurrenceSpec(wall_time_hhmm=None, suffix="")]
    if mode == "anytime":
        n = parsed.daily_occurrences if parsed.daily_occurrences > 0 else 1
        return [
            IntradayOccurrenceSpec(wall_time_hhmm=None, suffix=f"__occ{i + 1}")
            for i in range(n)
        ]
    if mode == "specific_times":
        if not parsed.specific_times:
            return [IntradayOccurrenceSpec(wall_time_hhmm=None, suffix="")]
        return [
            IntradayOccurrenceSpec(
                wall_time_hhmm=t,
                suffix=f"__{t.replace(':', '')}",
            )
            for t in parsed.specific_times
        ]
    if mode == "interval":
        max_o = parsed.daily_occurrences if parsed.daily_occurrences > 0 else None
        interval_times = _generate_interval_times(
            parsed.window_start,
            parsed.window_end,
            parsed.interval_minutes,
            max_o,
        )
        if not interval_times:
            return [IntradayOccurrenceSpec(wall_time_hhmm=None, suffix="")]
        return [
            IntradayOccurrenceSpec(
                wall_time_hhmm=t,
                suffix=f"__{t.replace(':', '')}",
            )
            for t in interval_times
        ]
    if mode == "window":
        return [IntradayOccurrenceSpec(wall_time_hhmm=None, suffix="")]
    return [IntradayOccurrenceSpec(wall_time_hhmm=None, suffix="")]


def uses_expanded_intraday_slots(specs: list[IntradayOccurrenceSpec]) -> bool:
    """Match mobile: intradayOccs.length > 1 || intradayOccs[0].time !== null."""
    if len(specs) > 1:
        return True
    return bool(specs and specs[0].wall_time_hhmm is not None)


def _dependency_scheduled_anchor(dt: datetime) -> datetime:
    if dt.hour == 0 and dt.minute == 0 and dt.second == 0 and dt.microsecond == 0:
        return dt.replace(hour=23, minute=59, second=59, microsecond=999999)
    return dt


def _safe_zone(name: str | None) -> ZoneInfo | timezone:
    if not name:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:
        return timezone.utc


def _occurrence_scheduled_for(
    task: Task,
    client_day: date,
    client_timezone: str | None,
) -> datetime | None:
    """Best-effort scheduled_for for dependency checks on client_day (single slot)."""
    if task.is_recurring:
        if task.scheduled_at:
            st = task.scheduled_at
            if st.tzinfo is None:
                st = st.replace(tzinfo=timezone.utc)
            if client_timezone:
                zi = _safe_zone(client_timezone)
                if isinstance(zi, ZoneInfo):
                    local_st = st.astimezone(zi)
                    combined = datetime.combine(
                        client_day,
                        time(local_st.hour, local_st.minute, local_st.second),
                        tzinfo=zi,
                    )
                    return _dependency_scheduled_anchor(combined)
            tz = st.tzinfo or timezone.utc
            combined = datetime.combine(client_day, st.time(), tzinfo=tz)
            return _dependency_scheduled_anchor(combined)
        tzinfo = _safe_zone(client_timezone) if client_timezone else timezone.utc
        if isinstance(tzinfo, ZoneInfo):
            return datetime.combine(client_day, _END_OF_DAY, tzinfo=tzinfo)
        return datetime.combine(client_day, _END_OF_DAY, tzinfo=timezone.utc)
    if task.scheduled_at:
        st = task.scheduled_at
        if st.tzinfo is None:
            st = st.replace(tzinfo=timezone.utc)
        if st.date() != client_day:
            return None
        return _dependency_scheduled_anchor(st)
    if task.scheduled_date:
        try:
            sd = datetime.strptime(task.scheduled_date, "%Y-%m-%d").date()
        except ValueError:
            return None
        if sd != client_day:
            return None
        tzinfo = _safe_zone(client_timezone) if client_timezone else timezone.utc
        if isinstance(tzinfo, ZoneInfo):
            return datetime.combine(client_day, _END_OF_DAY, tzinfo=tzinfo)
        return datetime.combine(client_day, _END_OF_DAY, tzinfo=timezone.utc)
    tzinfo = _safe_zone(client_timezone) if client_timezone else timezone.utc
    if isinstance(tzinfo, ZoneInfo):
        return datetime.combine(client_day, _END_OF_DAY, tzinfo=tzinfo)
    return datetime.combine(client_day, _END_OF_DAY, tzinfo=timezone.utc)


def _parse_hhmm(hhmm: str) -> time:
    h_str, m_str = hhmm.split(":")[:2]
    return time(int(h_str), int(m_str), 0)


def list_dependency_anchors_for_day(
    task: Task,
    client_day: date,
    client_timezone: str | None,
) -> list[tuple[str, datetime]]:
    """
    Ordered (slot_key, scheduled_for) for check_dependencies on client_day.

    slot_key matches mobile (suffix without leading '__').
    """
    if not task.is_recurring or not task.recurrence_rule:
        anchor = _occurrence_scheduled_for(task, client_day, client_timezone)
        if anchor is None:
            return []
        return [("", anchor)]

    parsed = parse_intraday_rrule(task.recurrence_rule)
    specs = get_intraday_occurrence_specs(parsed)
    if not uses_expanded_intraday_slots(specs):
        anchor = _occurrence_scheduled_for(task, client_day, client_timezone)
        if anchor is None:
            return []
        return [("", anchor)]

    zi = _safe_zone(client_timezone)
    tz_for_combine: ZoneInfo | timezone = (
        zi if isinstance(zi, ZoneInfo) else timezone.utc
    )
    out: list[tuple[str, datetime]] = []
    for spec in specs:
        sk = slot_key_from_suffix(spec.suffix)
        if spec.wall_time_hhmm is None:
            anchor = datetime.combine(client_day, _END_OF_DAY, tzinfo=tz_for_combine)
        else:
            t_wall = _parse_hhmm(spec.wall_time_hhmm)
            anchor = datetime.combine(client_day, t_wall, tzinfo=tz_for_combine)
        out.append((sk, _dependency_scheduled_anchor(anchor)))
    return out
