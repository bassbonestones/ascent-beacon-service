"""Skipping upstream with keep-pending must allow completing downstream (hard dep)."""
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


async def _skip_one_time_with_hard_downstream(
    client: AsyncClient, auth_headers: dict[str, str], aid: str
) -> None:
    sk = await client.post(
        f"/tasks/{aid}/skip",
        json={"reason": "cannot do A"},
        headers=auth_headers,
    )
    assert sk.status_code == 200
    body = sk.json()
    if body.get("status") == "has_dependents":
        sk2 = await client.post(
            f"/tasks/{aid}/skip",
            json={"reason": "cannot do A", "confirm_proceed": True},
            headers=auth_headers,
        )
        assert sk2.status_code == 200, sk2.text
        assert sk2.json()["status"] == "skipped"
    else:
        assert body["status"] == "skipped"


@pytest.mark.asyncio
async def test_one_time_skip_upstream_then_complete_downstream(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    a = await client.post("/tasks", json={"title": "Up OT"}, headers=auth_headers)
    b = await client.post("/tasks", json={"title": "Down OT"}, headers=auth_headers)
    aid, bid = a.json()["id"], b.json()["id"]
    dep = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": aid,
            "downstream_task_id": bid,
            "strength": "hard",
            "scope": "next_occurrence",
            "required_occurrence_count": 1,
        },
        headers=auth_headers,
    )
    assert dep.status_code == 201

    await _skip_one_time_with_hard_downstream(client, auth_headers, aid)

    st = await client.get(f"/tasks/{bid}/dependency-status", headers=auth_headers)
    assert st.status_code == 200
    assert st.json()["all_met"] is True

    co = await client.post(f"/tasks/{bid}/complete", json={}, headers=auth_headers)
    assert co.status_code == 200, co.text
    assert co.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_recurring_skip_upstream_then_complete_downstream_same_anchor(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    when = datetime(2026, 6, 15, 14, 30, 0, tzinfo=timezone.utc)
    when_s = when.isoformat()

    a = await client.post(
        "/tasks",
        json={
            "title": "Up Rec",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_behavior": "essential",
            "scheduling_mode": "date_only",
        },
        headers=auth_headers,
    )
    b = await client.post(
        "/tasks",
        json={
            "title": "Down Rec",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_behavior": "essential",
            "scheduling_mode": "date_only",
        },
        headers=auth_headers,
    )
    aid, bid = a.json()["id"], b.json()["id"]
    dep = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": aid,
            "downstream_task_id": bid,
            "strength": "hard",
            "scope": "next_occurrence",
            "required_occurrence_count": 1,
        },
        headers=auth_headers,
    )
    assert dep.status_code == 201

    sk = await client.post(
        f"/tasks/{aid}/skip",
        json={"scheduled_for": when_s, "local_date": "2026-06-15", "reason": "skip A"},
        headers=auth_headers,
    )
    assert sk.status_code == 200
    if sk.json().get("status") == "has_dependents":
        sk2 = await client.post(
            f"/tasks/{aid}/skip",
            json={
                "scheduled_for": when_s,
                "local_date": "2026-06-15",
                "reason": "skip A",
                "confirm_proceed": True,
            },
            headers=auth_headers,
        )
        assert sk2.status_code == 200, sk2.text

    st = await client.get(
        f"/tasks/{bid}/dependency-status",
        params={"scheduled_for": when_s},
        headers=auth_headers,
    )
    assert st.status_code == 200
    assert st.json()["all_met"] is True

    co = await client.post(
        f"/tasks/{bid}/complete",
        json={"scheduled_for": when_s, "local_date": "2026-06-15"},
        headers=auth_headers,
    )
    assert co.status_code == 200, co.text


@pytest.mark.asyncio
async def test_next_occurrence_counts_skip_by_scheduled_slot_not_wall_clock(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    """Skip uses scheduled_for slot; B later same wall day still sees A as satisfied."""
    morning = datetime(2026, 8, 1, 9, 0, 0, tzinfo=timezone.utc)
    midday = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)
    evening = datetime(2026, 8, 1, 21, 0, 0, tzinfo=timezone.utc)

    a = await client.post(
        "/tasks",
        json={
            "title": "Slot Up",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_behavior": "essential",
            "scheduling_mode": "date_only",
        },
        headers=auth_headers,
    )
    b = await client.post(
        "/tasks",
        json={
            "title": "Slot Down",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_behavior": "essential",
            "scheduling_mode": "date_only",
        },
        headers=auth_headers,
    )
    aid, bid = a.json()["id"], b.json()["id"]
    await client.post(
        "/dependencies",
        json={
            "upstream_task_id": aid,
            "downstream_task_id": bid,
            "strength": "hard",
            "scope": "next_occurrence",
            "required_occurrence_count": 1,
        },
        headers=auth_headers,
    )

    sk = await client.post(
        f"/tasks/{aid}/skip",
        json={
            "scheduled_for": midday.isoformat(),
            "local_date": "2026-08-01",
            "reason": "midday skip",
        },
        headers=auth_headers,
    )
    if sk.json().get("status") == "has_dependents":
        sk2 = await client.post(
            f"/tasks/{aid}/skip",
            json={
                "scheduled_for": midday.isoformat(),
                "local_date": "2026-08-01",
                "reason": "midday skip",
                "confirm_proceed": True,
            },
            headers=auth_headers,
        )
        assert sk2.status_code == 200, sk2.text

    st_morning = await client.get(
        f"/tasks/{bid}/dependency-status",
        params={"scheduled_for": morning.isoformat()},
        headers=auth_headers,
    )
    assert st_morning.json()["has_unmet_hard"] is True

    st_evening = await client.get(
        f"/tasks/{bid}/dependency-status",
        params={"scheduled_for": evening.isoformat()},
        headers=auth_headers,
    )
    assert st_evening.json()["has_unmet_hard"] is False
