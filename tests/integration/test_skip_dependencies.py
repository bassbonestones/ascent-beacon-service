"""
Integration tests for skip dependency impact and skip-chain (Phase 4i-4).
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestSkipSoftDownstream:
    """Skipping upstream with only soft downstream does not require confirmation."""

    async def test_skip_upstream_soft_downstream_no_preview(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post("/tasks", json={"title": "Soft Up"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "Soft Down"}, headers=auth_headers)
        uid, did = up.json()["id"], down.json()["id"]
        dep = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": did,
                "strength": "soft",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        assert dep.status_code == 201

        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        body = sk.json()
        assert body.get("status") == "skipped"
        assert "id" in body
        assert body["id"] == uid


@pytest.mark.asyncio
class TestSkipHardDownstream:
    """Hard downstream with required_count=1 triggers preview unless confirmed."""

    async def test_skip_hard_required_one_returns_has_dependents(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post("/tasks", json={"title": "Hard Up"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "Hard Down"}, headers=auth_headers)
        uid, did = up.json()["id"], down.json()["id"]
        dep = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": did,
                "strength": "hard",
                "scope": "next_occurrence",
                "required_occurrence_count": 1,
            },
            headers=auth_headers,
        )
        assert dep.status_code == 201

        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        body = sk.json()
        assert body["status"] == "has_dependents"
        assert len(body["affected_downstream"]) == 1
        assert body["affected_downstream"][0]["task_id"] == did
        assert body["affected_downstream"][0]["strength"] == "hard"

    async def test_skip_hard_confirm_proceed_persists(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post("/tasks", json={"title": "Hard Up 2"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "Hard Down 2"}, headers=auth_headers)
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

        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={"confirm_proceed": True, "reason": "ok"},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        body = sk.json()
        assert body["status"] == "skipped"
        assert body["id"] == uid

    async def test_skip_hard_required_two_no_preview_when_not_impossible(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Count>1 without impossibility heuristic does not block skip."""
        up = await client.post("/tasks", json={"title": "H Up 3"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "H Down 3"}, headers=auth_headers)
        uid, did = up.json()["id"], down.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": did,
                "strength": "hard",
                "scope": "within_window",
                "required_occurrence_count": 2,
                "validity_window_minutes": 10080,
            },
            headers=auth_headers,
        )

        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        assert sk.json()["status"] == "skipped"

    async def test_skip_hard_count_impossible_within_window_previews(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """required_count=2 in a 1-day window: skipping uses the only slot → preview."""
        up = await client.post("/tasks", json={"title": "Tight Up"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "Tight Down"}, headers=auth_headers)
        uid = up.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": down.json()["id"],
                "strength": "hard",
                "scope": "within_window",
                "required_occurrence_count": 2,
                "validity_window_minutes": 1440,
            },
            headers=auth_headers,
        )
        sk = await client.post(f"/tasks/{uid}/skip", json={}, headers=auth_headers)
        assert sk.status_code == 200
        assert sk.json()["status"] == "has_dependents"


@pytest.mark.asyncio
class TestSkipChain:
    """POST /tasks/{id}/skip-chain cascade."""

    async def test_skip_chain_rejects_without_cascade_flag(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        t = await client.post("/tasks", json={"title": "Solo"}, headers=auth_headers)
        tid = t.json()["id"]
        resp = await client.post(
            f"/tasks/{tid}/skip-chain",
            json={"cascade_skip": False},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    async def test_skip_chain_linear_order(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """A -> B -> C hard: chain returns three task responses in order root, B, C."""
        a = await client.post("/tasks", json={"title": "Chain A"}, headers=auth_headers)
        b = await client.post("/tasks", json={"title": "Chain B"}, headers=auth_headers)
        c = await client.post("/tasks", json={"title": "Chain C"}, headers=auth_headers)
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

        resp = await client.post(
            f"/tasks/{aid}/skip-chain",
            json={"cascade_skip": True, "reason": "vacation"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 3
        assert [r["id"] for r in rows] == [aid, bid, cid]
        assert all(r["status"] == "skipped" for r in rows)

    async def test_skip_chain_diamond_order(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """A -> B, A -> C, B -> D, C -> D: topo order has B,C before D."""
        a = await client.post("/tasks", json={"title": "D A"}, headers=auth_headers)
        b = await client.post("/tasks", json={"title": "D B"}, headers=auth_headers)
        c = await client.post("/tasks", json={"title": "D C"}, headers=auth_headers)
        d = await client.post("/tasks", json={"title": "D D"}, headers=auth_headers)
        aid, bid, cid, did = (
            a.json()["id"],
            b.json()["id"],
            c.json()["id"],
            d.json()["id"],
        )
        for pair in ((aid, bid), (aid, cid), (bid, did), (cid, did)):
            r = await client.post(
                "/dependencies",
                json={
                    "upstream_task_id": pair[0],
                    "downstream_task_id": pair[1],
                    "strength": "hard",
                    "scope": "next_occurrence",
                },
                headers=auth_headers,
            )
            assert r.status_code == 201

        resp = await client.post(
            f"/tasks/{aid}/skip-chain",
            json={"cascade_skip": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()]
        assert ids[0] == aid
        assert set(ids[1:3]) == {bid, cid}
        assert ids[3] == did

    async def test_skip_chain_single_task_no_dependents(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        t = await client.post("/tasks", json={"title": "Lonely"}, headers=auth_headers)
        tid = t.json()["id"]
        resp = await client.post(
            f"/tasks/{tid}/skip-chain",
            json={"cascade_skip": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1


@pytest.mark.asyncio
class TestSkipRecurring:
    """Recurring skip with scheduled_for."""

    async def test_recurring_skip_hard_preview(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post(
            "/tasks",
            json={
                "title": "Rec Up",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "recurrence_behavior": "essential",
                "scheduling_mode": "date_only",
            },
            headers=auth_headers,
        )
        assert up.status_code == 201
        down = await client.post("/tasks", json={"title": "Rec Down"}, headers=auth_headers)
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
        when = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={"scheduled_for": when.isoformat()},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        assert sk.json()["status"] == "has_dependents"

    async def test_recurring_skip_confirm(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post(
            "/tasks",
            json={
                "title": "Rec Up 2",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "recurrence_behavior": "essential",
                "scheduling_mode": "date_only",
            },
            headers=auth_headers,
        )
        down = await client.post("/tasks", json={"title": "Rec Down 2"}, headers=auth_headers)
        uid = up.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": down.json()["id"],
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        when = datetime(2026, 4, 11, 9, 0, 0, tzinfo=timezone.utc)
        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={"confirm_proceed": True, "scheduled_for": when.isoformat()},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        assert sk.json()["skipped_for_today"] is True


@pytest.mark.asyncio
class TestSkipMixedRules:
    """Soft + hard on same upstream: hard wins."""

    async def test_soft_and_hard_downstream_previews_for_hard(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post("/tasks", json={"title": "Mix Up"}, headers=auth_headers)
        sdown = await client.post("/tasks", json={"title": "Mix Soft"}, headers=auth_headers)
        hdown = await client.post("/tasks", json={"title": "Mix Hard"}, headers=auth_headers)
        uid, sid, hid = up.json()["id"], sdown.json()["id"], hdown.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": sid,
                "strength": "soft",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": hid,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )

        sk = await client.post(f"/tasks/{uid}/skip", json={}, headers=auth_headers)
        assert sk.status_code == 200
        body = sk.json()
        assert body["status"] == "has_dependents"
        affected_ids = {x["task_id"] for x in body["affected_downstream"]}
        assert hid in affected_ids
        assert sid not in affected_ids


@pytest.mark.asyncio
class TestSkipPreviewShape:
    """Response shape checks."""

    async def test_preview_weekly_downstream_affected_occurrences(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Weekly recurring downstream uses affected_occurrences estimate of 1."""
        up = await client.post("/tasks", json={"title": "Wk Up"}, headers=auth_headers)
        down = await client.post(
            "/tasks",
            json={
                "title": "Wk Down",
                "is_recurring": True,
                "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO",
                "recurrence_behavior": "essential",
                "scheduling_mode": "date_only",
            },
            headers=auth_headers,
        )
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
        occ = sk.json()["affected_downstream"][0]["affected_occurrences"]
        assert occ == 1

    async def test_preview_contains_rule_and_occurrence_estimate(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post(
            "/tasks",
            json={
                "title": "Shape Up",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "recurrence_behavior": "essential",
                "scheduling_mode": "date_only",
            },
            headers=auth_headers,
        )
        down = await client.post(
            "/tasks",
            json={
                "title": "Shape Down",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "recurrence_behavior": "essential",
                "scheduling_mode": "date_only",
            },
            headers=auth_headers,
        )
        uid, did = up.json()["id"], down.json()["id"]
        dep = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": did,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        rid = dep.json()["id"]

        sk = await client.post(f"/tasks/{uid}/skip", json={}, headers=auth_headers)
        row = sk.json()["affected_downstream"][0]
        assert row["rule_id"] == rid
        assert row["affected_occurrences"] >= 1


@pytest.mark.asyncio
class TestSkipExtra:
    """Additional coverage for reasons and flags."""

    async def test_confirm_proceed_false_explicit_still_previews(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post("/tasks", json={"title": "E1"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "E2"}, headers=auth_headers)
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
        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={"confirm_proceed": False},
            headers=auth_headers,
        )
        assert sk.json()["status"] == "has_dependents"

    async def test_skip_reason_on_confirm(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post("/tasks", json={"title": "E3"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "E4"}, headers=auth_headers)
        uid = up.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": down.json()["id"],
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={"confirm_proceed": True, "reason": "rain"},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        assert sk.json()["skip_reason"] == "rain"

    async def test_skip_chain_reason_on_responses(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        a = await client.post("/tasks", json={"title": "R1"}, headers=auth_headers)
        b = await client.post("/tasks", json={"title": "R2"}, headers=auth_headers)
        aid, bid = a.json()["id"], b.json()["id"]
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
        resp = await client.post(
            f"/tasks/{aid}/skip-chain",
            json={"cascade_skip": True, "reason": "sick"},
            headers=auth_headers,
        )
        for row in resp.json():
            assert row["skip_reason"] == "sick"
