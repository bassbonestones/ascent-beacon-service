"""
Integration tests for dependency completion (Phase 4i-2).

Tests the complete endpoint's dependency checking, the complete-chain
endpoint, and the dependency-status endpoint.
"""
import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient

from app.core.time import utc_now


@pytest.mark.asyncio
class TestDependencyBlocking:
    """Test that hard dependencies block completion."""

    async def test_all_occurrences_daily_uses_rule_b_calendar_periods(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Always-required-first (all_occurrences) still aligns periods for daily tasks."""
        day1_eod = datetime(2026, 6, 10, 23, 59, 59, tzinfo=timezone.utc)
        day2_morning = datetime(2026, 6, 11, 9, 0, 0, tzinfo=timezone.utc)

        gym = await client.post(
            "/tasks",
            json={
                "title": "Gym all-occ",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "date_only",
                "recurrence_behavior": "essential",
            },
            headers=auth_headers,
        )
        assert gym.status_code == 201
        protein = await client.post(
            "/tasks",
            json={
                "title": "Protein all-occ",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "date_only",
                "recurrence_behavior": "essential",
            },
            headers=auth_headers,
        )
        assert protein.status_code == 201
        gid, pid = gym.json()["id"], protein.json()["id"]

        dep = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": gid,
                "downstream_task_id": pid,
                "strength": "hard",
                "scope": "all_occurrences",
                "required_occurrence_count": 1,
            },
            headers=auth_headers,
        )
        assert dep.status_code == 201

        cg = await client.post(
            f"/tasks/{gid}/complete",
            json={
                "scheduled_for": day1_eod.isoformat(),
                "local_date": "2026-06-10",
            },
            headers=auth_headers,
        )
        assert cg.status_code == 200, cg.text

        st = await client.get(
            f"/tasks/{pid}/dependency-status",
            params={
                "scheduled_for": day2_morning.isoformat(),
                "local_date": "2026-06-11",
            },
            headers=auth_headers,
        )
        assert st.status_code == 200
        assert st.json()["has_unmet_hard"] is True

        cp = await client.post(
            f"/tasks/{pid}/complete",
            json={
                "scheduled_for": day2_morning.isoformat(),
                "local_date": "2026-06-11",
            },
            headers=auth_headers,
        )
        assert cp.status_code == 409, cp.text
    
    async def test_complete_blocked_by_hard_dependency(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Completing task with unmet hard dep returns 409."""
        # Create upstream task
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Upstream Task"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create downstream task
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Downstream Task"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create hard dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Try to complete downstream - should fail
        complete_resp = await client.post(
            f"/tasks/{downstream_id}/complete",
            json={},
            headers=auth_headers,
        )
        assert complete_resp.status_code == 409
        data = complete_resp.json()
        assert "blockers" in data
        assert len(data["blockers"]) == 1
        assert data["blockers"][0]["upstream_task"]["id"] == upstream_id
    
    async def test_complete_allowed_with_soft_dependency(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Task with unmet soft dep can still be completed."""
        # Create upstream task
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Soft Upstream"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create downstream task
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Soft Downstream"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create soft dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "soft",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Complete downstream - should succeed
        complete_resp = await client.post(
            f"/tasks/{downstream_id}/complete",
            json={},
            headers=auth_headers,
        )
        assert complete_resp.status_code == 200
    
    async def test_complete_allowed_when_deps_met(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Task with met hard dep can be completed."""
        # Create upstream task
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Met Upstream"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create downstream task
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Met Downstream"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create hard dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Complete upstream first
        complete_up = await client.post(
            f"/tasks/{upstream_id}/complete",
            json={},
            headers=auth_headers,
        )
        assert complete_up.status_code == 200
        
        # Complete downstream - should succeed now
        complete_down = await client.post(
            f"/tasks/{downstream_id}/complete",
            json={},
            headers=auth_headers,
        )
        assert complete_down.status_code == 200


@pytest.mark.asyncio
class TestDependencyOverride:
    """Test overriding unmet hard dependencies."""
    
    async def test_override_without_reason_fails(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Override without reason returns 400."""
        # Create upstream task
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Override Upstream"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create downstream task
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Override Downstream"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create hard dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Try override without reason
        complete_resp = await client.post(
            f"/tasks/{downstream_id}/complete",
            json={"override_confirm": True},
            headers=auth_headers,
        )
        assert complete_resp.status_code == 400
        assert "override_reason" in complete_resp.json()["detail"]
    
    async def test_override_with_reason_succeeds(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Override with reason completes task."""
        # Create upstream task
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Override2 Upstream"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create downstream task
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Override2 Downstream"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create hard dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Override with reason
        complete_resp = await client.post(
            f"/tasks/{downstream_id}/complete",
            json={
                "override_confirm": True,
                "override_reason": "Urgent deadline",
            },
            headers=auth_headers,
        )
        assert complete_resp.status_code == 200
        assert complete_resp.json()["status"] == "completed"
    
    async def test_override_with_recurring_upstream(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Override with recurring upstream creates resolution."""
        now = utc_now()
        scheduled_time = now.replace(hour=10, minute=0, second=0, microsecond=0)
        
        # Create recurring upstream
        upstream_resp = await client.post(
            "/tasks",
            json={
                "title": "Override3 Recurring Upstream",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduled_at": scheduled_time.isoformat(),
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
            },
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create downstream task
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Override3 Downstream"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create hard dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Override with reason (upstream not completed)
        complete_resp = await client.post(
            f"/tasks/{downstream_id}/complete",
            json={
                "override_confirm": True,
                "override_reason": "Emergency override",
                "scheduled_for": now.isoformat(),
            },
            headers=auth_headers,
        )
        assert complete_resp.status_code == 200
        assert complete_resp.json()["status"] == "completed"


@pytest.mark.asyncio
class TestDependencyStatusEndpoint:
    """Test GET /tasks/{id}/dependency-status endpoint."""
    
    async def test_dependency_status_with_blockers(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Get dependency status shows blockers."""
        # Create tasks
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Status Upstream"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Status Downstream"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Get dependency status
        status_resp = await client.get(
            f"/tasks/{downstream_id}/dependency-status",
            headers=auth_headers,
        )
        assert status_resp.status_code == 200
        data = status_resp.json()
        
        assert data["task_id"] == downstream_id
        assert data["has_unmet_hard"] is True
        assert data["all_met"] is False
        assert data["readiness_state"] == "blocked"
        assert len(data["dependencies"]) == 1
    
    async def test_dependency_status_no_deps(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Task with no deps shows ready state."""
        # Create task
        task_resp = await client.post(
            "/tasks",
            json={"title": "No Deps Task"},
            headers=auth_headers,
        )
        assert task_resp.status_code == 201
        task_id = task_resp.json()["id"]
        
        # Get dependency status
        status_resp = await client.get(
            f"/tasks/{task_id}/dependency-status",
            headers=auth_headers,
        )
        assert status_resp.status_code == 200
        data = status_resp.json()
        
        assert data["readiness_state"] == "ready"
        assert data["all_met"] is True
        assert len(data["dependencies"]) == 0


@pytest.mark.asyncio
class TestCompleteChainEndpoint:
    """Test POST /tasks/{id}/complete-chain endpoint."""
    
    async def test_complete_chain_single_prereq(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Complete chain with one prerequisite."""
        # Create upstream
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Chain Upstream"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create downstream
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Chain Downstream"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Complete chain
        chain_resp = await client.post(
            f"/tasks/{downstream_id}/complete-chain",
            json={},
            headers=auth_headers,
        )
        assert chain_resp.status_code == 200
        completed = chain_resp.json()
        
        # Should have completed both tasks
        assert len(completed) == 2
        # Upstream completed first
        assert completed[0]["id"] == upstream_id
        assert completed[0]["status"] == "completed"
        # Then downstream
        assert completed[1]["id"] == downstream_id
        assert completed[1]["status"] == "completed"
    
    async def test_complete_chain_already_met(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Complete chain when deps already met."""
        # Create upstream
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Chain2 Upstream"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Complete upstream first
        await client.post(
            f"/tasks/{upstream_id}/complete",
            json={},
            headers=auth_headers,
        )
        
        # Create downstream
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Chain2 Downstream"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Complete chain - should only complete downstream
        chain_resp = await client.post(
            f"/tasks/{downstream_id}/complete-chain",
            json={},
            headers=auth_headers,
        )
        assert chain_resp.status_code == 200
        completed = chain_resp.json()
        
        # Should have only the downstream task
        assert len(completed) == 1
        assert completed[0]["id"] == downstream_id
    
    async def test_complete_chain_with_recurring_upstream(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Complete chain with recurring prerequisite."""
        now = utc_now()
        scheduled_time = now.replace(hour=9, minute=0, second=0, microsecond=0)
        
        # Create recurring upstream
        upstream_resp = await client.post(
            "/tasks",
            json={
                "title": "Recurring Chain Upstream",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduled_at": scheduled_time.isoformat(),
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
            },
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create downstream
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Recurring Chain Downstream"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Complete chain
        chain_resp = await client.post(
            f"/tasks/{downstream_id}/complete-chain",
            json={"scheduled_for": now.isoformat()},
            headers=auth_headers,
        )
        assert chain_resp.status_code == 200
        completed = chain_resp.json()
        
        # Both should be completed
        assert len(completed) == 2
        # Recurring upstream stays "pending" but was marked completed_for_today
        assert completed[0]["id"] == upstream_id
        assert completed[0]["completed_for_today"] is True
        # Downstream fully completed
        assert completed[1]["id"] == downstream_id
        assert completed[1]["status"] == "completed"
    
    async def test_complete_chain_with_recurring_target(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Complete chain where target task is recurring."""
        now = utc_now()
        scheduled_time = now.replace(hour=11, minute=0, second=0, microsecond=0)
        
        # Create one-time upstream
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "One-time Chain Upstream"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create recurring downstream (target)
        downstream_resp = await client.post(
            "/tasks",
            json={
                "title": "Recurring Chain Target",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduled_at": scheduled_time.isoformat(),
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
            },
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Complete chain
        chain_resp = await client.post(
            f"/tasks/{downstream_id}/complete-chain",
            json={"scheduled_for": now.isoformat()},
            headers=auth_headers,
        )
        assert chain_resp.status_code == 200
        completed = chain_resp.json()
        
        # Both should be completed
        assert len(completed) == 2
        # Upstream fully completed
        assert completed[0]["id"] == upstream_id
        assert completed[0]["status"] == "completed"
        # Recurring target stays "pending" but was marked completed_for_today
        assert completed[1]["id"] == downstream_id
        assert completed[1]["completed_for_today"] is True
    
    async def test_complete_chain_target_already_completed(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Complete chain where non-recurring target is already completed."""
        # Create upstream
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Chain Upstream"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create non-recurring downstream (target)
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Chain Target"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Complete upstream first
        upstream_complete_resp = await client.post(
            f"/tasks/{upstream_id}/complete",
            json={},
            headers=auth_headers,
        )
        assert upstream_complete_resp.status_code == 200
        
        # Complete target task
        complete_resp = await client.post(
            f"/tasks/{downstream_id}/complete",
            json={},
            headers=auth_headers,
        )
        assert complete_resp.status_code == 200
        
        # Now complete chain - target is already completed
        chain_resp = await client.post(
            f"/tasks/{downstream_id}/complete-chain",
            json={},
            headers=auth_headers,
        )
        assert chain_resp.status_code == 200
        completed = chain_resp.json()
        
        # Should have upstream (added to list), target skipped via early return
        # The early return at line 446-447 is hit because target is already completed
        assert len(completed) == 1
        assert completed[0]["id"] == upstream_id


@pytest.mark.asyncio
class TestCountBasedDependencies:
    """Test count-based dependency completion."""
    
    async def test_requires_multiple_completions(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Task requiring 2 upstream completions stays blocked until met."""
        # Create recurring upstream with schedule
        scheduled_time = utc_now().replace(hour=8, minute=0, second=0)
        upstream_resp = await client.post(
            "/tasks",
            json={
                "title": "Water (count based)",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduled_at": scheduled_time.isoformat(),
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
            },
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create downstream
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Gym (needs 2 waters)"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create count-based dependency using all_occurrences scope (need 2)
        now = utc_now()
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
                "scope": "all_occurrences",
                "required_occurrence_count": 2,
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Complete upstream once
        await client.post(
            f"/tasks/{upstream_id}/complete",
            json={"scheduled_for": now.isoformat()},
            headers=auth_headers,
        )
        
        # Try complete downstream - should still be blocked (only 1 of 2)
        complete_resp = await client.post(
            f"/tasks/{downstream_id}/complete",
            json={"scheduled_for": now.isoformat()},
            headers=auth_headers,
        )
        assert complete_resp.status_code == 409
        data = complete_resp.json()
        assert data["blockers"][0]["completed_count"] == 1
        assert data["blockers"][0]["required_count"] == 2
        
        # Complete upstream again
        await client.post(
            f"/tasks/{upstream_id}/complete",
            json={"scheduled_for": (now + timedelta(hours=1)).isoformat()},
            headers=auth_headers,
        )
        
        # Now complete downstream - should succeed
        complete_resp2 = await client.post(
            f"/tasks/{downstream_id}/complete",
            json={"scheduled_for": now.isoformat()},
            headers=auth_headers,
        )
        assert complete_resp2.status_code == 200


@pytest.mark.asyncio
class TestWithinWindowScope:
    """Test within_window scope for dependencies."""
    
    async def test_within_window_scope_allows_recent(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Completion within window satisfies dependency."""
        now = utc_now()
        
        # Create upstream task
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Warmup Within Window"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create downstream task
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Workout Within Window"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create within_window dependency (60 minutes)
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
                "scope": "within_window",
                "validity_window_minutes": 60,
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Complete upstream
        await client.post(
            f"/tasks/{upstream_id}/complete",
            json={},
            headers=auth_headers,
        )
        
        # Complete downstream within window - should succeed
        complete_resp = await client.post(
            f"/tasks/{downstream_id}/complete",
            json={"scheduled_for": (now + timedelta(minutes=30)).isoformat()},
            headers=auth_headers,
        )
        assert complete_resp.status_code == 200
    
    async def test_within_window_uses_default_interval(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """within_window uses upstream's recurrence interval as default window."""
        now = utc_now()
        scheduled_time = now.replace(hour=8, minute=0, second=0, microsecond=0)
        
        # Create recurring upstream task (daily = 1440 minute default window)
        upstream_resp = await client.post(
            "/tasks",
            json={
                "title": "Daily Recurring Upstream",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduled_at": scheduled_time.isoformat(),
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
            },
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create downstream task
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Depends on Daily"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create within_window dependency WITHOUT explicit validity_window
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
                "scope": "within_window",
                # No validity_window_minutes - use default
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Complete upstream
        await client.post(
            f"/tasks/{upstream_id}/complete",
            json={"scheduled_for": now.isoformat()},
            headers=auth_headers,
        )
        
        # Complete downstream within default window - should succeed
        complete_resp = await client.post(
            f"/tasks/{downstream_id}/complete",
            json={"scheduled_for": (now + timedelta(hours=12)).isoformat()},
            headers=auth_headers,
        )
        assert complete_resp.status_code == 200


@pytest.mark.asyncio
class TestDependentsInfo:
    """Test checking downstream dependents for a task."""
    
    async def test_dependency_status_shows_dependents(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Dependency status shows downstream tasks that depend on this one."""
        # Create upstream
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Has Dependents"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        
        # Create downstream
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Depends On Upstream"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Check upstream's status - should show downstream as dependent
        status_resp = await client.get(
            f"/tasks/{upstream_id}/dependency-status",
            headers=auth_headers,
        )
        assert status_resp.status_code == 200
        data = status_resp.json()
        
        assert len(data["dependents"]) == 1
        assert data["dependents"][0]["downstream_task"]["id"] == downstream_id
        assert data["dependents"][0]["strength"] == "hard"


@pytest.mark.asyncio
class TestCheckHardDependentsFunction:
    """Test the check_hard_dependents helper function."""
    
    async def test_check_hard_dependents_returns_affected(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session
    ) -> None:
        """check_hard_dependents returns affected downstream tasks."""
        from app.services.dependency_service import check_hard_dependents
        
        # Create upstream
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Skip Upstream"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        user_id = upstream_resp.json()["user_id"]
        
        # Create downstream
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Affected Downstream"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create hard dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Check hard dependents
        affected = await check_hard_dependents(db_session, upstream_id, user_id)
        
        assert len(affected) == 1
        assert affected[0]["task_id"] == downstream_id
        assert affected[0]["strength"] == "hard"
    
    async def test_check_hard_dependents_ignores_soft(
        self, client: AsyncClient, auth_headers: dict[str, str], db_session
    ) -> None:
        """check_hard_dependents ignores soft dependencies."""
        from app.services.dependency_service import check_hard_dependents
        
        # Create upstream
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Soft Upstream"},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]
        user_id = upstream_resp.json()["user_id"]
        
        # Create downstream
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Soft Downstream"},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]
        
        # Create soft dependency
        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "soft",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201
        
        # Check hard dependents - should be empty
        affected = await check_hard_dependents(db_session, upstream_id, user_id)
        
        assert len(affected) == 0


@pytest.mark.asyncio
class TestTaskListDependencySummary:
    """Phase 4i-5: dependency_summary embedded on task list/detail."""

    async def test_list_tasks_include_dependency_summary(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        day = "2030-06-10"
        iso = f"{day}T15:00:00+00:00"
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "List Summary Up", "scheduled_at": iso},
            headers=auth_headers,
        )
        assert upstream_resp.status_code == 201
        upstream_id = upstream_resp.json()["id"]

        downstream_resp = await client.post(
            "/tasks",
            json={"title": "List Summary Down", "scheduled_at": iso},
            headers=auth_headers,
        )
        assert downstream_resp.status_code == 201
        downstream_id = downstream_resp.json()["id"]

        dep_resp = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        assert dep_resp.status_code == 201

        list_resp = await client.get(
            f"/tasks?client_today={day}&include_dependency_summary=true&status=pending",
            headers=auth_headers,
        )
        assert list_resp.status_code == 200
        tasks = list_resp.json()["tasks"]
        down = next(t for t in tasks if t["id"] == downstream_id)
        assert down["dependency_summary"] is not None
        assert down["dependency_summary"]["readiness_state"] == "blocked"
        assert down["dependency_summary"]["has_unmet_hard"] is True
        assert down["dependency_summary"]["has_unmet_soft"] is False

        up = next(t for t in tasks if t["id"] == upstream_id)
        assert up.get("dependency_summary") is None

    async def test_get_task_include_dependency_summary(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        day = "2030-06-11"
        iso = f"{day}T10:00:00+00:00"
        upstream_resp = await client.post(
            "/tasks",
            json={"title": "Get Up", "scheduled_at": iso},
            headers=auth_headers,
        )
        upstream_id = upstream_resp.json()["id"]
        downstream_resp = await client.post(
            "/tasks",
            json={"title": "Get Down", "scheduled_at": iso},
            headers=auth_headers,
        )
        downstream_id = downstream_resp.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": upstream_id,
                "downstream_task_id": downstream_id,
                "strength": "soft",
            },
            headers=auth_headers,
        )

        one = await client.get(
            f"/tasks/{downstream_id}?include_dependency_summary=true&client_today={day}",
            headers=auth_headers,
        )
        assert one.status_code == 200
        body = one.json()
        assert body["dependency_summary"] is not None
        assert body["dependency_summary"]["has_unmet_soft"] is True
        assert "Usually follows" in (body["dependency_summary"]["advisory_text"] or "")
