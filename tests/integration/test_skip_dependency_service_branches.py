"""
Branch coverage for skip_dependency_service (backend floor ≥97.01%).
"""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.models.dependency import DependencyRule


@pytest.mark.asyncio
async def test_skip_makes_soft_rule_returns_false(db_session) -> None:
    """skip_makes_hard_rule_impossible is False for soft strength."""
    from app.services.skip_dependency_service import skip_makes_hard_rule_impossible

    rule = Mock()
    rule.strength = "soft"
    anchor = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    assert await skip_makes_hard_rule_impossible(db_session, rule, anchor) is False


@pytest.mark.asyncio
async def test_skip_makes_hard_required_one_returns_false(db_session) -> None:
    """skip_makes_hard_rule_impossible is False when required_count <= 1."""
    from app.services.skip_dependency_service import skip_makes_hard_rule_impossible

    rule = Mock()
    rule.strength = "hard"
    rule.required_occurrence_count = 1
    anchor = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    assert await skip_makes_hard_rule_impossible(db_session, rule, anchor) is False


@pytest.mark.asyncio
async def test_skip_makes_all_occurrences_returns_false(db_session) -> None:
    """all_occurrences scope skips impossibility heuristic (always False)."""
    from app.services import skip_dependency_service as sds
    from app.services.skip_dependency_service import skip_makes_hard_rule_impossible

    rule = Mock()
    rule.strength = "hard"
    rule.required_occurrence_count = 3
    rule.scope = "all_occurrences"

    anchor = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    with patch.object(sds, "_count_qualifying_completions", new_callable=AsyncMock, return_value=1):
        assert await skip_makes_hard_rule_impossible(db_session, rule, anchor) is False


@pytest.mark.asyncio
async def test_skip_makes_still_needed_zero_returns_false(db_session) -> None:
    """When qualifying count meets required, impossibility is False."""
    from app.services import skip_dependency_service as sds
    from app.services.skip_dependency_service import skip_makes_hard_rule_impossible

    rule = Mock()
    rule.strength = "hard"
    rule.required_occurrence_count = 2
    rule.scope = "within_window"

    anchor = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    with patch.object(sds, "_count_qualifying_completions", new_callable=AsyncMock, return_value=2):
        assert await skip_makes_hard_rule_impossible(db_session, rule, anchor) is False


@pytest.mark.asyncio
async def test_skip_makes_unknown_scope_returns_false(db_session) -> None:
    """Unrecognized scope hits else branch and returns False."""
    from app.services import skip_dependency_service as sds
    from app.services.skip_dependency_service import skip_makes_hard_rule_impossible

    rule = Mock()
    rule.strength = "hard"
    rule.required_occurrence_count = 2
    rule.scope = "invalid_scope"  # type: ignore[assignment]

    anchor = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    with patch.object(sds, "_count_qualifying_completions", new_callable=AsyncMock, return_value=1):
        assert await skip_makes_hard_rule_impossible(db_session, rule, anchor) is False


@pytest.mark.asyncio
async def test_skip_makes_next_occurrence_window(db_session) -> None:
    """next_occurrence branch uses 30-day lookback window."""
    from app.services import skip_dependency_service as sds
    from app.services.skip_dependency_service import skip_makes_hard_rule_impossible

    rule = Mock()
    rule.strength = "hard"
    rule.required_occurrence_count = 2
    rule.scope = "next_occurrence"
    rule.upstream_task_id = "u1"

    anchor = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    with patch.object(sds, "_count_qualifying_completions", new_callable=AsyncMock, return_value=1):
        with patch.object(sds, "_max_slots_in_window", new_callable=AsyncMock, return_value=5):
            with patch.object(sds, "_count_upstream_actions_in_window", new_callable=AsyncMock, return_value=1):
                result = await skip_makes_hard_rule_impossible(db_session, rule, anchor)
    assert result is False


@pytest.mark.asyncio
async def test_get_transitive_raises_when_chain_exceeds_max_depth(
    client: AsyncClient, auth_headers: dict[str, str], db_session,
) -> None:
    """BFS aborts when reachable hard dependents exceed MAX_CHAIN_DEPTH."""
    from app.services import skip_dependency_service as sds
    from app.services.skip_dependency_service import get_transitive_hard_dependents_toposort

    ids: list[str] = []
    for label in ("D0", "D1", "D2"):
        r = await client.post("/tasks", json={"title": label}, headers=auth_headers)
        assert r.status_code == 201
        ids.append(r.json()["id"])
    u0, u1, u2 = ids[0], ids[1], ids[2]
    user_id = (await client.get(f"/tasks/{u0}", headers=auth_headers)).json()["user_id"]

    for up, down in ((u0, u1), (u1, u2)):
        dep = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": up,
                "downstream_task_id": down,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        assert dep.status_code == 201

    with patch.object(sds, "MAX_CHAIN_DEPTH", 1):
        with pytest.raises(ValueError, match="exceeds maximum depth"):
            await get_transitive_hard_dependents_toposort(db_session, u0, user_id)


@pytest.mark.asyncio
async def test_get_transitive_raises_on_cycle(
    client: AsyncClient, auth_headers: dict[str, str], db_session,
) -> None:
    """Cycle among reachable nodes (B↔C) breaks topological ordering."""
    from app.services.skip_dependency_service import get_transitive_hard_dependents_toposort

    a = await client.post("/tasks", json={"title": "Root A"}, headers=auth_headers)
    b = await client.post("/tasks", json={"title": "Node B"}, headers=auth_headers)
    c = await client.post("/tasks", json={"title": "Node C"}, headers=auth_headers)
    assert a.status_code == b.status_code == c.status_code == 201
    aid, bid, cid = a.json()["id"], b.json()["id"], c.json()["id"]
    user_id = a.json()["user_id"]

    r1 = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": aid,
            "downstream_task_id": bid,
            "strength": "hard",
            "scope": "next_occurrence",
        },
        headers=auth_headers,
    )
    r2 = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": bid,
            "downstream_task_id": cid,
            "strength": "hard",
            "scope": "next_occurrence",
        },
        headers=auth_headers,
    )
    assert r1.status_code == 201 and r2.status_code == 201

    dep_cb = DependencyRule(
        user_id=user_id,
        upstream_task_id=cid,
        downstream_task_id=bid,
        strength="hard",
        scope="next_occurrence",
        required_occurrence_count=1,
        validity_window_minutes=None,
    )
    db_session.add(dep_cb)
    await db_session.commit()

    with pytest.raises(ValueError, match="Cycle detected"):
        await get_transitive_hard_dependents_toposort(db_session, aid, user_id)


@pytest.mark.asyncio
async def test_preview_monthly_downstream_occurrence_estimate(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    """Non-daily/non-weekly recurring downstream uses default affected_occurrences."""
    up = await client.post("/tasks", json={"title": "Mth Up"}, headers=auth_headers)
    down = await client.post(
        "/tasks",
        json={
            "title": "Mth Down",
            "is_recurring": True,
            "recurrence_rule": "FREQ=MONTHLY;BYMONTHDAY=1",
            "recurrence_behavior": "essential",
            "scheduling_mode": "date_only",
        },
        headers=auth_headers,
    )
    assert up.status_code == 201 and down.status_code == 201
    uid, did = up.json()["id"], down.json()["id"]
    await client.post(
        "/dependencies",
        json={
            "upstream_task_id": uid,
            "downstream_task_id": did,
            "strength": "hard",
            "scope": "next_occurrence",
        },
        headers=auth_headers,
    )
    sk = await client.post(f"/tasks/{uid}/skip", json={}, headers=auth_headers)
    assert sk.status_code == 200
    row = sk.json()["affected_downstream"][0]
    assert row["affected_occurrences"] == 1


@pytest.mark.asyncio
async def test_within_window_bounds_missing_upstream_uses_default_window(
    db_session,
) -> None:
    """If upstream task row is missing, default validity is 1440 minutes."""
    from app.services.skip_dependency_service import _within_window_bounds

    rule = Mock()
    rule.validity_window_minutes = None
    rule.upstream_task_id = str(uuid4())
    anchor = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    window_start, window_end = await _within_window_bounds(db_session, rule, anchor)
    assert window_end == anchor
    assert (anchor - window_start) == timedelta(minutes=1440)


@pytest.mark.asyncio
async def test_within_window_bounds_null_validity_loads_upstream(
    client: AsyncClient, auth_headers: dict[str, str], db_session,
) -> None:
    """When validity_window_minutes is NULL, upstream recurrence supplies the window."""
    from app.services.skip_dependency_service import _within_window_bounds

    up = await client.post(
        "/tasks",
        json={
            "title": "NullVal Up",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_behavior": "essential",
            "scheduling_mode": "date_only",
        },
        headers=auth_headers,
    )
    down = await client.post("/tasks", json={"title": "NullVal Down"}, headers=auth_headers)
    uid, did = up.json()["id"], down.json()["id"]
    dep_resp = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": uid,
            "downstream_task_id": did,
            "strength": "hard",
            "scope": "within_window",
            "required_occurrence_count": 1,
            "validity_window_minutes": 2880,
        },
        headers=auth_headers,
    )
    assert dep_resp.status_code == 201
    rule_id = dep_resp.json()["id"]

    await db_session.execute(
        update(DependencyRule)
        .where(DependencyRule.id == rule_id)
        .values(validity_window_minutes=None)
    )
    await db_session.commit()

    stmt = select(DependencyRule).where(DependencyRule.id == rule_id)
    result = await db_session.execute(stmt)
    rule = result.scalar_one()
    anchor = datetime(2026, 4, 10, 15, 0, 0, tzinfo=timezone.utc)
    window_start, window_end = await _within_window_bounds(db_session, rule, anchor)
    assert window_end == anchor
    assert window_start < anchor
    assert (anchor - window_start) >= timedelta(minutes=1439)


@pytest.mark.asyncio
async def test_max_slots_recurring_upstream_in_window(
    client: AsyncClient, auth_headers: dict[str, str], db_session,
) -> None:
    """_max_slots_in_window uses recurrence interval for recurring upstream."""
    from app.services.skip_dependency_service import _max_slots_in_window

    up = await client.post(
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
    down = await client.post("/tasks", json={"title": "Slot Down"}, headers=auth_headers)
    uid, did = up.json()["id"], down.json()["id"]
    dep_resp = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": uid,
            "downstream_task_id": did,
            "strength": "hard",
            "scope": "within_window",
            "required_occurrence_count": 1,
            "validity_window_minutes": 4320,
        },
        headers=auth_headers,
    )
    assert dep_resp.status_code == 201
    stmt = select(DependencyRule).where(DependencyRule.id == dep_resp.json()["id"])
    rule = (await db_session.execute(stmt)).scalar_one()
    ws = datetime(2026, 4, 9, 0, 0, 0, tzinfo=timezone.utc)
    we = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
    slots = await _max_slots_in_window(db_session, rule, ws, we)
    assert slots >= 1
