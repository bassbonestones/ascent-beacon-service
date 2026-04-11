"""After skip A, skip C, complete B, reopen B+C: C should not list A as unmet (A still skipped)."""
import pytest
from httpx import AsyncClient


async def _skip_hard(client: AsyncClient, auth_headers: dict[str, str], tid: str, body: dict) -> None:
    sk = await client.post(f"/tasks/{tid}/skip", json=body, headers=auth_headers)
    assert sk.status_code == 200
    data = sk.json()
    if data.get("status") == "has_dependents":
        sk2 = await client.post(
            f"/tasks/{tid}/skip",
            json={**body, "confirm_proceed": True},
            headers=auth_headers,
        )
        assert sk2.status_code == 200, sk2.text


@pytest.mark.asyncio
async def test_reopen_b_and_c_after_skip_a_complete_b_only_b_prereq_for_c(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    a = await client.post("/tasks", json={"title": "R A"}, headers=auth_headers)
    b = await client.post("/tasks", json={"title": "R B"}, headers=auth_headers)
    c = await client.post("/tasks", json={"title": "R C"}, headers=auth_headers)
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

    await _skip_hard(client, auth_headers, aid, {"reason": "skip a"})
    await _skip_hard(client, auth_headers, cid, {"reason": "skip c"})

    co = await client.post(f"/tasks/{bid}/complete", json={}, headers=auth_headers)
    assert co.status_code == 200, co.text

    ro_c = await client.post(f"/tasks/{cid}/reopen", json={}, headers=auth_headers)
    assert ro_c.status_code == 200, ro_c.text
    ro_b = await client.post(f"/tasks/{bid}/reopen", json={}, headers=auth_headers)
    assert ro_b.status_code == 200, ro_b.text

    st = await client.get(f"/tasks/{cid}/dependency-status", headers=auth_headers)
    assert st.status_code == 200
    body = st.json()
    assert body["has_unmet_hard"] is True
    tids = {x["upstream_task"]["id"] for x in body["transitive_unmet_hard_prerequisites"]}
    assert aid not in tids, body["transitive_unmet_hard_prerequisites"]
    assert bid in tids

    co2 = await client.post(f"/tasks/{bid}/complete", json={}, headers=auth_headers)
    assert co2.status_code == 200, co2.text
