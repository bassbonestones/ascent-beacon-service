"""Chain A→B→C: skip A and C, then B must still complete (A skip satisfies B→A)."""
import pytest
from httpx import AsyncClient


async def _skip_with_hard_preview(
    client: AsyncClient, auth_headers: dict[str, str], task_id: str, body: dict
) -> None:
    sk = await client.post(
        f"/tasks/{task_id}/skip",
        json=body,
        headers=auth_headers,
    )
    assert sk.status_code == 200
    data = sk.json()
    if data.get("status") == "has_dependents":
        sk2 = await client.post(
            f"/tasks/{task_id}/skip",
            json={**body, "confirm_proceed": True},
            headers=auth_headers,
        )
        assert sk2.status_code == 200, sk2.text


@pytest.mark.asyncio
async def test_skip_a_skip_c_one_time_then_complete_b(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
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
                "required_occurrence_count": 1,
            },
            headers=auth_headers,
        )
        assert r.status_code == 201

    await _skip_with_hard_preview(
        client, auth_headers, aid, {"reason": "skip A"},
    )
    await _skip_with_hard_preview(
        client, auth_headers, cid, {"reason": "skip C"},
    )

    st = await client.get(f"/tasks/{bid}/dependency-status", headers=auth_headers)
    assert st.status_code == 200
    body = st.json()
    assert body["has_unmet_hard"] is False, body
    assert body["all_met"] is True, body

    co = await client.post(f"/tasks/{bid}/complete", json={}, headers=auth_headers)
    assert co.status_code == 200, co.text
    assert co.json()["status"] == "completed"
