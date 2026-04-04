"""
Recurrence service for RRULE parsing and occurrence calculation.

Phase 4b: Recurrence Engine

Uses python-dateutil for iCal RRULE parsing. Supports:
- All RRULE frequencies (minutely, hourly, daily, weekly, monthly, yearly)
- Flexible day/time patterns
- Floating (time-of-day) vs Fixed (timezone-locked) scheduling
"""
from datetime import datetime, date, timedelta
from typing import List, Optional
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr, rrule, rruleset
from dateutil.rrule import DAILY, WEEKLY, MONTHLY, YEARLY
from loguru import logger

from typing import Union

# Type alias for rrule results
RRuleType = Union[rrule, rruleset]


# Constants for scheduling modes
SCHEDULING_MODE_FLOATING = "floating"  # "Time-of-day" - adjusts with timezone
SCHEDULING_MODE_FIXED = "fixed"  # "Fixed time" - timezone-locked


def parse_rrule(rule_string: str, dtstart: Optional[datetime] = None) -> RRuleType:
    """
    Parse an RRULE string into a dateutil rrule object.
    
    Args:
        rule_string: iCal RRULE string (e.g., "FREQ=DAILY;BYHOUR=9")
        dtstart: Start datetime for the rule (defaults to now)
    
    Returns:
        Parsed rrule object
        
    Raises:
        ValueError: If the RRULE string is invalid
    """
    try:
        if dtstart is None:
            dtstart = datetime.now(ZoneInfo("UTC"))
        
        # If DTSTART is in the rule, use that
        if "DTSTART" in rule_string.upper():
            return rrulestr(rule_string)
        
        # Otherwise use provided dtstart
        return rrulestr(rule_string, dtstart=dtstart)
    except Exception as e:
        logger.error(f"Failed to parse RRULE: {rule_string} - {e}")
        raise ValueError(f"Invalid RRULE: {rule_string}") from e


def get_next_occurrence(
    rule_string: str,
    after: Optional[datetime] = None,
    scheduling_mode: Optional[str] = None,
    user_timezone: Optional[str] = None,
) -> Optional[datetime]:
    """
    Get the next occurrence of a recurring task.
    
    Args:
        rule_string: iCal RRULE string
        after: Get occurrence after this datetime (defaults to now)
        scheduling_mode: 'floating' or 'fixed'
        user_timezone: User's current timezone (for floating tasks)
    
    Returns:
        Next occurrence datetime (in UTC), or None if no more occurrences
    """
    if after is None:
        after = datetime.now(ZoneInfo("UTC"))
    
    try:
        rule = parse_rrule(rule_string, dtstart=after)
        next_dt = rule.after(after, inc=False)
        
        if next_dt is None:
            return None
        
        # Ensure we have a datetime (not date)
        if not isinstance(next_dt, datetime):
            return None
        
        # For floating times, adjust to user's timezone
        if scheduling_mode == SCHEDULING_MODE_FLOATING and user_timezone:
            next_dt = _adjust_floating_time(next_dt, user_timezone)
        
        return next_dt
    except ValueError:
        return None


def get_occurrences_in_range(
    rule_string: str,
    start: datetime,
    end: datetime,
    scheduling_mode: Optional[str] = None,
    user_timezone: Optional[str] = None,
    max_count: int = 100,
) -> List[datetime]:
    """
    Get all occurrences of a recurring task within a date range.
    
    Args:
        rule_string: iCal RRULE string
        start: Start of range (inclusive)
        end: End of range (inclusive)
        scheduling_mode: 'floating' or 'fixed'
        user_timezone: User's current timezone (for floating tasks)
        max_count: Maximum number of occurrences to return
    
    Returns:
        List of occurrence datetimes (in UTC)
    """
    try:
        rule = parse_rrule(rule_string, dtstart=start)
        occurrences = list(rule.between(start, end, inc=True))[:max_count]
        
        # For floating times, adjust to user's timezone
        if scheduling_mode == SCHEDULING_MODE_FLOATING and user_timezone:
            occurrences = [
                _adjust_floating_time(dt, user_timezone) for dt in occurrences
            ]
        
        return occurrences
    except ValueError:
        return []


def get_today_occurrences(
    rule_string: str,
    user_timezone: str = "UTC",
    scheduling_mode: Optional[str] = None,
) -> List[datetime]:
    """
    Get all occurrences for today in user's timezone.
    
    Args:
        rule_string: iCal RRULE string
        user_timezone: User's timezone for "today" calculation
        scheduling_mode: 'floating' or 'fixed'
    
    Returns:
        List of today's occurrence datetimes
    """
    tz = ZoneInfo(user_timezone)
    now = datetime.now(tz)
    
    # Start and end of today in user's timezone
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1) - timedelta(microseconds=1)
    
    return get_occurrences_in_range(
        rule_string,
        start_of_day,
        end_of_day,
        scheduling_mode=scheduling_mode,
        user_timezone=user_timezone,
    )


def count_expected_occurrences(
    rule_string: str,
    start: datetime,
    end: datetime,
) -> int:
    """
    Count expected occurrences in a date range (for stats calculation).
    
    Args:
        rule_string: iCal RRULE string
        start: Start of range
        end: End of range
    
    Returns:
        Number of expected occurrences
    """
    # Just count occurrences in range - simple and reliable
    return len(get_occurrences_in_range(rule_string, start, end, max_count=1000))


def is_overdue(
    rule_string: str,
    last_completed_at: Optional[datetime],
    scheduling_mode: Optional[str] = None,
    user_timezone: str = "UTC",
) -> bool:
    """
    Check if a recurring task has an overdue occurrence.
    
    Args:
        rule_string: iCal RRULE string
        last_completed_at: When the task was last completed
        scheduling_mode: 'floating' or 'fixed'
        user_timezone: User's timezone
    
    Returns:
        True if there's an overdue occurrence
    """
    now = datetime.now(ZoneInfo("UTC"))
    
    # If never completed, check if any occurrence has passed
    if last_completed_at is None:
        last_completed_at = datetime.min.replace(tzinfo=ZoneInfo("UTC"))
    
    # Get next occurrence after last completion
    next_occ = get_next_occurrence(
        rule_string,
        after=last_completed_at,
        scheduling_mode=scheduling_mode,
        user_timezone=user_timezone,
    )
    
    if next_occ is None:
        return False
    
    return next_occ < now


def _adjust_floating_time(dt: datetime, user_timezone: str) -> datetime:
    """
    Adjust a floating time to the user's current timezone.
    
    For floating times, the time-of-day is fixed (e.g., 7am) but the
    actual UTC moment changes based on user's location.
    
    Args:
        dt: Original datetime
        user_timezone: User's current timezone
    
    Returns:
        Adjusted datetime in UTC
    """
    try:
        tz = ZoneInfo(user_timezone)
        # Extract time-of-day from original
        time_of_day = dt.time()
        # Apply to user's timezone
        local_dt = datetime.combine(dt.date(), time_of_day, tzinfo=tz)
        # Convert back to UTC
        return local_dt.astimezone(ZoneInfo("UTC"))
    except Exception as e:
        logger.warning(f"Failed to adjust floating time: {e}")
        return dt


def build_rrule_string(
    frequency: str,
    interval: int = 1,
    by_day: Optional[List[str]] = None,
    by_hour: Optional[int] = None,
    by_minute: Optional[int] = None,
    until: Optional[datetime] = None,
    count: Optional[int] = None,
) -> str:
    """
    Build an RRULE string from components.
    
    Args:
        frequency: DAILY, WEEKLY, MONTHLY, YEARLY
        interval: Every N frequency units
        by_day: List of days (MO, TU, WE, TH, FR, SA, SU)
        by_hour: Hour of day (0-23)
        by_minute: Minute of hour (0-59)
        until: End date for recurrence
        count: Number of occurrences
    
    Returns:
        RRULE string
    """
    parts = [f"FREQ={frequency.upper()}"]
    
    if interval > 1:
        parts.append(f"INTERVAL={interval}")
    
    if by_day:
        parts.append(f"BYDAY={','.join(by_day)}")
    
    if by_hour is not None:
        parts.append(f"BYHOUR={by_hour}")
    
    if by_minute is not None:
        parts.append(f"BYMINUTE={by_minute}")
    
    if until:
        parts.append(f"UNTIL={until.strftime('%Y%m%dT%H%M%SZ')}")
    elif count:
        parts.append(f"COUNT={count}")
    
    return ";".join(parts)


def get_frequency_description(rule_string: str) -> str:
    """
    Get a human-readable description of the recurrence pattern.
    
    Args:
        rule_string: iCal RRULE string
    
    Returns:
        Human-readable description (e.g., "Daily at 9:00 AM")
    """
    try:
        # Parse the RRULE string directly
        parts = dict(p.split("=", 1) for p in rule_string.split(";") if "=" in p)
        
        # Map frequency to text
        freq_map = {
            "YEARLY": "Yearly",
            "MONTHLY": "Monthly",
            "WEEKLY": "Weekly",
            "DAILY": "Daily",
            "HOURLY": "Hourly",
            "MINUTELY": "Minutely",
        }
        
        freq = parts.get("FREQ", "").upper()
        freq_text = freq_map.get(freq, "Custom")
        
        # Add interval if > 1
        interval = parts.get("INTERVAL", "1")
        if interval != "1":
            freq_text = f"Every {interval} {freq_text.lower()}"
        
        # Add day info for weekly
        if "BYDAY" in parts:
            day_map = {"MO": "Mon", "TU": "Tue", "WE": "Wed", "TH": "Thu", 
                       "FR": "Fri", "SA": "Sat", "SU": "Sun"}
            days = [day_map.get(d.strip(), d) for d in parts["BYDAY"].split(",")]
            freq_text += f" on {', '.join(days)}"
        
        # Add time info
        if "BYHOUR" in parts:
            hour = int(parts["BYHOUR"].split(",")[0])
            minute = int(parts.get("BYMINUTE", "0").split(",")[0])
            time_str = f"{hour:02d}:{minute:02d}"
            freq_text += f" at {time_str}"
        
        return freq_text
    except Exception:
        return "Custom recurrence"
