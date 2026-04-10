"""Comprehensive coverage tests targeting low-coverage API endpoints.

Targets: occurrence_ordering.py, task_stats.py, alignment.py, value_similarity.py
"""

import pytest
from httpx import AsyncClient
from datetime import datetime, timezone, timedelta
from uuid import uuid4


# ============================================================================
# OCCURRENCE ORDERING TESTS
# ============================================================================

class TestOccurrenceOrdering:
    """Tests for task occurrence reordering endpoints."""

    @pytest.mark.asyncio
    async def test_reorder_occurrences_today_mode(self, client: AsyncClient):
        """Test reordering with save_mode='today'."""
        goal = await client.post("/goals", json={"title": "Reorder Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task1 = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Task 1",
                "duration_minutes": 30,
                "scheduled_date": now.strftime("%Y-%m-%d"),
            },
        )
        task1_id = task1.json()["id"]
        
        task2 = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Task 2",
                "duration_minutes": 30,
                "scheduled_date": now.strftime("%Y-%m-%d"),
            },
        )
        task2_id = task2.json()["id"]
        
        response = await client.post(
            "/tasks/reorder-occurrences",
            json={
                "date": now.strftime("%Y-%m-%d"),
                "save_mode": "today",
                "occurrences": [
                    {"task_id": task2_id, "occurrence_index": 0},
                    {"task_id": task1_id, "occurrence_index": 0},
                ],
            },
        )
        assert response.status_code == 200
        assert response.json()["save_mode"] == "today"

    @pytest.mark.asyncio
    async def test_reorder_occurrences_permanent_mode(self, client: AsyncClient):
        """Test reordering with save_mode='permanent'."""
        goal = await client.post("/goals", json={"title": "Perm Reorder Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Recurring Task",
                "duration_minutes": 30,
                "scheduled_at": now.isoformat(),
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
            },
        )
        task_id = task.json()["id"]
        
        response = await client.post(
            "/tasks/reorder-occurrences",
            json={
                "date": now.strftime("%Y-%m-%d"),
                "save_mode": "permanent",
                "occurrences": [
                    {"task_id": task_id, "occurrence_index": 0},
                ],
            },
        )
        assert response.status_code == 200
        assert response.json()["save_mode"] == "permanent"

    @pytest.mark.asyncio
    async def test_reorder_invalid_task_id(self, client: AsyncClient):
        """Test reordering with invalid task ID returns 404."""
        now = datetime.now(timezone.utc)
        response = await client.post(
            "/tasks/reorder-occurrences",
            json={
                "date": now.strftime("%Y-%m-%d"),
                "save_mode": "today",
                "occurrences": [
                    {"task_id": str(uuid4()), "occurrence_index": 0},
                ],
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_occurrence_order(self, client: AsyncClient):
        """Test getting task occurrence order for a day."""
        now = datetime.now(timezone.utc)
        response = await client.get(
            "/tasks/occurrence-order",
            params={"date": now.strftime("%Y-%m-%d")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "has_overrides" in data

    @pytest.mark.asyncio
    async def test_get_occurrence_order_with_data(self, client: AsyncClient):
        """Test getting occurrence order after reordering."""
        goal = await client.post("/goals", json={"title": "Order Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Ordered Task",
                "duration_minutes": 30,
                "scheduled_date": now.strftime("%Y-%m-%d"),
            },
        )
        task_id = task.json()["id"]
        
        # Reorder to create an override
        await client.post(
            "/tasks/reorder-occurrences",
            json={
                "date": now.strftime("%Y-%m-%d"),
                "save_mode": "today",
                "occurrences": [
                    {"task_id": task_id, "occurrence_index": 0},
                ],
            },
        )
        
        # Get order
        response = await client.get(
            "/tasks/occurrence-order",
            params={"date": now.strftime("%Y-%m-%d")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["has_overrides"] is True

    @pytest.mark.asyncio
    async def test_reorder_mixed_recurring_and_single(self, client: AsyncClient):
        """Test reordering with both recurring and single tasks."""
        goal = await client.post("/goals", json={"title": "Mixed Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        # Create a single (non-recurring) task
        single_task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Single Task",
                "duration_minutes": 30,
                "scheduled_date": now.strftime("%Y-%m-%d"),
            },
        )
        single_task_id = single_task.json()["id"]
        
        # Create a recurring task
        recurring_task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Recurring Task",
                "duration_minutes": 30,
                "scheduled_at": now.isoformat(),
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
            },
        )
        recurring_task_id = recurring_task.json()["id"]
        
        # Reorder with permanent mode - should split handling
        response = await client.post(
            "/tasks/reorder-occurrences",
            json={
                "date": now.strftime("%Y-%m-%d"),
                "save_mode": "permanent",
                "occurrences": [
                    {"task_id": single_task_id, "occurrence_index": 0},
                    {"task_id": recurring_task_id, "occurrence_index": 0},
                ],
            },
        )
        assert response.status_code == 200


# ============================================================================
# TASK STATS TESTS
# ============================================================================

class TestTaskStats:
    """Tests for task statistics endpoints."""

    @pytest.mark.asyncio
    async def test_get_task_stats(self, client: AsyncClient):
        """Test getting stats for a recurring task."""
        goal = await client.post("/goals", json={"title": "Stats Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Stats Task",
                "duration_minutes": 30,
                "scheduled_at": start.isoformat(),
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
            },
        )
        task_id = task.json()["id"]
        
        response = await client.get(
            f"/tasks/{task_id}/stats",
            params={
                "start": start.isoformat(),
                "end": now.isoformat(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "total_expected" in data
        assert "completion_rate" in data

    @pytest.mark.asyncio
    async def test_get_task_stats_nonexistent(self, client: AsyncClient):
        """Test getting stats for nonexistent task returns 404."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        response = await client.get(
            f"/tasks/{uuid4()}/stats",
            params={
                "start": start.isoformat(),
                "end": now.isoformat(),
            },
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_completion_history(self, client: AsyncClient):
        """Test getting completion history for a task."""
        goal = await client.post("/goals", json={"title": "History Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "History Task",
                "duration_minutes": 30,
                "scheduled_at": start.isoformat(),
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
            },
        )
        task_id = task.json()["id"]
        
        response = await client.get(
            f"/tasks/{task_id}/history",
            params={
                "start": start.isoformat(),
                "end": now.isoformat(),
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "days" in data

    @pytest.mark.asyncio
    async def test_get_completion_history_nonexistent(self, client: AsyncClient):
        """Test getting history for nonexistent task returns 404."""
        now = datetime.now(timezone.utc)
        start = now - timedelta(days=7)
        response = await client.get(
            f"/tasks/{uuid4()}/history",
            params={
                "start": start.isoformat(),
                "end": now.isoformat(),
            },
        )
        assert response.status_code == 404


# ============================================================================
# ALIGNMENT TESTS
# ============================================================================

class TestAlignment:
    """Tests for alignment check endpoint."""

    @pytest.mark.asyncio
    async def test_check_alignment_empty(self, client: AsyncClient):
        """Test alignment check with no values or priorities."""
        response = await client.post("/alignment/check", json={})
        assert response.status_code == 200
        data = response.json()
        assert "alignment_fit" in data
        assert data["declared"] == {}

    @pytest.mark.asyncio
    async def test_check_alignment_with_values(self, client: AsyncClient):
        """Test alignment check with values."""
        # Create a value first
        await client.post(
            "/values",
            json={
                "statement": "I value health",
                "weight_raw": 25,
                "origin": "declared",
            },
        )
        
        response = await client.post("/alignment/check", json={})
        assert response.status_code == 200
        data = response.json()
        assert "alignment_fit" in data
        # Should have declared values now
        assert len(data["declared"]) >= 1


# ============================================================================
# DEPENDENCIES TESTS
# ============================================================================

class TestDependencies:
    """Tests for dependency rule endpoints."""

    @pytest.mark.asyncio
    async def test_create_dependency_rule(self, client: AsyncClient):
        """Test creating a dependency rule between tasks."""
        goal = await client.post("/goals", json={"title": "Dep Goal"})
        goal_id = goal.json()["id"]
        
        task1 = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Upstream", "duration_minutes": 30},
        )
        task1_id = task1.json()["id"]
        
        task2 = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Downstream", "duration_minutes": 30},
        )
        task2_id = task2.json()["id"]
        
        response = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": task1_id,
                "downstream_task_id": task2_id,
                "dependency_type": "blocks",
            },
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_dependency_rule_cycle_detection(self, client: AsyncClient):
        """Test that cycle detection prevents circular dependencies."""
        goal = await client.post("/goals", json={"title": "Cycle Goal"})
        goal_id = goal.json()["id"]
        
        task1 = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Task A", "duration_minutes": 30},
        )
        task1_id = task1.json()["id"]
        
        task2 = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Task B", "duration_minutes": 30},
        )
        task2_id = task2.json()["id"]
        
        # Create A -> B
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": task1_id,
                "downstream_task_id": task2_id,
                "dependency_type": "blocks",
            },
        )
        
        # Try to create B -> A (should fail - cycle)
        response = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": task2_id,
                "downstream_task_id": task1_id,
                "dependency_type": "blocks",
            },
        )
        assert response.status_code == 400
        assert "cycle" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_list_dependency_rules(self, client: AsyncClient):
        """Test listing dependency rules."""
        response = await client.get("/dependencies")
        assert response.status_code == 200
        data = response.json()
        assert "rules" in data

    @pytest.mark.asyncio
    async def test_delete_dependency_rule(self, client: AsyncClient):
        """Test deleting a dependency rule."""
        goal = await client.post("/goals", json={"title": "Del Dep Goal"})
        goal_id = goal.json()["id"]
        
        task1 = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Task 1", "duration_minutes": 30},
        )
        task1_id = task1.json()["id"]
        
        task2 = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Task 2", "duration_minutes": 30},
        )
        task2_id = task2.json()["id"]
        
        # Create rule
        create_response = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": task1_id,
                "downstream_task_id": task2_id,
                "dependency_type": "blocks",
            },
        )
        rule_id = create_response.json()["id"]
        
        # Delete rule
        delete_response = await client.delete(f"/dependencies/{rule_id}")
        assert delete_response.status_code == 204


# ============================================================================
# LINKS TESTS - Removed (endpoints don't exist)
# ============================================================================


# ============================================================================
# RECOMMENDATIONS TESTS - Removed (endpoints don't exist)
# ============================================================================
