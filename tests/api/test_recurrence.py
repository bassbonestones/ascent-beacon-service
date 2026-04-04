"""Tests for the recurrence service."""
import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.services.recurrence import (
    parse_rrule,
    get_next_occurrence,
    get_occurrences_in_range,
    get_today_occurrences,
    build_rrule_string,
    get_frequency_description,
)


class TestParseRRule:
    """Tests for parse_rrule function."""
    
    def test_parse_daily_rule(self) -> None:
        """Test parsing a daily recurrence rule."""
        rrule_str = "FREQ=DAILY"
        rule = parse_rrule(rrule_str)
        assert rule is not None
    
    def test_parse_weekly_rule(self) -> None:
        """Test parsing a weekly recurrence rule."""
        rrule_str = "FREQ=WEEKLY;BYDAY=MO,WE,FR"
        rule = parse_rrule(rrule_str)
        assert rule is not None
    
    def test_parse_monthly_rule(self) -> None:
        """Test parsing a monthly recurrence rule."""
        rrule_str = "FREQ=MONTHLY;BYMONTHDAY=15"
        rule = parse_rrule(rrule_str)
        assert rule is not None
    
    def test_parse_with_dtstart(self) -> None:
        """Test parsing with explicit DTSTART."""
        rrule_str = "DTSTART:20240101T090000Z\nFREQ=DAILY"
        rule = parse_rrule(rrule_str)
        assert rule is not None
    
    def test_parse_invalid_rule(self) -> None:
        """Test parsing an invalid rule raises error."""
        with pytest.raises(ValueError):
            parse_rrule("INVALID_RULE")
    
    def test_parse_empty_rule(self) -> None:
        """Test parsing empty string raises error."""
        with pytest.raises(ValueError):
            parse_rrule("")


class TestGetNextOccurrence:
    """Tests for get_next_occurrence function."""
    
    def test_next_daily_occurrence(self) -> None:
        """Test getting next occurrence for daily rule."""
        rrule_str = "FREQ=DAILY"
        start = datetime(2024, 1, 1, 9, 0, tzinfo=ZoneInfo("UTC"))
        after = datetime(2024, 1, 1, 10, 0, tzinfo=ZoneInfo("UTC"))
        
        next_occ = get_next_occurrence(rrule_str, start, after)
        
        assert next_occ is not None
        assert next_occ.date() == datetime(2024, 1, 2).date()
    
    def test_next_weekly_occurrence(self) -> None:
        """Test getting next occurrence for weekly rule on specific days."""
        # Monday, Wednesday, Friday
        rrule_str = "FREQ=WEEKLY;BYDAY=MO,WE,FR"
        # Start on a Monday
        start = datetime(2024, 1, 1, 9, 0, tzinfo=ZoneInfo("UTC"))  # Monday
        after = datetime(2024, 1, 1, 10, 0, tzinfo=ZoneInfo("UTC"))
        
        next_occ = get_next_occurrence(rrule_str, start, after)
        
        assert next_occ is not None
        # Next should be Wednesday (Jan 3)
        assert next_occ.weekday() == 2  # Wednesday
    
    def test_no_more_occurrences(self) -> None:
        """Test when rule has no more occurrences (COUNT limit reached)."""
        rrule_str = "FREQ=DAILY;COUNT=1"
        start = datetime(2024, 1, 1, 9, 0, tzinfo=ZoneInfo("UTC"))
        # After should be past the single occurrence
        after = datetime(2024, 1, 2, 0, 0, tzinfo=ZoneInfo("UTC"))
        
        # Should return None when no more occurrences
        next_occ = get_next_occurrence(rrule_str, start, after)
        
        assert next_occ is None
    
    def test_invalid_rrule(self) -> None:
        """Test with invalid rrule."""
        result = get_next_occurrence(
            "INVALID",
            datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC")),
            datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC")),
        )
        assert result is None


class TestGetOccurrencesInRange:
    """Tests for get_occurrences_in_range function."""
    
    def test_daily_occurrences_in_range(self) -> None:
        """Test getting daily occurrences within a date range."""
        rrule_str = "FREQ=DAILY"
        range_start = datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC"))
        range_end = datetime(2024, 1, 3, 23, 59, 59, tzinfo=ZoneInfo("UTC"))
        
        occurrences = get_occurrences_in_range(rrule_str, range_start, range_end)
        
        # Should have 3 occurrences (Jan 1, 2, 3)
        assert len(occurrences) == 3
    
    def test_weekly_occurrences_in_range(self) -> None:
        """Test getting weekly occurrences (M/W/F) in a 7-day range."""
        rrule_str = "FREQ=WEEKLY;BYDAY=MO,WE,FR"
        range_start = datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC"))  # Monday
        range_end = datetime(2024, 1, 7, 23, 59, 59, tzinfo=ZoneInfo("UTC"))
        
        occurrences = get_occurrences_in_range(rrule_str, range_start, range_end)
        
        # M/W/F in a week = 3 occurrences
        assert len(occurrences) == 3
    
    def test_max_count_limit(self) -> None:
        """Test that max_count parameter limits results."""
        rrule_str = "FREQ=DAILY"
        range_start = datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC"))
        range_end = datetime(2024, 12, 31, tzinfo=ZoneInfo("UTC"))
        
        occurrences = get_occurrences_in_range(
            rrule_str, range_start, range_end, max_count=5
        )
        
        assert len(occurrences) == 5
    
    def test_empty_range(self) -> None:
        """Test when no occurrences fall within range."""
        rrule_str = "FREQ=WEEKLY;BYDAY=FR"  # Fridays only
        # Monday-Tuesday range, no Fridays. Jan 1, 2024 is Monday.
        range_start = datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC"))
        range_end = datetime(2024, 1, 2, tzinfo=ZoneInfo("UTC"))
        
        occurrences = get_occurrences_in_range(rrule_str, range_start, range_end)
        
        assert len(occurrences) == 0
    
    def test_invalid_rrule(self) -> None:
        """Test with invalid rrule returns empty list."""
        result = get_occurrences_in_range(
            "INVALID",
            datetime(2024, 1, 1, tzinfo=ZoneInfo("UTC")),
            datetime(2024, 1, 31, tzinfo=ZoneInfo("UTC")),
        )
        assert result == []


class TestGetTodayOccurrences:
    """Tests for get_today_occurrences function."""
    
    def test_daily_has_today_occurrence(self) -> None:
        """Test that daily task has occurrence today."""
        rrule_str = "FREQ=DAILY"
        
        occurrences = get_today_occurrences(rrule_str, "UTC")
        
        # Daily always has today
        assert len(occurrences) >= 1
    
    def test_timezone_handling(self) -> None:
        """Test that timezone is respected."""
        rrule_str = "FREQ=DAILY"
        
        # Test with different timezone
        occurrences = get_today_occurrences(rrule_str, "America/New_York")
        
        assert isinstance(occurrences, list)


class TestBuildRRuleString:
    """Tests for build_rrule_string function."""
    
    def test_build_daily(self) -> None:
        """Test building daily rule."""
        result = build_rrule_string(frequency="DAILY")
        assert "FREQ=DAILY" in result
    
    def test_build_weekly_with_days(self) -> None:
        """Test building weekly rule with specific days."""
        result = build_rrule_string(frequency="WEEKLY", by_day=["MO", "WE", "FR"])
        assert "FREQ=WEEKLY" in result
        assert "BYDAY=MO,WE,FR" in result
    
    def test_build_monthly(self) -> None:
        """Test building monthly rule."""
        result = build_rrule_string(frequency="MONTHLY")
        assert "FREQ=MONTHLY" in result
    
    def test_build_with_interval(self) -> None:
        """Test building rule with interval."""
        result = build_rrule_string(frequency="DAILY", interval=2)
        assert "FREQ=DAILY" in result
        assert "INTERVAL=2" in result
    
    def test_build_with_count(self) -> None:
        """Test building rule with count limit."""
        result = build_rrule_string(frequency="DAILY", count=10)
        assert "FREQ=DAILY" in result
        assert "COUNT=10" in result
    
    def test_build_with_until(self) -> None:
        """Test building rule with end date."""
        until = datetime(2024, 12, 31, tzinfo=ZoneInfo("UTC"))
        result = build_rrule_string(frequency="DAILY", until=until)
        assert "FREQ=DAILY" in result
        assert "UNTIL=" in result
    
    def test_build_yearly(self) -> None:
        """Test building yearly rule."""
        result = build_rrule_string(frequency="YEARLY")
        assert "FREQ=YEARLY" in result
    
    def test_build_with_hour_minute(self) -> None:
        """Test building rule with specific time."""
        result = build_rrule_string(frequency="DAILY", by_hour=9, by_minute=30)
        assert "FREQ=DAILY" in result
        assert "BYHOUR=9" in result
        assert "BYMINUTE=30" in result


class TestGetFrequencyDescription:
    """Tests for get_frequency_description function."""
    
    def test_daily_description(self) -> None:
        """Test description for daily rule."""
        result = get_frequency_description("FREQ=DAILY")
        assert "Daily" in result or "daily" in result.lower()
    
    def test_weekly_description(self) -> None:
        """Test description for weekly rule."""
        result = get_frequency_description("FREQ=WEEKLY")
        assert "Weekly" in result or "week" in result.lower()
    
    def test_monthly_description(self) -> None:
        """Test description for monthly rule."""
        result = get_frequency_description("FREQ=MONTHLY")
        assert "Monthly" in result or "month" in result.lower()
    
    def test_yearly_description(self) -> None:
        """Test description for yearly rule."""
        result = get_frequency_description("FREQ=YEARLY")
        assert "Yearly" in result or "year" in result.lower()
    
    def test_with_interval(self) -> None:
        """Test description with interval."""
        result = get_frequency_description("FREQ=DAILY;INTERVAL=2")
        assert "2" in result
    
    def test_with_days(self) -> None:
        """Test description with specific days."""
        result = get_frequency_description("FREQ=WEEKLY;BYDAY=MO,WE,FR")
        # Should mention some days or weekdays
        assert len(result) > 0
    
    def test_invalid_rrule(self) -> None:
        """Test with invalid rrule."""
        result = get_frequency_description("INVALID")
        assert result == "Custom"
