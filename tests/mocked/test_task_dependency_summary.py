"""Unit tests for task_dependency_summary helpers (Phase 4i-5)."""
from datetime import date, datetime, time, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.dependency import DependencyBlocker, DependencyStatusResponse, TaskInfo
from app.services import intraday_occurrence_anchors as ioa
from app.services import task_dependency_summary as tds


class _RecurringTask:
    is_recurring = True
    scheduled_at: datetime | None = None
    scheduled_date: str | None = None


class _OneShotTask:
    is_recurring = False
    scheduled_at: datetime | None = None
    scheduled_date: str | None = None


def test_occurrence_recurring_with_naive_scheduled_at() -> None:
    t = _RecurringTask()
    t.scheduled_at = datetime(2026, 1, 1, 8, 15, 0)
    out = ioa._occurrence_scheduled_for(t, date(2026, 6, 1), None)
    assert out is not None
    assert out.date() == date(2026, 6, 1)
    assert out.hour == 8 and out.minute == 15


def test_occurrence_recurring_midnight_template_anchors_end_of_day() -> None:
    """Midnight slot would make completed_at < 00:00 exclude same-day upstream."""
    t = _RecurringTask()
    t.scheduled_at = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    out = ioa._occurrence_scheduled_for(t, date(2026, 6, 2), None)
    assert out is not None
    assert out.hour == 23 and out.minute == 59 and out.second == 59


def test_occurrence_recurring_no_scheduled_at() -> None:
    t = _RecurringTask()
    t.scheduled_at = None
    out = ioa._occurrence_scheduled_for(t, date(2026, 6, 2), None)
    assert out == datetime.combine(
        date(2026, 6, 2), time(23, 59, 59, 999999), tzinfo=timezone.utc
    )


def test_occurrence_one_time_wrong_day() -> None:
    t = _OneShotTask()
    t.scheduled_at = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
    assert ioa._occurrence_scheduled_for(t, date(2026, 6, 2), None) is None


def test_occurrence_one_time_same_day() -> None:
    t = _OneShotTask()
    t.scheduled_at = datetime(2026, 6, 3, 9, 0, tzinfo=timezone.utc)
    out = ioa._occurrence_scheduled_for(t, date(2026, 6, 3), None)
    assert out == t.scheduled_at


def test_occurrence_scheduled_date_match() -> None:
    t = _OneShotTask()
    t.scheduled_at = None
    t.scheduled_date = "2026-06-04"
    out = ioa._occurrence_scheduled_for(t, date(2026, 6, 4), None)
    assert out == datetime.combine(
        date(2026, 6, 4), time(23, 59, 59, 999999), tzinfo=timezone.utc
    )


def test_occurrence_scheduled_date_invalid() -> None:
    t = _OneShotTask()
    t.scheduled_date = "not-a-date"
    assert ioa._occurrence_scheduled_for(t, date(2026, 6, 4), None) is None


def test_occurrence_scheduled_date_mismatch() -> None:
    t = _OneShotTask()
    t.scheduled_date = "2026-06-05"
    assert ioa._occurrence_scheduled_for(t, date(2026, 6, 6), None) is None


def test_occurrence_anytime_fallback() -> None:
    t = _OneShotTask()
    t.scheduled_at = None
    t.scheduled_date = None
    out = ioa._occurrence_scheduled_for(t, date(2026, 6, 7), None)
    assert out == datetime.combine(
        date(2026, 6, 7), time(23, 59, 59, 999999), tzinfo=timezone.utc
    )


@pytest.mark.asyncio
async def test_build_task_dependency_summary_soft_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocker = DependencyBlocker(
        rule_id="r1",
        upstream_task=TaskInfo(id="u1", title="Up", is_recurring=False),
        strength="soft",
        scope="next_occurrence",
        required_count=1,
        completed_count=0,
        is_met=False,
    )
    status = DependencyStatusResponse(
        task_id="d1",
        dependencies=[blocker],
    )

    async def _fake_check(
        db: object,
        task_id: str,
        user_id: str,
        scheduled_for: datetime | None = None,
        local_date: str | None = None,
    ) -> DependencyStatusResponse:
        assert task_id == "d1"
        assert local_date == "2026-06-10"
        return status

    async def _fake_skipped(
        db: object,
        upstream_task_id: str,
        local_date_str: str,
    ) -> bool:
        assert upstream_task_id == "u1"
        return True

    monkeypatch.setattr(tds, "check_dependencies", _fake_check)
    monkeypatch.setattr(tds, "_upstream_skipped_on_local_date", _fake_skipped)

    class _Task:
        id = "d1"
        is_recurring = True
        scheduled_at = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        scheduled_date = None
        recurrence_rule = None

    db = AsyncMock()
    summary = await tds.build_task_dependency_summary(db, "user-1", _Task(), "2026-06-10")
    assert summary.has_unmet_soft is True
    assert summary.advisory_text and "Skipped today" in summary.advisory_text


@pytest.mark.asyncio
async def test_build_summaries_for_tasks_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _fake_ids(db: object, user_id: str) -> set[str]:
        return {"d1"}

    async def _fake_build_day(
        db: object,
        user_id: str,
        task: object,
        local_date_str: str,
        client_timezone: str | None,
    ) -> dict[str, object]:
        from app.schemas.tasks import TaskDependencySummary

        return {
            "": TaskDependencySummary(
                readiness_state="ready",
                has_unmet_hard=False,
                has_unmet_soft=False,
            )
        }

    monkeypatch.setattr(tds, "downstream_task_ids_with_rules", _fake_ids)
    monkeypatch.setattr(tds, "build_task_dependency_summaries_for_day", _fake_build_day)

    class _A:
        id = "d1"

    class _B:
        id = "x"

    db = AsyncMock()
    out = await tds.build_summaries_for_tasks(db, "u", [_A(), _B()], "2026-06-10")
    assert set(out.keys()) == {"d1"}


@pytest.mark.asyncio
async def test_build_task_dependency_summary_soft_not_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocker = DependencyBlocker(
        rule_id="r1",
        upstream_task=TaskInfo(id="u1", title="Up", is_recurring=False),
        strength="soft",
        scope="next_occurrence",
        required_count=1,
        completed_count=0,
        is_met=False,
    )
    status = DependencyStatusResponse(task_id="d1", dependencies=[blocker])

    async def _fake_check(
        db: object,
        task_id: str,
        user_id: str,
        scheduled_for: datetime | None = None,
        local_date: str | None = None,
    ) -> DependencyStatusResponse:
        return status

    async def _fake_skipped(
        db: object,
        upstream_task_id: str,
        local_date_str: str,
    ) -> bool:
        return False

    monkeypatch.setattr(tds, "check_dependencies", _fake_check)
    monkeypatch.setattr(tds, "_upstream_skipped_on_local_date", _fake_skipped)

    class _Task:
        id = "d1"
        is_recurring = False
        scheduled_at = datetime(2026, 6, 10, 9, 0, tzinfo=timezone.utc)
        scheduled_date = None
        recurrence_rule = None

    db = AsyncMock()
    summary = await tds.build_task_dependency_summary(db, "user-1", _Task(), "2026-06-10")
    assert summary.advisory_text and "Not completed yet" in summary.advisory_text


@pytest.mark.asyncio
async def test_build_task_dependency_summary_hard_no_advisory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    blocker = DependencyBlocker(
        rule_id="r1",
        upstream_task=TaskInfo(id="u1", title="Up", is_recurring=False),
        strength="hard",
        scope="next_occurrence",
        required_count=1,
        completed_count=0,
        is_met=False,
    )
    status = DependencyStatusResponse(task_id="d1", dependencies=[blocker])

    async def _fake_check(
        db: object,
        task_id: str,
        user_id: str,
        scheduled_for: datetime | None = None,
        local_date: str | None = None,
    ) -> DependencyStatusResponse:
        return status

    monkeypatch.setattr(tds, "check_dependencies", _fake_check)

    class _Task:
        id = "d1"
        is_recurring = True
        scheduled_at = datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)
        scheduled_date = None
        recurrence_rule = None

    db = AsyncMock()
    summary = await tds.build_task_dependency_summary(db, "user-1", _Task(), "2026-06-10")
    assert summary.advisory_text is None
    assert summary.has_unmet_hard is True


@pytest.mark.asyncio
async def test_upstream_skipped_on_local_date_true() -> None:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = "found-id"
    db.execute = AsyncMock(return_value=result)
    assert await tds._upstream_skipped_on_local_date(db, "t-up", "2026-06-10") is True


@pytest.mark.asyncio
async def test_upstream_skipped_on_local_date_false() -> None:
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    assert await tds._upstream_skipped_on_local_date(db, "t-up", "2026-06-10") is False


@pytest.mark.asyncio
async def test_downstream_task_ids_with_rules() -> None:
    db = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = [("a",), ("b",)]
    db.execute = AsyncMock(return_value=result)
    out = await tds.downstream_task_ids_with_rules(db, "user-1")
    assert out == {"a", "b"}

