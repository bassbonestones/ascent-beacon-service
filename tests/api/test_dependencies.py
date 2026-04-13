"""Tests for dependencies API endpoints (Phase 4i)."""

import pytest
from httpx import AsyncClient

from app.models.user import User


# ============================================================================
# Helper Functions
# ============================================================================


async def create_task(client: AsyncClient, title: str = "Test Task") -> dict:
    """Create a task and return its data."""
    response = await client.post(
        "/tasks",
        json={"title": title, "duration_minutes": 30},
    )
    assert response.status_code == 201
    return response.json()


async def create_dependency(
    client: AsyncClient,
    upstream_id: str,
    downstream_id: str,
    strength: str = "soft",
    scope: str = "next_occurrence",
    required_count: int = 1,
) -> dict:
    """Create a dependency rule and return its data."""
    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": upstream_id,
            "downstream_task_id": downstream_id,
            "strength": strength,
            "scope": scope,
            "required_occurrence_count": required_count,
        },
    )
    assert response.status_code == 201
    return response.json()


# ============================================================================
# Create Dependency Rule Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_dependency_simple(client: AsyncClient, test_user: User):
    """Test creating a simple dependency between two tasks."""
    # Create two tasks
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    # Create dependency: A → B (A must be done before B)
    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
        },
    )

    assert response.status_code == 201
    data = response.json()

    assert data["user_id"] == test_user.id
    assert data["upstream_task_id"] == task_a["id"]
    assert data["downstream_task_id"] == task_b["id"]
    assert data["strength"] == "soft"  # default
    assert data["scope"] == "next_occurrence"  # default
    assert data["required_occurrence_count"] == 1


@pytest.mark.asyncio
async def test_create_dependency_hard(client: AsyncClient):
    """Test creating a hard (blocking) dependency."""
    task_a = await create_task(client, "Prerequisite")
    task_b = await create_task(client, "Dependent")

    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
            "strength": "hard",
        },
    )

    assert response.status_code == 201
    assert response.json()["strength"] == "hard"


@pytest.mark.asyncio
async def test_create_dependency_count_based(client: AsyncClient):
    """Test creating a count-based dependency (e.g., 4 waters before gym)."""
    water = await create_task(client, "Drink Water")
    gym = await create_task(client, "Go to Gym")

    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": water["id"],
            "downstream_task_id": gym["id"],
            "strength": "hard",
            "scope": "within_window",
            "required_occurrence_count": 4,
            "validity_window_minutes": 480,  # 8 hours
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["required_occurrence_count"] == 4
    assert data["scope"] == "within_window"
    assert data["validity_window_minutes"] == 480


@pytest.mark.asyncio
async def test_create_dependency_includes_task_info(client: AsyncClient):
    """Test that response includes nested task info."""
    task_a = await create_task(client, "Morning Warmup")
    task_b = await create_task(client, "Workout")

    data = await create_dependency(client, task_a["id"], task_b["id"])

    assert data["upstream_task"]["id"] == task_a["id"]
    assert data["upstream_task"]["title"] == "Morning Warmup"
    assert data["downstream_task"]["id"] == task_b["id"]
    assert data["downstream_task"]["title"] == "Workout"


# ============================================================================
# Validation Error Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_dependency_self_reference(client: AsyncClient):
    """Test that a task cannot depend on itself."""
    task = await create_task(client, "Solo Task")

    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task["id"],
            "downstream_task_id": task["id"],
        },
    )

    assert response.status_code == 422  # Pydantic validation


@pytest.mark.asyncio
async def test_create_dependency_upstream_not_found(client: AsyncClient):
    """Test dependency with non-existent upstream task."""
    task = await create_task(client, "Real Task")

    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": "00000000-0000-0000-0000-000000000000",
            "downstream_task_id": task["id"],
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_dependency_downstream_not_found(client: AsyncClient):
    """Test dependency with non-existent downstream task."""
    task = await create_task(client, "Real Task")

    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task["id"],
            "downstream_task_id": "00000000-0000-0000-0000-000000000000",
        },
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_dependency_duplicate(client: AsyncClient):
    """Test creating duplicate dependency fails."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    # First creation succeeds
    await create_dependency(client, task_a["id"], task_b["id"])

    # Second creation fails
    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
        },
    )

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


# ============================================================================
# Cycle Detection Tests
# ============================================================================


@pytest.mark.asyncio
async def test_create_dependency_direct_cycle(client: AsyncClient):
    """Test that direct A→B, B→A cycle is rejected."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    # A → B succeeds
    await create_dependency(client, task_a["id"], task_b["id"])

    # B → A would create cycle
    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_b["id"],
            "downstream_task_id": task_a["id"],
        },
    )

    assert response.status_code == 400
    assert "cycle" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_dependency_transitive_cycle(client: AsyncClient):
    """Test that transitive A→B→C, C→A cycle is rejected."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")
    task_c = await create_task(client, "Task C")

    # A → B succeeds
    await create_dependency(client, task_a["id"], task_b["id"])

    # B → C succeeds
    await create_dependency(client, task_b["id"], task_c["id"])

    # C → A would create cycle
    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_c["id"],
            "downstream_task_id": task_a["id"],
        },
    )

    assert response.status_code == 400
    assert "cycle" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_dependency_no_false_positive_cycle(client: AsyncClient):
    """Test that valid DAG is not falsely rejected as cycle."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")
    task_c = await create_task(client, "Task C")
    task_d = await create_task(client, "Task D")

    # Build diamond DAG: A → B, A → C, B → D, C → D
    await create_dependency(client, task_a["id"], task_b["id"])
    await create_dependency(client, task_a["id"], task_c["id"])
    await create_dependency(client, task_b["id"], task_d["id"])

    # C → D should succeed (not a cycle)
    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_c["id"],
            "downstream_task_id": task_d["id"],
        },
    )

    assert response.status_code == 201


# ============================================================================
# List Dependencies Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_dependencies_empty(client: AsyncClient):
    """Test listing dependencies when none exist."""
    response = await client.get("/dependencies")

    assert response.status_code == 200
    data = response.json()
    assert data["rules"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_dependencies_all(client: AsyncClient):
    """Test listing all dependencies."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")
    task_c = await create_task(client, "Task C")

    await create_dependency(client, task_a["id"], task_b["id"])
    await create_dependency(client, task_b["id"], task_c["id"])

    response = await client.get("/dependencies")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["rules"]) == 2


@pytest.mark.asyncio
async def test_list_dependencies_filter_upstream(client: AsyncClient):
    """Test filtering dependencies by upstream task."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")
    task_c = await create_task(client, "Task C")

    await create_dependency(client, task_a["id"], task_b["id"])
    await create_dependency(client, task_a["id"], task_c["id"])
    await create_dependency(client, task_b["id"], task_c["id"])

    response = await client.get(
        "/dependencies", params={"upstream_task_id": task_a["id"]}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2  # A → B, A → C


@pytest.mark.asyncio
async def test_list_dependencies_filter_downstream(client: AsyncClient):
    """Test filtering dependencies by downstream task."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")
    task_c = await create_task(client, "Task C")

    await create_dependency(client, task_a["id"], task_c["id"])
    await create_dependency(client, task_b["id"], task_c["id"])

    response = await client.get(
        "/dependencies", params={"downstream_task_id": task_c["id"]}
    )

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2  # Both A → C, B → C


@pytest.mark.asyncio
async def test_list_dependencies_filter_task_either(client: AsyncClient):
    """Test filtering dependencies by task (either upstream or downstream)."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")
    task_c = await create_task(client, "Task C")

    await create_dependency(client, task_a["id"], task_b["id"])  # A → B
    await create_dependency(client, task_b["id"], task_c["id"])  # B → C

    response = await client.get("/dependencies", params={"task_id": task_b["id"]})

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2  # Both rules involve B


# ============================================================================
# Get Single Dependency Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_dependency(client: AsyncClient):
    """Test getting a single dependency rule."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    created = await create_dependency(client, task_a["id"], task_b["id"], "hard")

    response = await client.get(f"/dependencies/{created['id']}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created["id"]
    assert data["strength"] == "hard"


@pytest.mark.asyncio
async def test_get_dependency_not_found(client: AsyncClient):
    """Test getting non-existent dependency returns 404."""
    response = await client.get("/dependencies/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


# ============================================================================
# Update Dependency Tests
# ============================================================================


@pytest.mark.asyncio
async def test_update_dependency_strength(client: AsyncClient):
    """Test updating dependency strength."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    created = await create_dependency(client, task_a["id"], task_b["id"], "soft")
    assert created["strength"] == "soft"

    response = await client.patch(
        f"/dependencies/{created['id']}",
        json={"strength": "hard"},
    )

    assert response.status_code == 200
    assert response.json()["strength"] == "hard"


@pytest.mark.asyncio
async def test_update_dependency_scope(client: AsyncClient):
    """Test updating dependency scope."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    created = await create_dependency(client, task_a["id"], task_b["id"])

    response = await client.patch(
        f"/dependencies/{created['id']}",
        json={"scope": "all_occurrences"},
    )

    assert response.status_code == 200
    assert response.json()["scope"] == "all_occurrences"


@pytest.mark.asyncio
async def test_update_dependency_count(client: AsyncClient):
    """Test updating required occurrence count."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    created = await create_dependency(client, task_a["id"], task_b["id"])
    assert created["required_occurrence_count"] == 1

    response = await client.patch(
        f"/dependencies/{created['id']}",
        json={"required_occurrence_count": 4},
    )

    assert response.status_code == 200
    assert response.json()["required_occurrence_count"] == 4


@pytest.mark.asyncio
async def test_update_dependency_not_found(client: AsyncClient):
    """Test updating non-existent dependency returns 404."""
    response = await client.patch(
        "/dependencies/00000000-0000-0000-0000-000000000000",
        json={"strength": "hard"},
    )
    assert response.status_code == 404


# ============================================================================
# Delete Dependency Tests
# ============================================================================


@pytest.mark.asyncio
async def test_delete_dependency(client: AsyncClient):
    """Test deleting a dependency rule."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    created = await create_dependency(client, task_a["id"], task_b["id"])

    response = await client.delete(f"/dependencies/{created['id']}")
    assert response.status_code == 204

    # Verify it's gone
    response = await client.get(f"/dependencies/{created['id']}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_dependency_not_found(client: AsyncClient):
    """Test deleting non-existent dependency returns 404."""
    response = await client.delete(
        "/dependencies/00000000-0000-0000-0000-000000000000"
    )
    assert response.status_code == 404


# ============================================================================
# Validate Dependency Tests
# ============================================================================


@pytest.mark.asyncio
async def test_validate_dependency_valid(client: AsyncClient):
    """Test validating a valid dependency."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    response = await client.post(
        "/dependencies/validate",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is True
    assert data["reason"] is None


@pytest.mark.asyncio
async def test_validate_dependency_self_reference(client: AsyncClient):
    """Test validating self-referential dependency."""
    task = await create_task(client, "Task")

    response = await client.post(
        "/dependencies/validate",
        json={
            "upstream_task_id": task["id"],
            "downstream_task_id": task["id"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "itself" in data["reason"].lower()


@pytest.mark.asyncio
async def test_validate_dependency_would_create_cycle(client: AsyncClient):
    """Test validation detects cycle."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    await create_dependency(client, task_a["id"], task_b["id"])

    response = await client.post(
        "/dependencies/validate",
        json={
            "upstream_task_id": task_b["id"],
            "downstream_task_id": task_a["id"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "cycle" in data["reason"].lower()


@pytest.mark.asyncio
async def test_validate_dependency_already_exists(client: AsyncClient):
    """Test validation detects existing rule."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    await create_dependency(client, task_a["id"], task_b["id"])

    response = await client.post(
        "/dependencies/validate",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "already exists" in data["reason"].lower()


@pytest.mark.asyncio
async def test_validate_dependency_task_not_found(client: AsyncClient):
    """Test validation handles missing tasks."""
    task = await create_task(client, "Real Task")

    response = await client.post(
        "/dependencies/validate",
        json={
            "upstream_task_id": "00000000-0000-0000-0000-000000000000",
            "downstream_task_id": task["id"],
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["valid"] is False
    assert "not found" in data["reason"].lower()


# ============================================================================
# Additional Coverage Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_dependencies_by_upstream_task(client: AsyncClient):
    """Test filtering dependencies by upstream task."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")
    task_c = await create_task(client, "Task C")

    # Create A -> B and A -> C
    await create_dependency(client, task_a["id"], task_b["id"])
    await create_dependency(client, task_a["id"], task_c["id"])

    # Filter by upstream_task_id
    response = await client.get(f"/dependencies?upstream_task_id={task_a['id']}")
    assert response.status_code == 200
    rules = response.json()["rules"]
    assert len(rules) == 2


@pytest.mark.asyncio
async def test_list_dependencies_by_downstream_task(client: AsyncClient):
    """Test filtering dependencies by downstream task."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")
    task_c = await create_task(client, "Task C")

    # Create A -> C and B -> C
    await create_dependency(client, task_a["id"], task_c["id"])
    await create_dependency(client, task_b["id"], task_c["id"])

    # Filter by downstream_task_id
    response = await client.get(f"/dependencies?downstream_task_id={task_c['id']}")
    assert response.status_code == 200
    rules = response.json()["rules"]
    assert len(rules) == 2


@pytest.mark.asyncio
async def test_list_dependencies_by_task_id(client: AsyncClient):
    """Test filtering dependencies where task appears either upstream or downstream."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")
    task_c = await create_task(client, "Task C")

    # Create A -> B and B -> C (B appears in both)
    await create_dependency(client, task_a["id"], task_b["id"])
    await create_dependency(client, task_b["id"], task_c["id"])

    # Filter by task_id to find all where B is involved
    response = await client.get(f"/dependencies?task_id={task_b['id']}")
    assert response.status_code == 200
    rules = response.json()["rules"]
    assert len(rules) == 2


@pytest.mark.asyncio
async def test_get_dependency_rule(client: AsyncClient):
    """Test getting a single dependency rule by ID."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    create_response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
            "strength": "hard",
            "scope": "all_occurrences",
        },
    )
    rule_id = create_response.json()["id"]

    # Get the rule
    get_response = await client.get(f"/dependencies/{rule_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == rule_id


@pytest.mark.asyncio
async def test_get_dependency_rule_not_found(client: AsyncClient):
    """Test getting non-existent dependency rule."""
    response = await client.get("/dependencies/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_dependency_rule(client: AsyncClient):
    """Test updating a dependency rule."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    create_response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
            "strength": "soft",
            "scope": "all_occurrences",
        },
    )
    rule_id = create_response.json()["id"]

    # Update to hard
    update_response = await client.patch(
        f"/dependencies/{rule_id}",
        json={"strength": "hard"},
    )
    assert update_response.status_code == 200
    assert update_response.json()["strength"] == "hard"


@pytest.mark.asyncio
async def test_update_dependency_rule_not_found(client: AsyncClient):
    """Test updating non-existent dependency rule."""
    response = await client.patch(
        "/dependencies/00000000-0000-0000-0000-000000000000",
        json={"strength": "hard"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_dependency_rule(client: AsyncClient):
    """Test deleting a dependency rule."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    create_response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
            "strength": "hard",
            "scope": "all_occurrences",
        },
    )
    rule_id = create_response.json()["id"]

    # Delete the rule
    delete_response = await client.delete(f"/dependencies/{rule_id}")
    assert delete_response.status_code == 204

    # Verify it's gone
    get_response = await client.get(f"/dependencies/{rule_id}")
    assert get_response.status_code == 404


@pytest.mark.asyncio
async def test_delete_dependency_rule_not_found(client: AsyncClient):
    """Test deleting non-existent dependency rule."""
    response = await client.delete("/dependencies/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_dependency_duplicate_fails(client: AsyncClient):
    """Test that duplicate dependency creation fails."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    # Create first rule
    await create_dependency(client, task_a["id"], task_b["id"])

    # Try to create duplicate
    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
            "strength": "hard",
            "scope": "all_occurrences",
        },
    )
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_dependency_with_window(client: AsyncClient):
    """Test creating dependency with validity window."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
            "strength": "soft",
            "scope": "within_window",
            "validity_window_minutes": 60,
        },
    )
    assert response.status_code == 201
    assert response.json()["scope"] == "within_window"
    assert response.json()["validity_window_minutes"] == 60


@pytest.mark.asyncio
async def test_create_dependency_next_occurrence_scope(client: AsyncClient):
    """Test creating dependency with next_occurrence scope."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
            "strength": "hard",
            "scope": "next_occurrence",
        },
    )
    assert response.status_code == 201
    assert response.json()["scope"] == "next_occurrence"


# ============================================================================
# Additional Dependency Tests for Coverage
# ============================================================================


@pytest.mark.asyncio
async def test_long_cycle_detection(client: AsyncClient):
    """Test cycle detection with longer chain (A→B→C→D, prevents D→A)."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")
    task_c = await create_task(client, "Task C")
    task_d = await create_task(client, "Task D")

    # Create A→B
    await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
            "strength": "soft",
            "scope": "next_occurrence",
        },
    )

    # Create B→C
    await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_b["id"],
            "downstream_task_id": task_c["id"],
            "strength": "soft",
            "scope": "next_occurrence",
        },
    )

    # Create C→D
    await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_c["id"],
            "downstream_task_id": task_d["id"],
            "strength": "soft",
            "scope": "next_occurrence",
        },
    )

    # Try to create D→A (would form 4-node cycle)
    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_d["id"],
            "downstream_task_id": task_a["id"],
            "strength": "soft",
            "scope": "next_occurrence",
        },
    )
    assert response.status_code == 400
    assert "cycle" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_update_dependency_all_fields(client: AsyncClient):
    """Test updating multiple dependency fields at once."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    # Create initial dependency
    create_resp = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
            "strength": "soft",
            "scope": "next_occurrence",
        },
    )
    assert create_resp.status_code == 201
    dep_id = create_resp.json()["id"]

    # Update multiple fields
    response = await client.patch(
        f"/dependencies/{dep_id}",
        json={
            "strength": "hard",
            "scope": "within_window",
            "validity_window_minutes": 120,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["strength"] == "hard"
    assert data["scope"] == "within_window"
    assert data["validity_window_minutes"] == 120


@pytest.mark.asyncio
async def test_list_dependencies_with_multiple_filters(client: AsyncClient):
    """Test listing dependencies with various filter combinations."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")
    task_c = await create_task(client, "Task C")

    # Create A→B
    resp1 = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
            "strength": "soft",
            "scope": "next_occurrence",
        },
    )
    assert resp1.status_code == 201

    # Create A→C
    resp2 = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_c["id"],
            "strength": "hard",
            "scope": "next_occurrence",
        },
    )
    assert resp2.status_code == 201

    # List all for user
    response = await client.get("/dependencies")
    assert response.status_code == 200
    assert len(response.json()["rules"]) >= 2  # May include other tests' deps

    # Filter by task_id (should find both since A is involved)
    response = await client.get("/dependencies", params={"task_id": task_a["id"]})
    assert response.status_code == 200
    assert len(response.json()["rules"]) >= 2


@pytest.mark.asyncio
async def test_get_dependency_with_task_info(client: AsyncClient):
    """Test getting dependency includes task information."""
    task_a = await create_task(client, "Upstream Task")
    task_b = await create_task(client, "Downstream Task")

    create_resp = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
            "strength": "soft",
            "scope": "next_occurrence",
        },
    )
    assert create_resp.status_code == 201
    dep_id = create_resp.json()["id"]

    # Get and verify task info is included (nested in upstream_task/downstream_task)
    response = await client.get(f"/dependencies/{dep_id}")
    assert response.status_code == 200
    data = response.json()
    # Task info is nested in upstream_task and downstream_task objects
    assert data["upstream_task"]["title"] == "Upstream Task"
    assert data["downstream_task"]["title"] == "Downstream Task"


@pytest.mark.asyncio
async def test_validate_dependency_with_multiple_existing(client: AsyncClient):
    """Test validation when there are multiple existing dependencies."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")
    task_c = await create_task(client, "Task C")

    # Create A→B and B→C
    await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
            "strength": "soft",
            "scope": "next_occurrence",
        },
    )
    await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_b["id"],
            "downstream_task_id": task_c["id"],
            "strength": "soft",
            "scope": "next_occurrence",
        },
    )

    # Validate A→C (should be valid, no direct cycle even with existing chain)
    response = await client.post(
        "/dependencies/validate",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_c["id"],
        },
    )
    assert response.status_code == 200
    assert response.json()["valid"] is True

    # Validate C→A (would create transitive cycle A→B→C→A)
    response = await client.post(
        "/dependencies/validate",
        json={
            "upstream_task_id": task_c["id"],
            "downstream_task_id": task_a["id"],
        },
    )
    assert response.status_code == 200
    # C→A creates a cycle since A→B→C exists
    assert response.json()["valid"] is False


@pytest.mark.asyncio
async def test_create_dependency_with_high_occurrence_count(client: AsyncClient):
    """Test creating dependency with required_occurrence_count > 1."""
    task_a = await create_task(client, "Task A")
    task_b = await create_task(client, "Task B")

    # Create with count
    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": task_a["id"],
            "downstream_task_id": task_b["id"],
            "strength": "hard",
            "scope": "within_window",
            "required_occurrence_count": 5,
            "validity_window_minutes": 480,
        },
    )
    assert response.status_code == 201
    assert response.json()["required_occurrence_count"] == 5


# ---- migrated from tests/mocked/test_services_dependencies_migrated.py ----

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
async def test_assistant_session_lifecycle(client: AsyncClient):
    """Test full assistant session lifecycle."""
    # Create session
    create_resp = await client.post(
        "/assistant/sessions",
        json={"context_mode": "general"},
    )
    assert create_resp.status_code == 201
    session_id = create_resp.json()["id"]

    # Get session
    get_resp = await client.get(f"/assistant/sessions/{session_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == session_id
    assert get_resp.json()["context_mode"] == "general"

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
    assert response.status_code == 422

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


# ---- migrated from tests/integration/test_api_helpers_dependencies.py ----

"""Integration coverage for dependencies helper behavior."""

import pytest
from datetime import datetime, timedelta, timezone
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_dependency_soft_dependency(client: AsyncClient):
    """Test creating a soft (non-hard) dependency."""
    goal = await client.post("/goals", json={"title": "Soft Dep Goal"})
    goal_id = goal.json()["id"]

    task1 = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Soft Up", "duration_minutes": 30},
    )
    t1_id = task1.json()["id"]

    task2 = await client.post(
        "/tasks",
        json={"goal_id": goal_id, "title": "Soft Down", "duration_minutes": 30},
    )
    t2_id = task2.json()["id"]

    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": t1_id,
            "downstream_task_id": t2_id,
            "rule_type": "completion",
            "is_hard": False,
        },
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_dependency_time_rule(client: AsyncClient):
    """Test creating a time-based dependency."""
    goal = await client.post("/goals", json={"title": "Time Dep Goal"})
    goal_id = goal.json()["id"]

    now = datetime.now(timezone.utc)

    task1 = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Time Up",
            "duration_minutes": 30,
            "scheduled_at": now.isoformat(),
        },
    )
    t1_id = task1.json()["id"]

    task2 = await client.post(
        "/tasks",
        json={
            "goal_id": goal_id,
            "title": "Time Down",
            "duration_minutes": 30,
            "scheduled_at": (now + timedelta(hours=1)).isoformat(),
        },
    )
    t2_id = task2.json()["id"]

    response = await client.post(
        "/dependencies",
        json={
            "upstream_task_id": t1_id,
            "downstream_task_id": t2_id,
            "strength": "hard",
            "scope": "next_occurrence",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["upstream_task_id"] == t1_id
    assert payload["downstream_task_id"] == t2_id
    assert payload["strength"] == "hard"


# ---- migrated from tests/integration/test_skip_dependencies.py ----

"""
Integration tests for skip dependency impact and skip-chain (Phase 4i-4).
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestSkipSoftDownstream:
    """Skipping upstream with only soft downstream does not require confirmation."""

    async def test_skip_upstream_soft_downstream_no_preview(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post("/tasks", json={"title": "Soft Up"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "Soft Down"}, headers=auth_headers)
        uid, did = up.json()["id"], down.json()["id"]
        dep = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": did,
                "strength": "soft",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        assert dep.status_code == 201

        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        body = sk.json()
        assert body.get("status") == "skipped"
        assert "id" in body
        assert body["id"] == uid


@pytest.mark.asyncio
class TestSkipHardDownstream:
    """Hard downstream with required_count=1 triggers preview unless confirmed."""

    async def test_skip_hard_required_one_returns_has_dependents(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post("/tasks", json={"title": "Hard Up"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "Hard Down"}, headers=auth_headers)
        uid, did = up.json()["id"], down.json()["id"]
        dep = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": did,
                "strength": "hard",
                "scope": "next_occurrence",
                "required_occurrence_count": 1,
            },
            headers=auth_headers,
        )
        assert dep.status_code == 201

        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        body = sk.json()
        assert body["status"] == "has_dependents"
        assert len(body["affected_downstream"]) == 1
        assert body["affected_downstream"][0]["task_id"] == did
        assert body["affected_downstream"][0]["strength"] == "hard"
        topo = body.get("transitive_hard_dependents_toposort") or []
        assert [x["task_id"] for x in topo] == [did]

    async def test_skip_hard_preview_transitive_chain_topo_order(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """A -> B -> C hard: preview includes full downstream chain B then C."""
        a = await client.post("/tasks", json={"title": "Prev A"}, headers=auth_headers)
        b = await client.post("/tasks", json={"title": "Prev B"}, headers=auth_headers)
        c = await client.post("/tasks", json={"title": "Prev C"}, headers=auth_headers)
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
        sk = await client.post(f"/tasks/{aid}/skip", json={}, headers=auth_headers)
        assert sk.status_code == 200
        body = sk.json()
        assert body["status"] == "has_dependents"
        topo = body["transitive_hard_dependents_toposort"]
        assert [x["task_id"] for x in topo] == [bid, cid]
        assert [x["task_title"] for x in topo] == ["Prev B", "Prev C"]

    async def test_skip_hard_preview_transitive_omits_still_completed_downstream(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """A→B→C hard: after full complete, reopen only A and B — preview lists B, not C."""
        a = await client.post("/tasks", json={"title": "Reo A"}, headers=auth_headers)
        b = await client.post("/tasks", json={"title": "Reo B"}, headers=auth_headers)
        c = await client.post("/tasks", json={"title": "Reo C"}, headers=auth_headers)
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
        for tid in (aid, bid, cid):
            co = await client.post(f"/tasks/{tid}/complete", json={}, headers=auth_headers)
            assert co.status_code == 200, co.text
        for tid in (aid, bid):
            ro = await client.post(f"/tasks/{tid}/reopen", json={}, headers=auth_headers)
            assert ro.status_code == 200, ro.text
        sk = await client.post(f"/tasks/{aid}/skip", json={}, headers=auth_headers)
        assert sk.status_code == 200, sk.text
        body = sk.json()
        assert body["status"] == "has_dependents"
        topo_ids = [x["task_id"] for x in body["transitive_hard_dependents_toposort"]]
        assert topo_ids == [bid]
        assert cid not in topo_ids

    async def test_skip_hard_confirm_proceed_persists(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post("/tasks", json={"title": "Hard Up 2"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "Hard Down 2"}, headers=auth_headers)
        uid, did = up.json()["id"], down.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": did,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )

        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={"confirm_proceed": True, "reason": "ok"},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        body = sk.json()
        assert body["status"] == "skipped"
        assert body["id"] == uid

    async def test_skip_hard_required_two_no_preview_when_not_impossible(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Count>1 without impossibility heuristic does not block skip."""
        up = await client.post("/tasks", json={"title": "H Up 3"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "H Down 3"}, headers=auth_headers)
        uid, did = up.json()["id"], down.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": did,
                "strength": "hard",
                "scope": "within_window",
                "required_occurrence_count": 2,
                "validity_window_minutes": 10080,
            },
            headers=auth_headers,
        )

        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        assert sk.json()["status"] == "skipped"

    async def test_skip_hard_count_impossible_within_window_previews(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """required_count=2 in a 1-day window: skipping uses the only slot → preview."""
        up = await client.post("/tasks", json={"title": "Tight Up"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "Tight Down"}, headers=auth_headers)
        uid = up.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": down.json()["id"],
                "strength": "hard",
                "scope": "within_window",
                "required_occurrence_count": 2,
                "validity_window_minutes": 1440,
            },
            headers=auth_headers,
        )
        sk = await client.post(f"/tasks/{uid}/skip", json={}, headers=auth_headers)
        assert sk.status_code == 200
        assert sk.json()["status"] == "has_dependents"


@pytest.mark.asyncio
class TestSkipChain:
    """POST /tasks/{id}/skip-chain cascade."""

    async def test_skip_chain_rejects_without_cascade_flag(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        t = await client.post("/tasks", json={"title": "Solo"}, headers=auth_headers)
        tid = t.json()["id"]
        resp = await client.post(
            f"/tasks/{tid}/skip-chain",
            json={"cascade_skip": False},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    async def test_skip_chain_linear_order(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """A -> B -> C hard: chain returns three task responses in order root, B, C."""
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
                },
                headers=auth_headers,
            )
            assert r.status_code == 201

        resp = await client.post(
            f"/tasks/{aid}/skip-chain",
            json={"cascade_skip": True, "reason": "vacation"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 3
        assert [r["id"] for r in rows] == [aid, bid, cid]
        assert all(r["status"] == "skipped" for r in rows)

    async def test_skip_chain_diamond_order(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """A -> B, A -> C, B -> D, C -> D: topo order has B,C before D."""
        a = await client.post("/tasks", json={"title": "D A"}, headers=auth_headers)
        b = await client.post("/tasks", json={"title": "D B"}, headers=auth_headers)
        c = await client.post("/tasks", json={"title": "D C"}, headers=auth_headers)
        d = await client.post("/tasks", json={"title": "D D"}, headers=auth_headers)
        aid, bid, cid, did = (
            a.json()["id"],
            b.json()["id"],
            c.json()["id"],
            d.json()["id"],
        )
        for pair in ((aid, bid), (aid, cid), (bid, did), (cid, did)):
            r = await client.post(
                "/dependencies",
                json={
                    "upstream_task_id": pair[0],
                    "downstream_task_id": pair[1],
                    "strength": "hard",
                    "scope": "next_occurrence",
                },
                headers=auth_headers,
            )
            assert r.status_code == 201

        resp = await client.post(
            f"/tasks/{aid}/skip-chain",
            json={"cascade_skip": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()]
        assert ids[0] == aid
        assert set(ids[1:3]) == {bid, cid}
        assert ids[3] == did

    async def test_skip_chain_single_task_no_dependents(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        t = await client.post("/tasks", json={"title": "Lonely"}, headers=auth_headers)
        tid = t.json()["id"]
        resp = await client.post(
            f"/tasks/{tid}/skip-chain",
            json={"cascade_skip": True},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1


@pytest.mark.asyncio
class TestSkipRecurring:
    """Recurring skip with scheduled_for."""

    async def test_recurring_skip_hard_preview(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post(
            "/tasks",
            json={
                "title": "Rec Up",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "recurrence_behavior": "essential",
                "scheduling_mode": "date_only",
            },
            headers=auth_headers,
        )
        assert up.status_code == 201
        down = await client.post("/tasks", json={"title": "Rec Down"}, headers=auth_headers)
        uid, did = up.json()["id"], down.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": did,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        when = datetime(2026, 4, 10, 12, 0, 0, tzinfo=timezone.utc)
        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={"scheduled_for": when.isoformat()},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        assert sk.json()["status"] == "has_dependents"

    async def test_recurring_skip_confirm(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post(
            "/tasks",
            json={
                "title": "Rec Up 2",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "recurrence_behavior": "essential",
                "scheduling_mode": "date_only",
            },
            headers=auth_headers,
        )
        down = await client.post("/tasks", json={"title": "Rec Down 2"}, headers=auth_headers)
        uid = up.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": down.json()["id"],
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        when = datetime(2026, 4, 11, 9, 0, 0, tzinfo=timezone.utc)
        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={"confirm_proceed": True, "scheduled_for": when.isoformat()},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        assert sk.json()["skipped_for_today"] is True


@pytest.mark.asyncio
class TestSkipMixedRules:
    """Soft + hard on same upstream: hard wins."""

    async def test_soft_and_hard_downstream_previews_for_hard(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post("/tasks", json={"title": "Mix Up"}, headers=auth_headers)
        sdown = await client.post("/tasks", json={"title": "Mix Soft"}, headers=auth_headers)
        hdown = await client.post("/tasks", json={"title": "Mix Hard"}, headers=auth_headers)
        uid, sid, hid = up.json()["id"], sdown.json()["id"], hdown.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": sid,
                "strength": "soft",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": hid,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )

        sk = await client.post(f"/tasks/{uid}/skip", json={}, headers=auth_headers)
        assert sk.status_code == 200
        body = sk.json()
        assert body["status"] == "has_dependents"
        affected_ids = {x["task_id"] for x in body["affected_downstream"]}
        assert hid in affected_ids
        assert sid not in affected_ids


@pytest.mark.asyncio
class TestSkipPreviewShape:
    """Response shape checks."""

    async def test_preview_weekly_downstream_affected_occurrences(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        """Weekly recurring downstream uses affected_occurrences estimate of 1."""
        up = await client.post("/tasks", json={"title": "Wk Up"}, headers=auth_headers)
        down = await client.post(
            "/tasks",
            json={
                "title": "Wk Down",
                "is_recurring": True,
                "recurrence_rule": "FREQ=WEEKLY;BYDAY=MO",
                "recurrence_behavior": "essential",
                "scheduling_mode": "date_only",
            },
            headers=auth_headers,
        )
        uid, did = up.json()["id"], down.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": did,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        sk = await client.post(f"/tasks/{uid}/skip", json={}, headers=auth_headers)
        occ = sk.json()["affected_downstream"][0]["affected_occurrences"]
        assert occ == 1

    async def test_preview_contains_rule_and_occurrence_estimate(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post(
            "/tasks",
            json={
                "title": "Shape Up",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "recurrence_behavior": "essential",
                "scheduling_mode": "date_only",
            },
            headers=auth_headers,
        )
        down = await client.post(
            "/tasks",
            json={
                "title": "Shape Down",
                "is_recurring": True,
                "recurrence_rule": "FREQ=DAILY",
                "recurrence_behavior": "essential",
                "scheduling_mode": "date_only",
            },
            headers=auth_headers,
        )
        uid, did = up.json()["id"], down.json()["id"]
        dep = await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": did,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        rid = dep.json()["id"]

        sk = await client.post(f"/tasks/{uid}/skip", json={}, headers=auth_headers)
        row = sk.json()["affected_downstream"][0]
        assert row["rule_id"] == rid
        assert row["affected_occurrences"] >= 1


@pytest.mark.asyncio
class TestSkipExtra:
    """Additional coverage for reasons and flags."""

    async def test_confirm_proceed_false_explicit_still_previews(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post("/tasks", json={"title": "E1"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "E2"}, headers=auth_headers)
        uid, did = up.json()["id"], down.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": did,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={"confirm_proceed": False},
            headers=auth_headers,
        )
        assert sk.json()["status"] == "has_dependents"

    async def test_skip_reason_on_confirm(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        up = await client.post("/tasks", json={"title": "E3"}, headers=auth_headers)
        down = await client.post("/tasks", json={"title": "E4"}, headers=auth_headers)
        uid = up.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": uid,
                "downstream_task_id": down.json()["id"],
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        sk = await client.post(
            f"/tasks/{uid}/skip",
            json={"confirm_proceed": True, "reason": "rain"},
            headers=auth_headers,
        )
        assert sk.status_code == 200
        assert sk.json()["skip_reason"] == "rain"

    async def test_skip_chain_reason_on_responses(
        self, client: AsyncClient, auth_headers: dict[str, str]
    ) -> None:
        a = await client.post("/tasks", json={"title": "R1"}, headers=auth_headers)
        b = await client.post("/tasks", json={"title": "R2"}, headers=auth_headers)
        aid, bid = a.json()["id"], b.json()["id"]
        await client.post(
            "/dependencies",
            json={
                "upstream_task_id": aid,
                "downstream_task_id": bid,
                "strength": "hard",
                "scope": "next_occurrence",
            },
            headers=auth_headers,
        )
        resp = await client.post(
            f"/tasks/{aid}/skip-chain",
            json={"cascade_skip": True, "reason": "sick"},
            headers=auth_headers,
        )
        for row in resp.json():
            assert row["skip_reason"] == "sick"
