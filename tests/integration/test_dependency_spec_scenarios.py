"""
Phase 4i-6: Spec scenario traceability + gap-only integration tests.

Scenario matrix (see docs/specs/occurrence-dependencies-spec.md — Test Scenarios):

| # | Title                         | Existing coverage (primary) | Gap? |
|---|-------------------------------|-----------------------------|------|
| 1 | Simple chain A→B→C           | test_skip_chain_linear_order (skip); complete-chain 2-node | Yes — complete ordering |
| 2 | Count-based                   | TestCountBasedDependencies::test_requires_multiple_completions | No |
| 3 | WITHIN_WINDOW expiration      | TestWithinWindowScope::* | No |
| 4 | NEXT_OCCURRENCE consumption | partial via next_occurrence rules | Yes — consume then block |
| 5 | Skip cascade                  | TestSkip* in test_skip_dependencies.py | No |
| 6 | Hard override                 | TestDependencyOverride::* | No |
| 7 | Soft advisory                 | TestTaskListDependencySummary; mocked advisory | Yes — list + Skipped today |
| 8 | Cross-goal dependency         | deps in test_recurring_scenarios same goal only | Yes |
New tests: scenarios 1,4,7,8 + dependency-status topo.
"""
from __future__ import annotations

import pytest
from datetime import timedelta
from httpx import AsyncClient

from app.core.time import utc_now


@pytest.mark.asyncio
async def test_spec_scenario1_three_task_hard_complete_order(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Scenario 1: A→B→C hard; complete C only after B then A satisfied (direct blockers)."""
    a = await client.post("/tasks", json={"title": "S1 A"}, headers=auth_headers)
    b = await client.post("/tasks", json={"title": "S1 B"}, headers=auth_headers)
    c = await client.post("/tasks", json={"title": "S1 C"}, headers=auth_headers)
    aid, bid, cid = a.json()["id"], b.json()["id"], c.json()["id"]

    for up, down in ((aid, bid), (bid, cid)):
        r = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": up,
                "downstream_task_id": down,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        assert r.status_code == 201

    r409 = await client.post(
        f"/tasks/{cid}/complete", json={}, headers=auth_headers
    )
    assert r409.status_code == 409
    assert r409.json()["blockers"][0]["upstream_task"]["id"] == bid

    assert (
        await client.post(f"/tasks/{aid}/complete", json={}, headers=auth_headers)
    ).status_code == 200

    r409b = await client.post(
        f"/tasks/{cid}/complete", json={}, headers=auth_headers
    )
    assert r409b.status_code == 409
    assert r409b.json()["blockers"][0]["upstream_task"]["id"] == bid

    assert (
        await client.post(f"/tasks/{bid}/complete", json={}, headers=auth_headers)
    ).status_code == 200

    assert (
        await client.post(f"/tasks/{cid}/complete", json={}, headers=auth_headers)
    ).status_code == 200


@pytest.mark.asyncio
async def test_spec_scenario4_next_occurrence_consumption_blocks_second_downstream(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Scenario 4: one upstream completion consumed; second downstream complete needs new upstream."""
    now = utc_now().replace(minute=0, second=0, microsecond=0)
    t_gym = now.replace(hour=7, minute=0)
    t_meal1 = now.replace(hour=8, minute=0)
    t_meal2 = now.replace(hour=9, minute=0)

    gym = await client.post(
        "/tasks",
        json={
            "title": "S4 Gym",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": t_gym.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
        headers=auth_headers,
    )
    meal = await client.post(
        "/tasks",
        json={
            "title": "S4 Meal",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": t_meal1.isoformat(),
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
        headers=auth_headers,
    )
    gym_id, meal_id = gym.json()["id"], meal.json()["id"]

    dep = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": gym_id,
            "downstream_task_id": meal_id,
            "strength": "hard",
            "scope": "next_occurrence",
            "required_occurrence_count": 1,
        },
        headers=auth_headers,
    )
    assert dep.status_code == 201

    assert (
        await client.post(
            f"/tasks/{gym_id}/complete",
            json={"scheduled_for": t_gym.isoformat()},
            headers=auth_headers,
        )
    ).status_code == 200

    assert (
        await client.post(
            f"/tasks/{meal_id}/complete",
            json={"scheduled_for": t_meal1.isoformat()},
            headers=auth_headers,
        )
    ).status_code == 200

    blocked = await client.post(
        f"/tasks/{meal_id}/complete",
        json={"scheduled_for": t_meal2.isoformat()},
        headers=auth_headers,
    )
    assert blocked.status_code == 409

    assert (
        await client.post(
            f"/tasks/{gym_id}/complete",
            json={"scheduled_for": (t_gym + timedelta(hours=1)).isoformat()},
            headers=auth_headers,
        )
    ).status_code == 200

    assert (
        await client.post(
            f"/tasks/{meal_id}/complete",
            json={"scheduled_for": t_meal2.isoformat()},
            headers=auth_headers,
        )
    ).status_code == 200


@pytest.mark.asyncio
async def test_spec_scenario7_list_dependency_summary_skipped_upstream_advisory(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Scenario 7: soft dep; upstream skipped → list payload advisory mentions Skipped today."""
    day = "2031-03-15"
    iso = f"{day}T12:00:00+00:00"

    up = await client.post(
        "/tasks",
        json={
            "title": "S7 Up",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduled_at": iso,
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
        headers=auth_headers,
    )
    down = await client.post(
        "/tasks",
        json={"title": "S7 Down", "scheduled_at": iso},
        headers=auth_headers,
    )
    up_id, down_id = up.json()["id"], down.json()["id"]

    assert (
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": up_id,
                "downstream_task_id": down_id,
                "strength": "soft",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
    ).status_code == 201

    skip_resp = await client.post(
        f"/tasks/{up_id}/skip",
        json={"reason": "s7 skip", "local_date": day},
        headers=auth_headers,
    )
    assert skip_resp.status_code == 200

    list_resp = await client.get(
        f"/tasks?client_today={day}&include_dependency_summary=true&status=pending",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    row = next(t for t in list_resp.json()["tasks"] if t["id"] == down_id)
    adv = (row.get("dependency_summary") or {}).get("advisory_text") or ""
    assert "Usually follows" in adv
    assert "Skipped today" in adv


@pytest.mark.asyncio
async def test_spec_scenario8_cross_goal_hard_dependency(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    """Scenario 8: task in Goal 2 depends on task in Goal 1; completion works across goals."""
    g1 = await client.post(
        "/goals", json={"title": "S8 Goal One"}, headers=auth_headers
    )
    g2 = await client.post(
        "/goals", json={"title": "S8 Goal Two"}, headers=auth_headers
    )
    g1_id, g2_id = g1.json()["id"], g2.json()["id"]

    ta = await client.post(
        "/tasks",
        json={"goal_id": g1_id, "title": "S8 Task A"},
        headers=auth_headers,
    )
    tb = await client.post(
        "/tasks",
        json={"goal_id": g2_id, "title": "S8 Task B"},
        headers=auth_headers,
    )
    aid, bid = ta.json()["id"], tb.json()["id"]

    assert (
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": aid,
                "downstream_task_id": bid,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
    ).status_code == 201

    assert (
        await client.post(f"/tasks/{bid}/complete", json={}, headers=auth_headers)
    ).status_code == 409

    assert (
        await client.post(f"/tasks/{aid}/complete", json={}, headers=auth_headers)
    ).status_code == 200

    assert (
        await client.post(f"/tasks/{bid}/complete", json={}, headers=auth_headers)
    ).status_code == 200


@pytest.mark.asyncio
async def test_dependency_status_transitive_unmet_hard_prereqs_topo(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    """GET dependency-status lists full unmet hard chain in topo order for modals."""
    a = await client.post("/tasks", json={"title": "Topo A"}, headers=auth_headers)
    b = await client.post("/tasks", json={"title": "Topo B"}, headers=auth_headers)
    c = await client.post("/tasks", json={"title": "Topo C"}, headers=auth_headers)
    aid, bid, cid = a.json()["id"], b.json()["id"], c.json()["id"]
    for up, down in ((aid, bid), (bid, cid)):
        r = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": up,
                "downstream_task_id": down,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        assert r.status_code == 201

    st = await client.get(f"/tasks/{cid}/dependency-status", headers=auth_headers)
    assert st.status_code == 200
    body = st.json()
    trans = body["transitive_unmet_hard_prerequisites"]
    assert len(trans) == 2
    assert [x["upstream_task"]["title"] for x in trans] == ["Topo A", "Topo B"]
