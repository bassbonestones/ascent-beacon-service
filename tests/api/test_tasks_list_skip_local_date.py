"""Regression: list_tasks must count recurring skips when scheduled_for is null."""

from datetime import date

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_tasks_recurring_skip_with_only_local_date_sets_skipped_for_today(
    client: AsyncClient,
) -> None:
    today = date.today().strftime("%Y-%m-%d")
    r = await client.post(
        "/tasks",
        json={
            "title": "Rec skip local date only",
            "is_recurring": True,
            "recurrence_rule": "FREQ=DAILY",
            "recurrence_behavior": "essential",
        },
    )
    assert r.status_code == 201, r.text
    tid = r.json()["id"]

    sk = await client.post(
        f"/tasks/{tid}/skip",
        json={"reason": "test", "local_date": today},
    )
    assert sk.status_code == 200, sk.text

    lst = await client.get(
        "/tasks",
        params={"include_completed": "true", "client_today": today},
    )
    assert lst.status_code == 200, lst.text
    row = next(t for t in lst.json()["tasks"] if t["id"] == tid)
    assert row["skipped_for_today"] is True
    assert row["skips_today"] >= 1
    assert today in row["skips_by_date"]
