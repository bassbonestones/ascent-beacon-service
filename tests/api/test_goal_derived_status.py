"""Integration tests for derived goal status (task tree)."""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_leaf_goal_completes_when_only_task_completed(client: AsyncClient):
    g = await client.post("/goals", json={"title": "Leaf"})
    assert g.status_code == 201
    gid = g.json()["id"]
    scheduled_at = datetime.now(timezone.utc).isoformat()
    t = await client.post(
        "/tasks",
        json={
            "goal_id": gid,
            "title": "Only",
            "duration_minutes": 30,
            "scheduled_at": scheduled_at,
        },
    )
    assert t.status_code == 201
    tid = t.json()["id"]
    c = await client.post(f"/tasks/{tid}/complete", json={})
    assert c.status_code == 200
    gr = await client.get(f"/goals/{gid}")
    assert gr.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_leaf_goal_in_progress_when_partial_tasks_done(client: AsyncClient):
    g = await client.post("/goals", json={"title": "Partial"})
    gid = g.json()["id"]
    scheduled_at = datetime.now(timezone.utc).isoformat()
    t1 = await client.post(
        "/tasks",
        json={
            "goal_id": gid,
            "title": "A",
            "duration_minutes": 10,
            "scheduled_at": scheduled_at,
        },
    )
    t2 = await client.post(
        "/tasks",
        json={
            "goal_id": gid,
            "title": "B",
            "duration_minutes": 10,
            "scheduled_at": scheduled_at,
        },
    )
    await client.post(f"/tasks/{t1.json()['id']}/complete", json={})
    gr = await client.get(f"/goals/{gid}")
    assert gr.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_parent_completes_when_subgoals_have_tasks_all_done(
    client: AsyncClient,
):
    p = await client.post("/goals", json={"title": "Root"})
    pid = p.json()["id"]
    c1 = await client.post(
        "/goals",
        json={"title": "Child1", "parent_goal_id": pid},
    )
    c2 = await client.post(
        "/goals",
        json={"title": "Child2", "parent_goal_id": pid},
    )
    id1, id2 = c1.json()["id"], c2.json()["id"]
    at = datetime.now(timezone.utc).isoformat()
    for gid in (id1, id2):
        tr = await client.post(
            "/tasks",
            json={
                "goal_id": gid,
                "title": "work",
                "duration_minutes": 15,
                "scheduled_at": at,
            },
        )
        assert tr.status_code == 201
        await client.post(f"/tasks/{tr.json()['id']}/complete", json={})

    pr = await client.get(f"/goals/{pid}")
    assert pr.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_parent_stays_in_progress_if_child_has_no_tasks(
    client: AsyncClient,
):
    p = await client.post("/goals", json={"title": "Root2"})
    pid = p.json()["id"]
    c1 = await client.post(
        "/goals",
        json={"title": "WithTask", "parent_goal_id": pid},
    )
    await client.post(
        "/goals",
        json={"title": "EmptyChild", "parent_goal_id": pid},
    )
    id1 = c1.json()["id"]
    at = datetime.now(timezone.utc).isoformat()
    tr = await client.post(
        "/tasks",
        json={
            "goal_id": id1,
            "title": "t",
            "duration_minutes": 5,
            "scheduled_at": at,
        },
    )
    await client.post(f"/tasks/{tr.json()['id']}/complete", json={})
    pr = await client.get(f"/goals/{pid}")
    assert pr.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_patch_goal_status_in_body_rejected(client: AsyncClient):
    g = await client.post("/goals", json={"title": "No manual"})
    gid = g.json()["id"]
    r = await client.patch(f"/goals/{gid}", json={"status": "completed"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_recurring_only_leaf_stays_not_started_until_occurrence(
    client: AsyncClient,
):
    g = await client.post("/goals", json={"title": "Habit only"})
    gid = g.json()["id"]
    at = datetime.now(timezone.utc).isoformat()
    t = await client.post(
        "/tasks",
        json={
            "goal_id": gid,
            "title": "Daily only",
            "duration_minutes": 0,
            "scheduled_at": at,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    assert t.status_code == 201
    gr = await client.get(f"/goals/{gid}")
    assert gr.json()["status"] == "not_started"


@pytest.mark.asyncio
async def test_recurring_only_leaf_in_progress_after_occurrence(
    client: AsyncClient,
):
    g = await client.post("/goals", json={"title": "Habit goal"})
    gid = g.json()["id"]
    at = datetime.now(timezone.utc).isoformat()
    t = await client.post(
        "/tasks",
        json={
            "goal_id": gid,
            "title": "Daily",
            "duration_minutes": 0,
            "scheduled_at": at,
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
        },
    )
    assert t.status_code == 201
    tid = t.json()["id"]
    c = await client.post(
        f"/tasks/{tid}/complete",
        json={"scheduled_for": at},
    )
    assert c.status_code == 200
    gr = await client.get(f"/goals/{gid}")
    assert gr.json()["status"] == "in_progress"


@pytest.mark.asyncio
async def test_nested_subgoal_task_satisfies_parent_completion(
    client: AsyncClient,
):
    root = await client.post("/goals", json={"title": "R"})
    rid = root.json()["id"]
    mid = (
        await client.post(
            "/goals",
            json={"title": "M", "parent_goal_id": rid},
        )
    ).json()["id"]
    leaf = (
        await client.post(
            "/goals",
            json={"title": "L", "parent_goal_id": mid},
        )
    ).json()["id"]
    at = datetime.now(timezone.utc).isoformat()
    tr = await client.post(
        "/tasks",
        json={
            "goal_id": leaf,
            "title": "deep",
            "duration_minutes": 5,
            "scheduled_at": at,
        },
    )
    await client.post(f"/tasks/{tr.json()['id']}/complete", json={})
    pr = await client.get(f"/goals/{rid}")
    assert pr.json()["status"] == "completed"
