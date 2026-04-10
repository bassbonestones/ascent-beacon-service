"""
Pure helper functions for completion data processing.

These functions extract complex logic from tasks.py for easier unit testing.
All functions are pure - no async, no DB access.
"""
from datetime import datetime, timezone
from dataclasses import dataclass, field


@dataclass
class CompletionDataMaps:
    """Container for all completion tracking data structures."""
    completions_today_count: dict[str, int] = field(default_factory=dict)
    completions_today_times: dict[str, list[str]] = field(default_factory=dict)
    completions_by_date_map: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    skips_today_count: dict[str, int] = field(default_factory=dict)
    skips_today_times: dict[str, list[str]] = field(default_factory=dict)
    skips_by_date_map: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    skip_reason_today_map: dict[str, str | None] = field(default_factory=dict)
    skip_reasons_by_date_map: dict[str, dict[str, str | None]] = field(default_factory=dict)


def ensure_timezone_aware(dt: datetime | None) -> datetime | None:
    """Ensure datetime is timezone-aware (UTC)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def determine_date_key(
    scheduled_for: datetime,
    local_date: str | None,
) -> str:
    """
    Determine the date key for a completion record.
    
    Uses local_date if available (timezone-correct), otherwise falls back
    to UTC date from scheduled_for for backward compatibility.
    """
    if local_date:
        return local_date
    return scheduled_for.strftime("%Y-%m-%d")


def process_completion_row(
    task_id: str,
    scheduled_for: datetime | None,
    record_status: str,
    skip_reason: str | None,
    local_date: str | None,
    today_str: str,
    data: CompletionDataMaps,
) -> None:
    """
    Process a single completion row and update data maps.
    
    Mutates the data object in place with completion/skip tracking.
    """
    if not scheduled_for:
        return
    
    # Ensure timezone-aware
    scheduled_for = ensure_timezone_aware(scheduled_for)
    date_key = determine_date_key(scheduled_for, local_date)
    
    if record_status == "completed":
        _process_completion(task_id, scheduled_for, date_key, today_str, data)
    else:
        _process_skip(task_id, scheduled_for, skip_reason, date_key, today_str, data)


def _process_completion(
    task_id: str,
    scheduled_for: datetime,
    date_key: str,
    today_str: str,
    data: CompletionDataMaps,
) -> None:
    """Process a completion record."""
    # Track completions by date
    if task_id not in data.completions_by_date_map:
        data.completions_by_date_map[task_id] = {}
    if date_key not in data.completions_by_date_map[task_id]:
        data.completions_by_date_map[task_id][date_key] = []
    data.completions_by_date_map[task_id][date_key].append(scheduled_for.isoformat())
    
    # Track today-specific counts
    if date_key == today_str:
        data.completions_today_count[task_id] = data.completions_today_count.get(task_id, 0) + 1
        if task_id not in data.completions_today_times:
            data.completions_today_times[task_id] = []
        data.completions_today_times[task_id].append(scheduled_for.isoformat())


def _process_skip(
    task_id: str,
    scheduled_for: datetime,
    skip_reason: str | None,
    date_key: str,
    today_str: str,
    data: CompletionDataMaps,
) -> None:
    """Process a skip record."""
    # Track skips by date
    if task_id not in data.skips_by_date_map:
        data.skips_by_date_map[task_id] = {}
    if date_key not in data.skips_by_date_map[task_id]:
        data.skips_by_date_map[task_id][date_key] = []
    data.skips_by_date_map[task_id][date_key].append(scheduled_for.isoformat())
    
    # Track skip reasons by date
    if task_id not in data.skip_reasons_by_date_map:
        data.skip_reasons_by_date_map[task_id] = {}
    data.skip_reasons_by_date_map[task_id][date_key] = skip_reason
    
    # Track today-specific counts
    if date_key == today_str:
        data.skips_today_count[task_id] = data.skips_today_count.get(task_id, 0) + 1
        if task_id not in data.skips_today_times:
            data.skips_today_times[task_id] = []
        data.skips_today_times[task_id].append(scheduled_for.isoformat())
        data.skip_reason_today_map[task_id] = skip_reason


def process_all_completion_rows(
    rows: list[tuple],
    today_str: str,
) -> CompletionDataMaps:
    """
    Process all completion rows into tracking data structures.
    
    Args:
        rows: List of tuples (task_id, scheduled_for, status, skip_reason, local_date)
        today_str: Today's date as YYYY-MM-DD string
    
    Returns:
        CompletionDataMaps with all processed data
    """
    data = CompletionDataMaps()
    
    for row in rows:
        task_id = row[0]
        scheduled_for = row[1]
        record_status = row[2]
        skip_reason = row[3]
        local_date = row[4] if len(row) > 4 else None
        
        process_completion_row(
            task_id=task_id,
            scheduled_for=scheduled_for,
            record_status=record_status,
            skip_reason=skip_reason,
            local_date=local_date,
            today_str=today_str,
            data=data,
        )
    
    return data


def count_task_statuses(tasks: list) -> tuple[int, int]:
    """
    Count pending and completed tasks.
    
    Args:
        tasks: List of task objects with .status attribute
    
    Returns:
        (pending_count, completed_count)
    """
    pending_count = sum(1 for t in tasks if t.status == "pending")
    completed_count = sum(1 for t in tasks if t.status == "completed")
    return pending_count, completed_count
