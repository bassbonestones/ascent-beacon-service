"""Shared record_state values for goals and tasks (Phase 4j)."""

ACTIVE = "active"
PAUSED = "paused"
ARCHIVED = "archived"
DELETED = "deleted"

VALID_STATES = frozenset({ACTIVE, PAUSED, ARCHIVED, DELETED})


def list_query_states(*, include_paused: bool, include_archived: bool) -> list[str]:
    """States included in list endpoints (default: active only)."""
    states = [ACTIVE]
    if include_paused:
        states.append(PAUSED)
    if include_archived:
        states.append(ARCHIVED)
    return states
