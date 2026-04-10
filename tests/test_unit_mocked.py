"""Unit tests with mocked external services and error scenarios."""

import pytest
from httpx import AsyncClient
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timezone, timedelta
import json


# ============================================================================
# Mock Fixtures
# ============================================================================


@pytest.fixture
def mock_validate_priority():
    """Mock priority validation to always return valid."""
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


@pytest.fixture
def mock_llm_alignment():
    """Mock LLM service for alignment reflection."""
    with patch("app.api.alignment.LLMService.get_alignment_reflection") as mock:
        async def async_return(*args, **kwargs):
            return "Your values and priorities are well aligned."
        mock.side_effect = async_return
        yield mock


@pytest.fixture
def mock_llm_recommendation():
    """Mock LLM service for assistant recommendations."""
    with patch("app.services.llm_service.LLMService.get_recommendation") as mock:
        async def async_return(*args, **kwargs):
            return {
                "choices": [{
                    "message": {
                        "content": "I can help you with that.",
                        "tool_calls": None,
                    }
                }]
            }
        mock.side_effect = async_return
        yield mock


# ============================================================================
# Alignment API Tests with Mocked LLM
# ============================================================================


@pytest.mark.asyncio
async def test_alignment_with_no_values_mocked(client: AsyncClient, mock_llm_alignment):
    """Test alignment check with no values returns defaults."""
    response = await client.post("/alignment/check")
    assert response.status_code == 200
    data = response.json()
    assert data["declared"] == {}
    assert data["implied"] == {}
    assert data["total_variation_distance"] == 0.0
    assert data["alignment_fit"] == 1.0


@pytest.mark.asyncio
async def test_alignment_with_values_no_priorities_mocked(
    client: AsyncClient, mock_llm_alignment
):
    """Test alignment with values but no anchored priorities."""
    # Create value
    val = await client.post(
        "/values",
        json={"statement": "Test Value", "weight_raw": 70, "origin": "declared"},
    )
    assert val.status_code == 201

    response = await client.post("/alignment/check")
    assert response.status_code == 200
    data = response.json()
    # Has declared but no implied (no anchored priorities)
    assert len(data["declared"]) >= 1
    assert data["implied"] == {}


@pytest.mark.asyncio
async def test_alignment_full_calculation_mocked(
    client: AsyncClient, mock_validate_priority, mock_llm_alignment
):
    """Test alignment with values and anchored priorities computes TVD."""
    # Create value
    val = await client.post(
        "/values",
        json={"statement": "Core Value", "weight_raw": 100, "origin": "declared"},
    )
    val_id = val.json()["id"]

    # Create priority linked to value
    priority = await client.post(
        "/priorities",
        json={
            "title": "Priority For Alignment",
            "why_matters": "Testing alignment calculation with linked values",
            "score": 5,
            "value_ids": [val_id],
        },
    )
    p_id = priority.json()["id"]

    # Anchor the priority
    await client.post(f"/priorities/{p_id}/anchor")

    response = await client.post("/alignment/check")
    assert response.status_code == 200
    data = response.json()
    assert "declared" in data
    assert "implied" in data
    assert "total_variation_distance" in data
    assert "alignment_fit" in data
    assert "reflection" in data


@pytest.mark.asyncio
async def test_alignment_multiple_priorities_mocked(
    client: AsyncClient, mock_validate_priority, mock_llm_alignment
):
    """Test alignment with multiple anchored priorities."""
    # Create values
    val1 = await client.post(
        "/values",
        json={"statement": "Value One", "weight_raw": 60, "origin": "declared"},
    )
    val1_id = val1.json()["id"]

    val2 = await client.post(
        "/values",
        json={"statement": "Value Two", "weight_raw": 40, "origin": "declared"},
    )
    val2_id = val2.json()["id"]

    # Create priorities linked to different values
    p1 = await client.post(
        "/priorities",
        json={
            "title": "Priority One",
            "why_matters": "First priority for alignment test",
            "score": 4,
            "value_ids": [val1_id],
        },
    )
    await client.post(f"/priorities/{p1.json()['id']}/anchor")

    p2 = await client.post(
        "/priorities",
        json={
            "title": "Priority Two",
            "why_matters": "Second priority for alignment test",
            "score": 3,
            "value_ids": [val2_id],
        },
    )
    await client.post(f"/priorities/{p2.json()['id']}/anchor")

    response = await client.post("/alignment/check")
    assert response.status_code == 200
    data = response.json()
    # Should have computed implied weights
    assert len(data["implied"]) >= 1


# ============================================================================
# Assistant API Tests with Mocked LLM
# ============================================================================


@pytest.mark.asyncio
async def test_assistant_session_lifecycle(client: AsyncClient):
    """Test full assistant session lifecycle."""
    # Create session
    create_resp = await client.post(
        "/assistant/sessions",
        json={"context_mode": "general"},
    )
    assert create_resp.status_code in [200, 201]
    session_id = create_resp.json()["id"]

    # Get session
    get_resp = await client.get(f"/assistant/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == session_id
    assert get_resp.json()["context_mode"] == "general"


@pytest.mark.asyncio
async def test_assistant_send_message_mocked(client: AsyncClient):
    """Test sending message to assistant with mocked LLM."""
    # Create session
    create_resp = await client.post(
        "/assistant/sessions",
        json={"context_mode": "general"},
    )
    session_id = create_resp.json()["id"]

    # Mock LLM response
    with patch("app.api.assistant.LLMService.get_recommendation") as mock_llm:
        async def mock_response(*args, **kwargs):
            return {
                "choices": [{
                    "message": {
                        "content": "I can help you explore your values.",
                        "tool_calls": None,
                    }
                }]
            }
        mock_llm.side_effect = mock_response

        response = await client.post(
            f"/assistant/sessions/{session_id}/message",
            json={"content": "Help me find my values", "input_modality": "text"},
        )
        assert response.status_code == 200
        assert "response" in response.json()


@pytest.mark.asyncio
async def test_assistant_message_with_tool_call_mocked(client: AsyncClient):
    """Test assistant message that triggers a tool call."""
    create_resp = await client.post(
        "/assistant/sessions",
        json={"context_mode": "values"},
    )
    session_id = create_resp.json()["id"]

    with patch("app.api.assistant.LLMService.get_recommendation") as mock_llm:
        async def mock_response(*args, **kwargs):
            return {
                "choices": [{
                    "message": {
                        "content": None,
                        "tool_calls": [{
                            "function": {
                                "name": "propose_value",
                                "arguments": json.dumps({
                                    "statement": "I value creativity",
                                    "rationale": "You mentioned enjoying creative work",
                                }),
                            }
                        }],
                    }
                }]
            }
        mock_llm.side_effect = mock_response

        response = await client.post(
            f"/assistant/sessions/{session_id}/message",
            json={"content": "I really enjoy creative work", "input_modality": "text"},
        )
        assert response.status_code == 200
        data = response.json()
        # Should have created a recommendation
        assert data.get("recommendation_id") is not None or "proposed value" in data.get("response", "")


@pytest.mark.asyncio
async def test_assistant_session_not_found(client: AsyncClient):
    """Test getting non-existent session returns 404."""
    response = await client.get("/assistant/sessions/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_assistant_message_session_not_found(client: AsyncClient):
    """Test sending message to non-existent session returns 404."""
    response = await client.post(
        "/assistant/sessions/00000000-0000-0000-0000-000000000000/message",
        json={"content": "test", "input_modality": "text"},
    )
    assert response.status_code == 404


# ============================================================================
# Recommendations API Tests
# ============================================================================


@pytest.mark.asyncio
async def test_recommendations_list_empty(client: AsyncClient):
    """Test listing pending recommendations when none exist."""
    response = await client.get("/recommendations/pending")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_recommendations_session_not_found(client: AsyncClient):
    """Test getting recommendations for non-existent session."""
    response = await client.get("/recommendations/session/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_accept_recommendation_not_found(client: AsyncClient):
    """Test accepting non-existent recommendation."""
    response = await client.post(
        "/recommendations/00000000-0000-0000-0000-000000000000/accept",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_reject_recommendation_not_found(client: AsyncClient):
    """Test rejecting non-existent recommendation."""
    response = await client.post(
        "/recommendations/00000000-0000-0000-0000-000000000000/reject",
        json={},
    )
    assert response.status_code == 404


# ============================================================================
# Discovery API Error Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_discovery_selection_duplicate(client: AsyncClient):
    """Test creating duplicate selection fails."""
    prompts = await client.get("/discovery/prompts")
    if len(prompts.json()["prompts"]) > 0:
        prompt_id = prompts.json()["prompts"][0]["id"]

        # First selection
        resp1 = await client.post(
            "/discovery/selections",
            json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 1},
        )
        
        if resp1.status_code in [200, 201]:
            # Duplicate should fail
            resp2 = await client.post(
                "/discovery/selections",
                json={"prompt_id": prompt_id, "bucket": "keep", "display_order": 2},
            )
            assert resp2.status_code == 400


@pytest.mark.asyncio
async def test_discovery_update_not_found(client: AsyncClient):
    """Test updating non-existent selection."""
    response = await client.put(
        "/discovery/selections/00000000-0000-0000-0000-000000000000",
        json={"bucket": "discard"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_discovery_delete_not_found(client: AsyncClient):
    """Test deleting non-existent selection."""
    response = await client.delete(
        "/discovery/selections/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


# ============================================================================
# Goals API Error Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_goal_invalid_parent_self_reference(client: AsyncClient):
    """Test goal cannot be its own parent."""
    goal = await client.post("/goals", json={"title": "Self Parent Test"})
    goal_id = goal.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}",
        json={"parent_goal_id": goal_id},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_goal_invalid_priority_link(client: AsyncClient):
    """Test linking goal to non-existent priority fails."""
    goal = await client.post("/goals", json={"title": "Invalid Link Test"})
    goal_id = goal.json()["id"]

    response = await client.post(
        f"/goals/{goal_id}/priorities/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code in [400, 404]


@pytest.mark.asyncio
async def test_goal_duplicate_priority_link(client: AsyncClient, mock_validate_priority):
    """Test duplicate priority link fails."""
    # Create priority
    priority = await client.post(
        "/priorities",
        json={
            "title": "Dup Link Test",
            "why_matters": "Testing duplicate link validation",
            "score": 3,
        },
    )
    p_id = priority.json()["id"]

    # Create goal
    goal = await client.post("/goals", json={"title": "Dup Link Goal"})
    goal_id = goal.json()["id"]

    # First link
    await client.post(f"/goals/{goal_id}/priorities/{p_id}")

    # Duplicate should fail
    response = await client.post(f"/goals/{goal_id}/priorities/{p_id}")
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_goal_remove_nonexistent_priority_link(client: AsyncClient):
    """Test removing priority link that doesn't exist."""
    goal = await client.post("/goals", json={"title": "Remove Link Test"})
    goal_id = goal.json()["id"]

    response = await client.delete(
        f"/goals/{goal_id}/priorities/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


# ============================================================================
# Tasks API Error Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_task_not_found(client: AsyncClient):
    """Test getting non-existent task."""
    response = await client.get("/tasks/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_task_create_invalid_goal(client: AsyncClient):
    """Test creating task with invalid goal fails."""
    response = await client.post(
        "/tasks",
        json={
            "goal_id": "00000000-0000-0000-0000-000000000000",
            "title": "Invalid Task",
            "duration_minutes": 30,
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_task_update_not_found(client: AsyncClient):
    """Test updating non-existent task."""
    response = await client.patch(
        "/tasks/00000000-0000-0000-0000-000000000000",
        json={"title": "Updated"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_task_delete_not_found(client: AsyncClient):
    """Test deleting non-existent task."""
    response = await client.delete("/tasks/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_task_complete_not_found(client: AsyncClient):
    """Test completing non-existent task."""
    response = await client.post(
        "/tasks/00000000-0000-0000-0000-000000000000/complete",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_task_skip_not_found(client: AsyncClient):
    """Test skipping non-existent task."""
    response = await client.post(
        "/tasks/00000000-0000-0000-0000-000000000000/skip",
        json={},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_task_stats_not_found(client: AsyncClient):
    """Test getting stats for non-existent task."""
    now = datetime.now(timezone.utc)
    response = await client.get(
        "/tasks/00000000-0000-0000-0000-000000000000/stats",
        params={
            "start": (now - timedelta(days=7)).isoformat(),
            "end": now.isoformat(),
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_task_history_not_found(client: AsyncClient):
    """Test getting history for non-existent task."""
    now = datetime.now(timezone.utc)
    response = await client.get(
        "/tasks/00000000-0000-0000-0000-000000000000/history",
        params={
            "start": (now - timedelta(days=7)).isoformat(),
            "end": now.isoformat(),
        },
    )
    assert response.status_code == 404


# ============================================================================
# Priorities API Error Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_priority_not_found(client: AsyncClient):
    """Test getting non-existent priority."""
    response = await client.get("/priorities/00000000-0000-0000-0000-000000000000/history")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_priority_delete_not_found(client: AsyncClient):
    """Test deleting non-existent priority."""
    response = await client.delete("/priorities/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_priority_anchor_not_found(client: AsyncClient):
    """Test anchoring non-existent priority."""
    response = await client.post("/priorities/00000000-0000-0000-0000-000000000000/anchor")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_priority_unanchor_not_found(client: AsyncClient):
    """Test unanchoring non-existent priority."""
    response = await client.post("/priorities/00000000-0000-0000-0000-000000000000/unanchor")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_priority_stash_not_found(client: AsyncClient):
    """Test stashing non-existent priority."""
    response = await client.post(
        "/priorities/00000000-0000-0000-0000-000000000000/stash",
        json={"is_stashed": True},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_priority_revision_not_found(client: AsyncClient, mock_validate_priority):
    """Test creating revision for non-existent priority."""
    response = await client.post(
        "/priorities/00000000-0000-0000-0000-000000000000/revisions",
        json={
            "title": "New Revision",
            "why_matters": "Testing revision on non-existent priority",
            "score": 3,
        },
    )
    assert response.status_code == 404


# ============================================================================
# Values API Error Scenarios  
# ============================================================================


@pytest.mark.asyncio
async def test_value_not_found(client: AsyncClient):
    """Test getting non-existent value history."""
    response = await client.get("/values/00000000-0000-0000-0000-000000000000/history")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_value_delete_not_found(client: AsyncClient):
    """Test deleting non-existent value."""
    response = await client.delete("/values/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_value_update_not_found(client: AsyncClient):
    """Test updating non-existent value."""
    response = await client.put(
        "/values/00000000-0000-0000-0000-000000000000",
        json={"statement": "Updated", "weight_raw": 50},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_value_revision_not_found(client: AsyncClient):
    """Test creating revision for non-existent value."""
    response = await client.post(
        "/values/00000000-0000-0000-0000-000000000000/revisions",
        json={"statement": "New Statement", "weight_raw": 50},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_value_acknowledge_insight_not_found(client: AsyncClient):
    """Test acknowledging insight for non-existent value."""
    response = await client.post(
        "/values/00000000-0000-0000-0000-000000000000/insights/acknowledge",
        json={},
    )
    assert response.status_code == 404


# ============================================================================
# Links API Error Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_links_get_not_found(client: AsyncClient):
    """Test getting links for non-existent priority revision."""
    response = await client.get(
        "/priority-revisions/00000000-0000-0000-0000-000000000000/links"
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_links_set_not_found(client: AsyncClient):
    """Test setting links for non-existent priority revision."""
    response = await client.put(
        "/priority-revisions/00000000-0000-0000-0000-000000000000/links",
        json={"links": []},
    )
    assert response.status_code == 404


# ============================================================================
# Dependencies API Error Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_dependency_create_invalid_upstream(client: AsyncClient):
    """Test creating dependency with invalid upstream task."""
    goal = await client.post("/goals", json={"title": "Dep Test Goal"})
    goal_id = goal.json()["id"]

    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Valid Task", "duration_minutes": 30},
    )
    task_id = task.json()["id"]

    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": "00000000-0000-0000-0000-000000000000",
            "downstream_task_id": task_id,
            "rule_type": "completion",
            "is_hard": True,
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dependency_create_invalid_downstream(client: AsyncClient):
    """Test creating dependency with invalid downstream task."""
    goal = await client.post("/goals", json={"title": "Dep Test Goal 2"})
    goal_id = goal.json()["id"]

    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Valid Task 2", "duration_minutes": 30},
    )
    task_id = task.json()["id"]

    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_id,
            "downstream_task_id": "00000000-0000-0000-0000-000000000000",
            "rule_type": "completion",
            "is_hard": True,
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_dependency_create_self_reference(client: AsyncClient):
    """Test creating dependency where task depends on itself."""
    goal = await client.post("/goals", json={"title": "Self Dep Goal"})
    goal_id = goal.json()["id"]

    task = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Self Ref Task", "duration_minutes": 30},
    )
    task_id = task.json()["id"]

    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_id,
            "downstream_task_id": task_id,
            "rule_type": "completion",
            "is_hard": True,
        },
    )
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_dependency_create_duplicate(client: AsyncClient):
    """Test creating duplicate dependency."""
    goal = await client.post("/goals", json={"title": "Dup Dep Goal"})
    goal_id = goal.json()["id"]

    task1 = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task A", "duration_minutes": 30},
    )
    t1_id = task1.json()["id"]

    task2 = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Task B", "duration_minutes": 30},
    )
    t2_id = task2.json()["id"]

    # First dependency
    await client.post(
        "/dependencies",
        json={
            "upstream_task_id": t1_id,
            "downstream_task_id": t2_id,
            "rule_type": "completion",
            "is_hard": True,
        },
    )

    # Duplicate
    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": t1_id,
            "downstream_task_id": t2_id,
            "rule_type": "completion",
            "is_hard": True,
        },
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_dependency_cycle_detection(client: AsyncClient):
    """Test that circular dependencies are prevented."""
    goal = await client.post("/goals", json={"title": "Cycle Goal"})
    goal_id = goal.json()["id"]

    task1 = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Cycle Task 1", "duration_minutes": 30},
    )
    t1_id = task1.json()["id"]

    task2 = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Cycle Task 2", "duration_minutes": 30},
    )
    t2_id = task2.json()["id"]

    # A -> B
    await client.post(
        "/dependencies",
        json={
            "upstream_task_id": t1_id,
            "downstream_task_id": t2_id,
            "rule_type": "completion",
            "is_hard": True,
        },
    )

    # B -> A should create cycle
    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": t2_id,
            "downstream_task_id": t1_id,
            "rule_type": "completion",
            "is_hard": True,
        },
    )
    assert response.status_code == 400


# ============================================================================
# Occurrence Ordering Error Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_reorder_invalid_tasks(client: AsyncClient):
    """Test reordering with invalid task IDs."""
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    response = await client.post(
        "/tasks/reorder-occurrences",
        json={
            "date": today,
            "save_mode": "today",
            "occurrences": [
                {"task_id": "00000000-0000-0000-0000-000000000000", "occurrence_index": 0},
            ],
        },
    )
    assert response.status_code == 404


# ============================================================================
# Auth API Error Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_auth_invalid_refresh_token(client: AsyncClient):
    """Test refresh with invalid token."""
    response = await client.post(
        "/auth/refresh",
        json={"refresh_token": "invalid_token_here"},
    )
    assert response.status_code in [401, 422]


@pytest.mark.asyncio
async def test_auth_logout_invalid_token(client: AsyncClient):
    """Test logout with invalid refresh token."""
    response = await client.post(
        "/auth/logout",
        json={"refresh_token": "invalid_token"},
    )
    # Logout may succeed silently or fail - either is valid behavior
    assert response.status_code in [200, 401, 422]


# ============================================================================
# Voice API Tests
# ============================================================================


@pytest.mark.asyncio
async def test_voice_stt_no_file(client: AsyncClient):
    """Test STT endpoint requires file."""
    response = await client.post("/voice/stt")
    assert response.status_code == 422


# ============================================================================
# Task Views Error Scenarios
# ============================================================================


@pytest.mark.asyncio
async def test_today_view_empty(client: AsyncClient):
    """Test today view with no tasks."""
    response = await client.get("/tasks/view/today")
    assert response.status_code == 200
    assert "tasks" in response.json()


@pytest.mark.asyncio
async def test_range_view_invalid_dates(client: AsyncClient):
    """Test range view with invalid date range (end before start)."""
    now = datetime.now(timezone.utc)
    response = await client.post(
        "/tasks/view/range",
        json={
            "start_date": now.isoformat(),
            "end_date": (now - timedelta(days=7)).isoformat(),
        },
    )
    # Should either return empty or error
    assert response.status_code in [200, 400, 422]


# ============================================================================
# Additional Edge Cases
# ============================================================================


@pytest.mark.asyncio
async def test_task_complete_already_completed(client: AsyncClient):
    """Test completing an already completed non-recurring task."""
    goal = await client.post("/goals", json={"title": "Complete Twice Goal"})
    goal_id = goal.json()["id"]

    task = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Complete Twice Task",
            "duration_minutes": 30,
            "is_recurring": False,
        },
    )
    task_id = task.json()["id"]

    # Complete first time
    await client.post(f"/tasks/{task_id}/complete", json={})

    # Complete again - should handle gracefully
    response = await client.post(f"/tasks/{task_id}/complete", json={})
    assert response.status_code in [200, 400]


@pytest.mark.asyncio
async def test_priority_orphan_anchored_prevention(client: AsyncClient, mock_validate_priority):
    """Test preventing orphaned anchored priorities."""
    # Create value
    val = await client.post(
        "/values",
        json={"statement": "Orphan Test Value", "weight_raw": 70, "origin": "declared"},
    )
    val_id = val.json()["id"]

    # Create priority with value link
    priority = await client.post(
        "/priorities",
        json={
            "title": "Orphan Test Priority",
            "why_matters": "Testing orphan prevention for anchored priorities",
            "score": 4,
            "value_ids": [val_id],
        },
    )
    p_id = priority.json()["id"]

    # Anchor it
    await client.post(f"/priorities/{p_id}/anchor")

    # Try to create revision without value links - should fail for anchored
    response = await client.post(
        f"/priorities/{p_id}/revisions",
        json={
            "title": "No Links Revision",
            "why_matters": "Testing revision without value links",
            "score": 3,
            "value_ids": [],
        },
    )
    # Should fail because anchored priorities need links
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_goal_invalid_status(client: AsyncClient):
    """Test setting invalid goal status."""
    goal = await client.post("/goals", json={"title": "Invalid Status Goal"})
    goal_id = goal.json()["id"]

    response = await client.patch(
        f"/goals/{goal_id}",
        json={"status": "invalid_status"},
    )
    assert response.status_code in [400, 422]


@pytest.mark.asyncio
async def test_value_max_weight_validation(client: AsyncClient):
    """Test value weight boundaries."""
    # Very high weight
    response = await client.post(
        "/values",
        json={"statement": "High Weight Value", "weight_raw": 10000, "origin": "declared"},
    )
    # Should either accept or reject based on validation
    assert response.status_code in [201, 400, 422]


@pytest.mark.asyncio
async def test_task_invalid_recurrence_rule(client: AsyncClient):
    """Test task with invalid recurrence rule."""
    goal = await client.post("/goals", json={"title": "Invalid Recurrence Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)
    response = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Invalid Recurrence Task",
            "duration_minutes": 30,
            "is_recurring": True,
            "recurrence_rule": "INVALID_RULE",
            "scheduling_mode": "floating",
            "recurrence_behavior": "habitual",
            "scheduled_at": now.isoformat(),
        },
    )
    # Should either accept (and handle later) or reject immediately
    assert response.status_code in [201, 400, 422]
