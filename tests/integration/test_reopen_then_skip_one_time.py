"""One-time task: reopen must leave row pending so POST /skip succeeds."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_reopen_skipped_one_time_then_skip_ok(
    client: AsyncClient, auth_headers: dict[str, str],
) -> None:
    r = await client.post("/tasks", json={"title": "Skip after reopen"}, headers=auth_headers)
    assert r.status_code == 201
    tid = r.json()["id"]

    sk = await client.post(
        f"/tasks/{tid}/skip",
        json={"reason": "not today"},
        headers=auth_headers,
    )
    assert sk.status_code == 200
    assert sk.json()["status"] == "skipped"

    reopen = await client.post(f"/tasks/{tid}/reopen", json={}, headers=auth_headers)
    assert reopen.status_code == 200
    assert reopen.json()["status"] == "pending"

    sk2 = await client.post(
        f"/tasks/{tid}/skip",
        json={"reason": "again"},
        headers=auth_headers,
    )
    assert sk2.status_code == 200, sk2.text
    assert sk2.json()["status"] == "skipped"
