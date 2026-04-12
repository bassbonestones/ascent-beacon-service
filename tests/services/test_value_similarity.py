"""Tests for value_similarity service."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import numpy as np

from app.services.value_similarity import (
    compute_value_similarity,
    llm_overlap_check,
    SIMILARITY_THRESHOLD,
    LLM_FALLBACK_THRESHOLD,
)


# ============================================================================
# Local cosine_similarity for testing
# ============================================================================


def cosine_similarity(vec1: np.ndarray, vec2: np.ndarray) -> float:
    """Compute cosine similarity between two vectors."""
    return np.dot(vec1, vec2) / (np.linalg.norm(vec1) * np.linalg.norm(vec2))


# ============================================================================
# cosine_similarity Tests
# ============================================================================


def test_cosine_similarity_identical_vectors():
    """Test that identical vectors have similarity of 1.0."""
    vec = np.array([1.0, 2.0, 3.0])
    result = cosine_similarity(vec, vec)
    assert abs(result - 1.0) < 0.0001


def test_cosine_similarity_orthogonal_vectors():
    """Test that orthogonal vectors have similarity of 0.0."""
    vec1 = np.array([1.0, 0.0, 0.0])
    vec2 = np.array([0.0, 1.0, 0.0])
    result = cosine_similarity(vec1, vec2)
    assert abs(result) < 0.0001


def test_cosine_similarity_opposite_vectors():
    """Test that opposite vectors have similarity of -1.0."""
    vec1 = np.array([1.0, 0.0, 0.0])
    vec2 = np.array([-1.0, 0.0, 0.0])
    result = cosine_similarity(vec1, vec2)
    assert abs(result - (-1.0)) < 0.0001


def test_cosine_similarity_similar_vectors():
    """Test similarity of similar vectors."""
    vec1 = np.array([1.0, 2.0, 3.0])
    vec2 = np.array([1.1, 2.1, 3.1])
    result = cosine_similarity(vec1, vec2)
    # Should be very high (close to 1.0)
    assert result > 0.99


def test_cosine_similarity_partial_overlap():
    """Test similarity of partially overlapping vectors."""
    vec1 = np.array([1.0, 0.0, 0.0, 0.0])
    vec2 = np.array([1.0, 1.0, 0.0, 0.0])
    result = cosine_similarity(vec1, vec2)
    # cos(45 degrees) = 0.707...
    assert 0.7 < result < 0.72


# ============================================================================
# llm_overlap_check Tests
# ============================================================================


@pytest.mark.asyncio
async def test_llm_overlap_check_empty_existing():
    """Test LLM overlap check with no existing statements."""
    result = await llm_overlap_check("I value honesty", [])
    assert result is None


@pytest.mark.asyncio
async def test_llm_overlap_check_overlap_detected():
    """Test LLM overlap check when overlap is detected."""
    mock_response = {
        "choices": [{
            "message": {
                "content": '{"overlap": true, "most_similar": "I value being honest"}'
            }
        }]
    }
    
    with patch(
        "app.services.value_similarity.llm_client.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await llm_overlap_check(
            "I value honesty",
            ["I value being honest", "I value creativity"]
        )
    
    assert result is not None
    assert result["overlap"] is True
    assert result["most_similar"] == "I value being honest"


@pytest.mark.asyncio
async def test_llm_overlap_check_no_overlap():
    """Test LLM overlap check when no overlap is detected."""
    mock_response = {
        "choices": [{
            "message": {
                "content": '{"overlap": false, "most_similar": null}'
            }
        }]
    }
    
    with patch(
        "app.services.value_similarity.llm_client.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await llm_overlap_check(
            "I value adventure",
            ["I value stability", "I value routine"]
        )
    
    assert result is None


@pytest.mark.asyncio
async def test_llm_overlap_check_invalid_json_response():
    """Test LLM overlap check when response is invalid JSON."""
    mock_response = {
        "choices": [{
            "message": {
                "content": "This is not JSON"
            }
        }]
    }
    
    with patch(
        "app.services.value_similarity.llm_client.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await llm_overlap_check(
            "I value honesty",
            ["I value being honest"]
        )
    
    assert result is None


@pytest.mark.asyncio
async def test_llm_overlap_check_empty_content():
    """Test LLM overlap check when response content is empty."""
    mock_response = {
        "choices": [{
            "message": {
                "content": None
            }
        }]
    }
    
    with patch(
        "app.services.value_similarity.llm_client.chat_completion",
        new_callable=AsyncMock,
        return_value=mock_response,
    ):
        result = await llm_overlap_check(
            "I value honesty",
            ["I value being honest"]
        )
    
    # Empty content defaults to "{}" which has no overlap
    assert result is None


# ============================================================================
# compute_value_similarity (mocked DB / embeddings)
# ============================================================================


@pytest.mark.asyncio
async def test_compute_value_similarity_no_existing_values() -> None:
    """No Value rows → early return with proposed embedding only."""
    mock_db = AsyncMock()
    exec_vals = MagicMock()
    exec_vals.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = exec_vals
    prop_emb = [0.3, 0.4, 0.5]
    with patch(
        "app.services.value_similarity.llm_client.create_embedding",
        new_callable=AsyncMock,
        return_value=prop_emb,
    ):
        match, emb = await compute_value_similarity(mock_db, "user-1", "hello", None)
    assert match is None
    assert emb == prop_emb


@pytest.mark.asyncio
async def test_compute_value_similarity_excludes_value_id() -> None:
    """exclude_value_id skips that value."""
    v = MagicMock()
    v.id = "skip-me"
    v.active_revision_id = "r1"
    rev = MagicMock()
    rev.id = "r1"
    rev.statement = "x"
    v.revisions = [rev]

    mock_db = AsyncMock()
    exec_vals = MagicMock()
    exec_vals.scalars.return_value.all.return_value = [v]
    mock_db.execute.return_value = exec_vals

    with patch(
        "app.services.value_similarity.llm_client.create_embedding",
        new_callable=AsyncMock,
        return_value=[1.0, 0.0],
    ):
        match, _ = await compute_value_similarity(
            mock_db, "user-1", "hello", "skip-me"
        )
    assert match is None


@pytest.mark.asyncio
async def test_compute_value_similarity_above_threshold_uses_embedding_row() -> None:
    """High cosine similarity returns best_match without LLM fallback."""
    v = MagicMock()
    v.id = "v1"
    v.active_revision_id = "rev1"
    rev = MagicMock()
    rev.id = "rev1"
    rev.statement = "aligned"
    v.revisions = [rev]

    emb_row = MagicMock()
    emb_row.embedding = [1.0, 0.0]

    exec_vals = MagicMock()
    exec_vals.scalars.return_value.all.return_value = [v]
    exec_emb = MagicMock()
    exec_emb.scalar_one_or_none.return_value = emb_row

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[exec_vals, exec_emb])

    with patch(
        "app.services.value_similarity.llm_client.create_embedding",
        new_callable=AsyncMock,
        return_value=[1.0, 0.0],
    ):
        match, _ = await compute_value_similarity(mock_db, "user-1", "aligned", None)
    assert match is not None
    assert match["similar_value_id"] == "v1"
    assert match["similarity_score"] == 1.0


@pytest.mark.asyncio
async def test_compute_value_similarity_creates_missing_embedding_row() -> None:
    """When no Embedding row exists, create via LLM and persist."""
    v = MagicMock()
    v.id = "v1"
    v.active_revision_id = "rev1"
    rev = MagicMock()
    rev.id = "rev1"
    rev.statement = "needs emb"
    v.revisions = [rev]

    exec_vals = MagicMock()
    exec_vals.scalars.return_value.all.return_value = [v]
    exec_emb = MagicMock()
    exec_emb.scalar_one_or_none.return_value = None

    mock_db = MagicMock()
    mock_db.execute = AsyncMock(side_effect=[exec_vals, exec_emb])
    mock_db.flush = AsyncMock()

    new_emb = [1.0, 0.0]
    with patch(
        "app.services.value_similarity.llm_client.create_embedding",
        new_callable=AsyncMock,
        return_value=new_emb,
    ):
        match, _ = await compute_value_similarity(mock_db, "user-1", "needs emb", None)
    assert match is not None
    mock_db.add.assert_called_once()
    mock_db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_compute_value_similarity_skips_without_active_revision_id() -> None:
    """Values with no active_revision_id are ignored (line 90–91)."""
    v = MagicMock()
    v.id = "v1"
    v.active_revision_id = None
    v.revisions = []

    exec_vals = MagicMock()
    exec_vals.scalars.return_value.all.return_value = [v]
    mock_db = AsyncMock()
    mock_db.execute.return_value = exec_vals

    with patch(
        "app.services.value_similarity.llm_client.create_embedding",
        new_callable=AsyncMock,
        return_value=[1.0, 0.0],
    ):
        match, _ = await compute_value_similarity(mock_db, "user-1", "x", None)
    assert match is None


@pytest.mark.asyncio
async def test_compute_value_similarity_skips_when_active_rev_not_found() -> None:
    """active_revision_id set but revision not in revisions list → continue."""
    v = MagicMock()
    v.id = "v1"
    v.active_revision_id = "ghost"
    v.revisions = []

    exec_vals = MagicMock()
    exec_vals.scalars.return_value.all.return_value = [v]
    mock_db = AsyncMock()
    mock_db.execute.return_value = exec_vals

    with patch(
        "app.services.value_similarity.llm_client.create_embedding",
        new_callable=AsyncMock,
        return_value=[1.0, 0.0],
    ):
        match, emb = await compute_value_similarity(mock_db, "user-1", "x", None)
    assert match is None
    assert emb == [1.0, 0.0]


@pytest.mark.asyncio
async def test_compute_value_similarity_llm_overlap_raises_returns_none() -> None:
    """Exception from llm_overlap_check in fallback band yields no match."""
    v = MagicMock()
    v.id = "v1"
    v.active_revision_id = "rev1"
    rev = MagicMock()
    rev.id = "rev1"
    rev.statement = "s"
    v.revisions = [rev]

    b = float(np.sqrt(1 - 0.65**2))
    emb_row = MagicMock()
    emb_row.embedding = [0.65, b]

    exec_vals = MagicMock()
    exec_vals.scalars.return_value.all.return_value = [v]
    exec_emb = MagicMock()
    exec_emb.scalar_one_or_none.return_value = emb_row

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[exec_vals, exec_emb])

    with patch(
        "app.services.value_similarity.llm_client.create_embedding",
        new_callable=AsyncMock,
        return_value=[1.0, 0.0],
    ):
        with patch(
            "app.services.value_similarity.llm_overlap_check",
            new_callable=AsyncMock,
            side_effect=RuntimeError("llm down"),
        ):
            match, _ = await compute_value_similarity(mock_db, "user-1", "x", None)
    assert match is None


@pytest.mark.asyncio
async def test_compute_value_similarity_llm_no_statement_match() -> None:
    """LLM most_similar does not match any revision statement → no match."""
    v = MagicMock()
    v.id = "v1"
    v.active_revision_id = "rev1"
    rev = MagicMock()
    rev.id = "rev1"
    rev.statement = "only this"
    v.revisions = [rev]

    b = float(np.sqrt(1 - 0.65**2))
    emb_row = MagicMock()
    emb_row.embedding = [0.65, b]

    exec_vals = MagicMock()
    exec_vals.scalars.return_value.all.return_value = [v]
    exec_emb = MagicMock()
    exec_emb.scalar_one_or_none.return_value = emb_row

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[exec_vals, exec_emb])

    async def wrong_overlap(_p: str, _ex: list[str]) -> dict[str, object]:
        return {"overlap": True, "most_similar": "something else"}

    with patch(
        "app.services.value_similarity.llm_client.create_embedding",
        new_callable=AsyncMock,
        return_value=[1.0, 0.0],
    ):
        with patch(
            "app.services.value_similarity.llm_overlap_check",
            new_callable=AsyncMock,
            side_effect=wrong_overlap,
        ):
            match, _ = await compute_value_similarity(mock_db, "user-1", "x", None)
    assert match is None


@pytest.mark.asyncio
async def test_compute_value_similarity_llm_fallback_branch() -> None:
    """Similarity in [LLM_FALLBACK, SIMILARITY_THRESHOLD) may resolve via LLM."""
    v_inactive = MagicMock()
    v_inactive.active_revision_id = None
    v_inactive.revisions = []

    v = MagicMock()
    v.id = "v1"
    v.active_revision_id = "rev1"
    rev = MagicMock()
    rev.id = "rev1"
    rev.statement = "exact llm match"
    v.revisions = [rev]

    # Unit vectors with cosine ~0.65 (between 0.6 and 0.75)
    b = float(np.sqrt(1 - 0.65**2))
    proposed = [1.0, 0.0]
    existing = [0.65, b]

    emb_row = MagicMock()
    emb_row.embedding = existing

    exec_vals = MagicMock()
    exec_vals.scalars.return_value.all.return_value = [v_inactive, v]
    exec_emb = MagicMock()
    exec_emb.scalar_one_or_none.return_value = emb_row

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=[exec_vals, exec_emb])

    llm_payload = {"overlap": True, "most_similar": "exact llm match"}

    async def fake_overlap(_p: str, _ex: list[str]) -> dict[str, object] | None:
        return llm_payload

    with patch(
        "app.services.value_similarity.llm_client.create_embedding",
        new_callable=AsyncMock,
        return_value=proposed,
    ):
        with patch(
            "app.services.value_similarity.llm_overlap_check",
            new_callable=AsyncMock,
            side_effect=fake_overlap,
        ):
            match, _ = await compute_value_similarity(mock_db, "user-1", "x", None)
    assert match is not None
    assert match["similar_statement"] == "exact llm match"


# ============================================================================
# Threshold Constants Tests
# ============================================================================


def test_similarity_threshold_is_reasonable():
    """Test that similarity threshold is a reasonable value."""
    assert 0.5 < SIMILARITY_THRESHOLD < 1.0


def test_llm_fallback_threshold_is_lower():
    """Test that LLM fallback threshold is lower than similarity threshold."""
    assert LLM_FALLBACK_THRESHOLD < SIMILARITY_THRESHOLD
    assert LLM_FALLBACK_THRESHOLD > 0.0
