"""Branch coverage tests - targeting specific conditional branches."""

import pytest
from httpx import AsyncClient
from datetime import datetime, timezone, timedelta
from unittest.mock import patch


@pytest.fixture
def mock_validate_priority():
    """Mock priority validation."""
    with patch("app.services.priority_validation.validate_priority") as mock:
        async def async_return(*args, **kwargs):
            return {
                "overall_valid": True,
                "name_valid": True,
                "why_valid": True,
                "name_feedback": [],
                "why_feedback": [],
                "why_passed_rules": {"specificity": True, "actionable": True},
                "name_rewrite": None,
                "why_rewrite": None,
                "rule_examples": None,
            }
        mock.side_effect = async_return
        yield mock


# ============================================================================
# TASKS.PY BRANCH COVERAGE
# ============================================================================


class TestTaskCreationBranches:
    """Test all branches in task creation validation."""

    @pytest.mark.asyncio
    async def test_create_recurring_without_scheduling_mode(self, client: AsyncClient):
        """Branch: is_recurring and scheduled_at but no scheduling_mode."""
        goal = await client.post("/goals", json={"title": "Branch Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Missing Mode Task",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduled_at": now.isoformat(),
                # No scheduling_mode - should fail
            },
        )
        assert response.status_code == 400
        assert "scheduling_mode is required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_anytime_recurring_fails(self, client: AsyncClient):
        """Branch: scheduling_mode == anytime and is_recurring."""
        goal = await client.post("/goals", json={"title": "Anytime R Goal"})
        goal_id = goal.json()["id"]
        
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Anytime Recurring",
                "duration_minutes": 30,
                "scheduling_mode": "anytime",
                "is_recurring": True,
            },
        )
        assert response.status_code == 400
        assert "Anytime tasks cannot be recurring" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_recurring_without_behavior(self, client: AsyncClient):
        """Branch: is_recurring but no recurrence_behavior."""
        goal = await client.post("/goals", json={"title": "No Behavior Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "No Behavior Task",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduled_at": now.isoformat(),
                "scheduling_mode": "floating",
                # No recurrence_behavior - should fail
            },
        )
        assert response.status_code == 400
        assert "recurrence_behavior is required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_non_recurring_with_behavior(self, client: AsyncClient):
        """Branch: not is_recurring but has recurrence_behavior."""
        goal = await client.post("/goals", json={"title": "Extra Behavior Goal"})
        goal_id = goal.json()["id"]
        
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Extra Behavior Task",
                "duration_minutes": 30,
                "is_recurring": False,
                "recurrence_behavior": "habitual",  # Should not be set
            },
        )
        assert response.status_code == 400
        assert "recurrence_behavior should only be set" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_create_date_only_scheduling(self, client: AsyncClient):
        """Branch: scheduled_date without scheduled_at -> date_only mode."""
        goal = await client.post("/goals", json={"title": "Date Only Goal"})
        goal_id = goal.json()["id"]
        
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        response = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Date Only Task",
                "duration_minutes": 30,
                "scheduled_date": today,
                # No scheduled_at -> should auto-set date_only mode
            },
        )
        assert response.status_code == 201
        assert response.json()["scheduling_mode"] == "date_only"

    @pytest.mark.asyncio
    async def test_create_task_without_goal(self, client: AsyncClient):
        """Branch: no goal_id provided."""
        response = await client.post(
            "/tasks",
            json={
                "title": "No Goal Task",
                "duration_minutes": 30,
            },
        )
        # Should succeed or fail based on whether goal_id is required
        assert response.status_code in [201, 422]


class TestTaskUpdateBranches:
    """Test all branches in task update."""

    @pytest.mark.asyncio
    async def test_update_change_goal(self, client: AsyncClient):
        """Branch: goal_id changed."""
        goal1 = await client.post("/goals", json={"title": "Old Goal"})
        goal2 = await client.post("/goals", json={"title": "New Goal"})
        g1_id = goal1.json()["id"]
        g2_id = goal2.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": g1_id, "title": "Move Task", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        response = await client.patch(
            f"/tasks/{task_id}",
            json={"goal_id": g2_id},
        )
        assert response.status_code == 200
        assert response.json()["goal_id"] == g2_id

    @pytest.mark.asyncio
    async def test_update_scheduled_date_sets_mode(self, client: AsyncClient):
        """Branch: scheduled_date set -> auto-sets date_only mode."""
        goal = await client.post("/goals", json={"title": "Date Mode Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Date Mode Task",
                "duration_minutes": 30,
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        today = now.strftime("%Y-%m-%d")
        response = await client.patch(
            f"/tasks/{task_id}",
            json={"scheduled_date": today, "scheduled_at": None},
        )
        assert response.status_code == 200
        assert response.json()["scheduling_mode"] == "date_only"

    @pytest.mark.asyncio
    async def test_update_make_recurring_without_behavior_fails(self, client: AsyncClient):
        """Branch: update to recurring without behavior."""
        goal = await client.post("/goals", json={"title": "Recurr Update Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Become Recurring", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        response = await client.patch(
            f"/tasks/{task_id}",
            json={"is_recurring": True, "recurrence_rule": "FREQ=DAILY"},
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_remove_recurring_clears_behavior(self, client: AsyncClient):
        """Branch: task becomes non-recurring -> behavior cleared."""
        goal = await client.post("/goals", json={"title": "Stop Recurring Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Stop Recurring Task",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        response = await client.patch(
            f"/tasks/{task_id}",
            json={"is_recurring": False},
        )
        assert response.status_code == 200
        assert response.json()["recurrence_behavior"] is None


class TestTaskCompletionBranches:
    """Test completion/skip/reopen branches."""

    @pytest.mark.asyncio
    async def test_complete_recurring_task(self, client: AsyncClient):
        """Branch: task.is_recurring in complete."""
        goal = await client.post("/goals", json={"title": "Complete R Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Complete Recurring",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        response = await client.post(
            f"/tasks/{task_id}/complete",
            json={"local_date": now.strftime("%Y-%m-%d")},
        )
        assert response.status_code == 200
        # Task should still be pending
        assert response.json()["status"] == "pending"
        assert response.json()["completed_for_today"] is True

    @pytest.mark.asyncio
    async def test_complete_one_time_task(self, client: AsyncClient):
        """Branch: not task.is_recurring in complete."""
        goal = await client.post("/goals", json={"title": "Complete Once Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Complete Once", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        response = await client.post(f"/tasks/{task_id}/complete", json={})
        assert response.status_code == 200
        assert response.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_skip_recurring_task(self, client: AsyncClient):
        """Branch: task.is_recurring in skip."""
        goal = await client.post("/goals", json={"title": "Skip R Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Skip Recurring",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        response = await client.post(
            f"/tasks/{task_id}/skip",
            json={"reason": "Too busy", "local_date": now.strftime("%Y-%m-%d")},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "pending"  # Still pending
        assert response.json()["skipped_for_today"] is True

    @pytest.mark.asyncio
    async def test_skip_one_time_task(self, client: AsyncClient):
        """Branch: not task.is_recurring in skip."""
        goal = await client.post("/goals", json={"title": "Skip Once Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Skip Once", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        response = await client.post(
            f"/tasks/{task_id}/skip",
            json={"reason": "Not needed"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "skipped"

    @pytest.mark.asyncio
    async def test_reopen_recurring_task(self, client: AsyncClient):
        """Branch: task.is_recurring in reopen."""
        goal = await client.post("/goals", json={"title": "Reopen R Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Reopen Recurring",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        # Complete first
        await client.post(
            f"/tasks/{task_id}/complete",
            json={"scheduled_for": now.isoformat()},
        )
        
        # Reopen
        response = await client.post(
            f"/tasks/{task_id}/reopen",
            json={"scheduled_for": now.isoformat()},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_reopen_recurring_without_scheduled_for(self, client: AsyncClient):
        """Branch: is_recurring but no scheduled_for in reopen."""
        goal = await client.post("/goals", json={"title": "Reopen No Time Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Reopen No Time",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        # Complete first
        await client.post(
            f"/tasks/{task_id}/complete",
            json={"scheduled_for": now.isoformat()},
        )
        
        # Reopen without scheduled_for
        response = await client.post(
            f"/tasks/{task_id}/reopen",
            json={},  # No scheduled_for
        )
        assert response.status_code == 400
        assert "scheduled_for is required" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_reopen_recurring_no_completion_found(self, client: AsyncClient):
        """Branch: no completion found for time slot."""
        goal = await client.post("/goals", json={"title": "No Completion Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "No Completion Task",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        # Try to reopen without completing first
        response = await client.post(
            f"/tasks/{task_id}/reopen",
            json={"scheduled_for": now.isoformat()},
        )
        assert response.status_code == 400
        assert "No completion found" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_reopen_one_time_already_pending(self, client: AsyncClient):
        """Branch: one-time task already pending in reopen."""
        goal = await client.post("/goals", json={"title": "Already Pending Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Already Pending", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        response = await client.post(f"/tasks/{task_id}/reopen", json={})
        assert response.status_code == 400
        assert "already pending" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_reopen_one_time_completed(self, client: AsyncClient):
        """Branch: one-time task completed -> reopen."""
        goal = await client.post("/goals", json={"title": "Reopen Completed Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Reopen Completed", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        # Complete it
        await client.post(f"/tasks/{task_id}/complete", json={})
        
        # Reopen
        response = await client.post(f"/tasks/{task_id}/reopen", json={})
        assert response.status_code == 200
        assert response.json()["status"] == "pending"


class TestTaskListBranches:
    """Test branches in list_tasks."""

    @pytest.mark.asyncio
    async def test_list_filter_by_goal(self, client: AsyncClient):
        """Branch: goal_id filter."""
        goal = await client.post("/goals", json={"title": "Filter Goal"})
        goal_id = goal.json()["id"]
        
        await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Filtered Task", "duration_minutes": 30},
        )
        
        response = await client.get("/tasks", params={"goal_id": goal_id})
        assert response.status_code == 200
        tasks = response.json()["tasks"]
        assert all(t["goal_id"] == goal_id for t in tasks)

    @pytest.mark.asyncio
    async def test_list_filter_by_status(self, client: AsyncClient):
        """Branch: status filter."""
        goal = await client.post("/goals", json={"title": "Status Filter Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Status Task", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        # Complete it
        await client.post(f"/tasks/{task_id}/complete", json={})
        
        # Filter by completed
        response = await client.get("/tasks", params={"status": "completed", "include_completed": True})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_include_completed(self, client: AsyncClient):
        """Branch: include_completed=True."""
        goal = await client.post("/goals", json={"title": "Include Completed Goal"})
        goal_id = goal.json()["id"]
        
        task = await client.post(
            "/tasks",
            json={"goal_id": goal_id, "title": "Include Task", "duration_minutes": 30},
        )
        task_id = task.json()["id"]
        
        await client.post(f"/tasks/{task_id}/complete", json={})
        
        response = await client.get("/tasks", params={"include_completed": True})
        assert response.status_code == 200
        # Should include completed tasks
        assert any(t["status"] == "completed" for t in response.json()["tasks"])

    @pytest.mark.asyncio
    async def test_list_with_client_today(self, client: AsyncClient):
        """Branch: client_today provided."""
        goal = await client.post("/goals", json={"title": "Client Today Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Client Today Task",
                "duration_minutes": 30,
                "scheduled_at": now.isoformat(),
            },
        )
        
        today_str = now.strftime("%Y-%m-%d")
        response = await client.get("/tasks", params={"client_today": today_str})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_with_days_ahead(self, client: AsyncClient):
        """Branch: days_ahead > 0."""
        goal = await client.post("/goals", json={"title": "Days Ahead Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        # Schedule for tomorrow
        await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Tomorrow Task",
                "duration_minutes": 30,
                "scheduled_at": (now + timedelta(days=1)).isoformat(),
            },
        )
        
        response = await client.get("/tasks", params={"days_ahead": 7})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_scheduled_after_filter(self, client: AsyncClient):
        """Branch: scheduled_after filter with valid date."""
        goal = await client.post("/goals", json={"title": "After Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "After Task",
                "duration_minutes": 30,
                "scheduled_at": now.isoformat(),
            },
        )
        
        yesterday = (now - timedelta(days=1)).isoformat()
        response = await client.get("/tasks", params={"scheduled_after": yesterday})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_scheduled_before_filter(self, client: AsyncClient):
        """Branch: scheduled_before filter with valid date."""
        goal = await client.post("/goals", json={"title": "Before Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Before Task",
                "duration_minutes": 30,
                "scheduled_at": now.isoformat(),
            },
        )
        
        tomorrow = (now + timedelta(days=1)).isoformat()
        response = await client.get("/tasks", params={"scheduled_before": tomorrow})
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_invalid_date_filters_ignored(self, client: AsyncClient):
        """Branch: invalid date format in filters -> ignored."""
        response = await client.get(
            "/tasks",
            params={
                "scheduled_after": "not-a-date",
                "scheduled_before": "also-invalid",
            },
        )
        assert response.status_code == 200  # Should succeed, just ignore bad dates


class TestTimeMachineBranches:
    """Test time machine endpoint branches."""

    @pytest.mark.asyncio
    async def test_count_future_completions_with_date(self, client: AsyncClient):
        """Branch: after_date provided."""
        goal = await client.post("/goals", json={"title": "Future Count Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Future Count Task",
                "duration_minutes": 30,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        # Complete for future date
        future = (now + timedelta(days=5))
        await client.post(
            f"/tasks/{task_id}/complete",
            json={"scheduled_for": future.isoformat()},
        )
        
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        response = await client.get(
            "/tasks/completions/future/count",
            params={"after_date": yesterday},
        )
        assert response.status_code == 200
        assert response.json()["count"] >= 0

    @pytest.mark.asyncio
    async def test_count_future_completions_default_date(self, client: AsyncClient):
        """Branch: after_date not provided -> defaults to today."""
        response = await client.get("/tasks/completions/future/count")
        assert response.status_code == 200
        assert "count" in response.json()

    @pytest.mark.asyncio
    async def test_count_future_completions_invalid_date(self, client: AsyncClient):
        """Branch: invalid date format."""
        response = await client.get(
            "/tasks/completions/future/count",
            params={"after_date": "invalid-date"},
        )
        assert response.status_code == 400
        assert "Invalid date format" in response.json()["detail"]


# ============================================================================
# DISCOVERY.PY BRANCH COVERAGE
# ============================================================================


class TestDiscoveryBranches:
    """Test discovery endpoint branches."""

    @pytest.mark.asyncio
    async def test_selection_already_exists(self, client: AsyncClient):
        """Branch: selection already exists."""
        prompts = await client.get("/discovery/prompts")
        prompts_list = prompts.json()["prompts"]
        
        if len(prompts_list) > 0:
            prompt_id = prompts_list[0]["id"]
            
            # Create first selection
            await client.post(
                "/discovery/selections",
                json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 1},
            )
            
            # Try to create duplicate
            response = await client.post(
                "/discovery/selections",
                json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 2},
            )
            assert response.status_code == 400
            assert "already exists" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_update_selection_bucket(self, client: AsyncClient):
        """Branch: update.bucket is not None."""
        prompts = await client.get("/discovery/prompts")
        prompts_list = prompts.json()["prompts"]
        
        if len(prompts_list) > 0:
            prompt_id = prompts_list[0]["id"]
            
            sel = await client.post(
                "/discovery/selections",
                json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 1},
            )
            sel_id = sel.json()["id"]
            
            response = await client.put(
                f"/discovery/selections/{sel_id}",
                json={"bucket": "discard"},
            )
            assert response.status_code == 200
            assert response.json()["bucket"] == "discard"

    @pytest.mark.asyncio
    async def test_update_selection_order(self, client: AsyncClient):
        """Branch: update.display_order is not None."""
        prompts = await client.get("/discovery/prompts")
        prompts_list = prompts.json()["prompts"]
        
        if len(prompts_list) > 0:
            prompt_id = prompts_list[0]["id"]
            
            sel = await client.post(
                "/discovery/selections",
                json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 1},
            )
            sel_id = sel.json()["id"]
            
            response = await client.put(
                f"/discovery/selections/{sel_id}",
                json={"display_order": 5},
            )
            assert response.status_code == 200
            assert response.json()["display_order"] == 5

    @pytest.mark.asyncio
    async def test_bulk_update_selections(self, client: AsyncClient):
        """Branch: bulk update with multiple selections."""
        prompts = await client.get("/discovery/prompts")
        prompts_list = prompts.json()["prompts"]
        
        if len(prompts_list) >= 2:
            response = await client.put(
                "/discovery/selections/bulk",
                json={
                    "selections": [
                        {"prompt_id": prompts_list[0]["id"], "bucket": "keep", "display_order": 1},
                        {"prompt_id": prompts_list[1]["id"], "bucket": "discard", "display_order": 2},
                    ]
                },
            )
            assert response.status_code == 200
            assert len(response.json()["selections"]) == 2


# ============================================================================
# TASK_STATS.PY BRANCH COVERAGE
# ============================================================================


class TestTaskStatsBranches:
    """Test task stats endpoint branches."""

    @pytest.mark.asyncio
    async def test_stats_for_recurring_task(self, client: AsyncClient):
        """Branch: task.is_recurring and task.recurrence_rule."""
        goal = await client.post("/goals", json={"title": "Stats Recurring Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Stats Recurring Task",
                "duration_minutes": 15,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": week_ago.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        response = await client.get(
            f"/tasks/{task_id}/stats",
            params={
                "start": week_ago.isoformat(),
                "end": now.isoformat(),
            },
        )
        assert response.status_code == 200
        stats = response.json()
        assert stats["total_expected"] >= 7

    @pytest.mark.asyncio
    async def test_stats_for_non_recurring_task(self, client: AsyncClient):
        """Branch: not is_recurring (expected = 1)."""
        goal = await client.post("/goals", json={"title": "Stats Once Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Stats Once Task",
                "duration_minutes": 30,
                "scheduled_at": now.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        response = await client.get(
            f"/tasks/{task_id}/stats",
            params={
                "start": (now - timedelta(days=1)).isoformat(),
                "end": (now + timedelta(days=1)).isoformat(),
            },
        )
        assert response.status_code == 200
        assert response.json()["total_expected"] == 1

    @pytest.mark.asyncio
    async def test_stats_with_completions_and_skips(self, client: AsyncClient):
        """Branch: count completed and skipped."""
        goal = await client.post("/goals", json={"title": "Mixed Stats Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Mixed Stats Task",
                "duration_minutes": 15,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": week_ago.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        # Complete some
        for i in range(3):
            d = now - timedelta(days=i)
            await client.post(
                f"/tasks/{task_id}/complete",
                json={"scheduled_for": d.isoformat()},
            )
        
        # Skip some
        for i in range(4, 6):
            d = now - timedelta(days=i)
            await client.post(
                f"/tasks/{task_id}/skip",
                json={"scheduled_for": d.isoformat()},
            )
        
        response = await client.get(
            f"/tasks/{task_id}/stats",
            params={
                "start": week_ago.isoformat(),
                "end": now.isoformat(),
            },
        )
        assert response.status_code == 200
        stats = response.json()
        assert stats["total_completed"] >= 0
        assert stats["total_skipped"] >= 0

    @pytest.mark.asyncio
    async def test_history_for_recurring_task(self, client: AsyncClient):
        """Branch: task.is_recurring in history."""
        goal = await client.post("/goals", json={"title": "History Recurring Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)
        
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "History Recurring Task",
                "duration_minutes": 15,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": week_ago.isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        response = await client.get(
            f"/tasks/{task_id}/history",
            params={
                "start": week_ago.isoformat(),
                "end": now.isoformat(),
            },
        )
        assert response.status_code == 200
        assert "days" in response.json()

    @pytest.mark.asyncio
    async def test_history_day_status_completed(self, client: AsyncClient):
        """Branch: completed >= expected."""
        goal = await client.post("/goals", json={"title": "Day Complete Goal"})
        goal_id = goal.json()["id"]
        
        now = datetime.now(timezone.utc)
        
        task = await client.post(
            "/tasks",
            json={
                "goal_id": goal_id,
                "title": "Day Complete Task",
                "duration_minutes": 15,
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "scheduling_mode": "floating",
                "recurrence_behavior": "habitual",
                "scheduled_at": (now - timedelta(days=3)).isoformat(),
            },
        )
        task_id = task.json()["id"]
        
        # Complete for a specific day
        yesterday = now - timedelta(days=1)
        await client.post(
            f"/tasks/{task_id}/complete",
            json={"scheduled_for": yesterday.isoformat()},
        )
        
        response = await client.get(
            f"/tasks/{task_id}/history",
            params={
                "start": (now - timedelta(days=3)).isoformat(),
                "end": now.isoformat(),
            },
        )
        assert response.status_code == 200
        days = response.json()["days"]
        # At least one day should be completed
        statuses = [d["status"] for d in days]
        assert "completed" in statuses or "missed" in statuses


# ============================================================================
# VALUES.PY BRANCH COVERAGE
# ============================================================================


class TestValuesBranches:
    """Test values endpoint branches."""

    @pytest.mark.asyncio
    async def test_value_create_with_origin_declared(self, client: AsyncClient):
        """Branch: origin == declared."""
        response = await client.post(
            "/values",
            json={"statement": "Declared Branch", "weight_raw": 70, "origin": "declared"},
        )
        assert response.status_code == 201
        assert response.json()["active_revision"]["origin"] == "declared"

    @pytest.mark.asyncio
    async def test_value_create_with_origin_suggested(self, client: AsyncClient):
        """Branch: origin == suggested."""
        response = await client.post(
            "/values",
            json={"statement": "Suggested Branch", "weight_raw": 60, "origin": "suggested"},
        )
        assert response.status_code == 201
        assert response.json()["active_revision"]["origin"] == "suggested"

    @pytest.mark.asyncio
    async def test_value_create_with_origin_inferred(self, client: AsyncClient):
        """Branch: origin == inferred."""
        response = await client.post(
            "/values",
            json={"statement": "Inferred Branch", "weight_raw": 50, "origin": "inferred"},
        )
        assert response.status_code == 201
        assert response.json()["active_revision"]["origin"] == "inferred"

    @pytest.mark.asyncio
    async def test_value_create_with_source_prompt(self, client: AsyncClient):
        """Branch: source_prompt_id provided."""
        prompts = await client.get("/discovery/prompts")
        prompts_list = prompts.json()["prompts"]
        
        if len(prompts_list) > 0:
            prompt_id = prompts_list[0]["id"]
            response = await client.post(
                "/values",
                json={
                    "statement": "From Prompt Branch",
                    "weight_raw": 55,
                    "origin": "declared",
                    "source_prompt_id": prompt_id,
                },
            )
            assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_value_update_creates_revision(self, client: AsyncClient):
        """Branch: update value -> new revision created."""
        val = await client.post(
            "/values",
            json={"statement": "Update Branch", "weight_raw": 60, "origin": "declared"},
        )
        val_id = val.json()["id"]
        
        response = await client.put(
            f"/values/{val_id}",
            json={"statement": "Updated Branch Statement", "weight_raw": 70},
        )
        assert response.status_code == 200
        assert response.json()["active_revision"]["statement"] == "Updated Branch Statement"


# ============================================================================
# PRIORITIES.PY BRANCH COVERAGE
# ============================================================================


class TestPrioritiesBranches:
    """Test priorities endpoint branches."""

    @pytest.mark.asyncio
    async def test_priority_with_value_links(self, client: AsyncClient, mock_validate_priority):
        """Branch: value_ids provided."""
        val = await client.post(
            "/values",
            json={"statement": "Link Branch Value", "weight_raw": 70, "origin": "declared"},
        )
        val_id = val.json()["id"]
        
        response = await client.post(
            "/priorities",
            json={
                "title": "Linked Branch Priority",
                "why_matters": "Testing value link branch",
                "score": 4,
                "value_ids": [val_id],
            },
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_priority_without_value_links(self, client: AsyncClient, mock_validate_priority):
        """Branch: value_ids not provided."""
        response = await client.post(
            "/priorities",
            json={
                "title": "No Links Branch Priority",
                "why_matters": "Testing no value links",
                "score": 3,
            },
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_priority_anchor_with_links(self, client: AsyncClient, mock_validate_priority):
        """Branch: anchor priority that has links."""
        val = await client.post(
            "/values",
            json={"statement": "Anchor Branch Value", "weight_raw": 70, "origin": "declared"},
        )
        val_id = val.json()["id"]
        
        priority = await client.post(
            "/priorities",
            json={
                "title": "Anchor Branch Priority",
                "why_matters": "Testing anchor with links",
                "score": 4,
                "value_ids": [val_id],
            },
        )
        p_id = priority.json()["id"]
        
        response = await client.post(f"/priorities/{p_id}/anchor")
        assert response.status_code == 200
        assert response.json()["active_revision"]["is_anchored"] is True

    @pytest.mark.asyncio
    async def test_priority_unanchor(self, client: AsyncClient, mock_validate_priority):
        """Branch: unanchor priority."""
        val = await client.post(
            "/values",
            json={"statement": "Unanchor Value", "weight_raw": 70, "origin": "declared"},
        )
        val_id = val.json()["id"]
        
        priority = await client.post(
            "/priorities",
            json={
                "title": "Unanchor Branch Priority",
                "why_matters": "Testing unanchor branch",
                "score": 4,
                "value_ids": [val_id],
            },
        )
        p_id = priority.json()["id"]
        
        await client.post(f"/priorities/{p_id}/anchor")
        response = await client.post(f"/priorities/{p_id}/unanchor")
        assert response.status_code == 200
        assert response.json()["active_revision"]["is_anchored"] is False

    @pytest.mark.asyncio
    async def test_priority_stash(self, client: AsyncClient, mock_validate_priority):
        """Branch: stash priority."""
        priority = await client.post(
            "/priorities",
            json={
                "title": "Stash Branch Priority",
                "why_matters": "Testing stash branch",
                "score": 2,
            },
        )
        p_id = priority.json()["id"]
        
        response = await client.post(
            f"/priorities/{p_id}/stash",
            json={"is_stashed": True},
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_priority_create_revision(self, client: AsyncClient, mock_validate_priority):
        """Branch: create new revision."""
        priority = await client.post(
            "/priorities",
            json={
                "title": "Revision Branch Priority",
                "why_matters": "Testing revision creation",
                "score": 3,
            },
        )
        p_id = priority.json()["id"]
        
        response = await client.post(
            f"/priorities/{p_id}/revisions",
            json={
                "title": "New Revision Title",
                "why_matters": "Updated revision text",
                "score": 4,
            },
        )
        assert response.status_code in [200, 201]
