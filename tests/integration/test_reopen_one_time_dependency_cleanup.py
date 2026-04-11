"""One-time reopen must remove TaskCompletion rows so dependency rules re-apply."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_reopen_chain_after_complete_chain_restores_hard_blocking(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    """Complete A→B→C via chain, reopen each one-time task, then B is blocked by A again."""
    a = await client.post("/tasks", json={"title": "Reopen A"}, headers=auth_headers)
    b = await client.post("/tasks", json={"title": "Reopen B"}, headers=auth_headers)
    c = await client.post("/tasks", json={"title": "Reopen C"}, headers=auth_headers)
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

    chain = await client.post(
        f"/tasks/{cid}/complete-chain", json={}, headers=auth_headers
    )
    assert chain.status_code == 200

    for tid in (cid, bid, aid):
        r = await client.post(f"/tasks/{tid}/reopen", json={}, headers=auth_headers)
        assert r.status_code == 200

    st = await client.get(f"/tasks/{cid}/dependency-status", headers=auth_headers)
    assert st.status_code == 200
    body = st.json()
    assert len(body["transitive_unmet_hard_prerequisites"]) == 2

    blocked = await client.post(f"/tasks/{bid}/complete", json={}, headers=auth_headers)
    assert blocked.status_code == 409
