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
