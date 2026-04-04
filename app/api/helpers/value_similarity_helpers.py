"""Similarity-related helper functions for values API."""

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.embedding import Embedding
from app.models.value import Value, ValueRevision
from app.schemas.values import ValueInsight, ValueResponse
from app.services.value_similarity import EMBEDDING_MODEL, compute_value_similarity


def build_similarity_insight(similar_statement: str, match: dict[str, Any]) -> ValueInsight:
    """Build a ValueInsight object from a similarity match."""
    return ValueInsight(
        type="similar_value",
        similar_value_id=match["similar_value_id"],
        similar_value_revision_id=match["similar_value_revision_id"],
        similarity_score=match["similarity_score"],
        message=(
            f'This sounds a bit like "{similar_statement}". '
            "Totally fine - just flagging it in case you want to refine later."
        ),
    )


def build_value_response_with_insight(
    value: Value,
    revision_lookup: dict[str, ValueRevision],
) -> ValueResponse:
    """Build a ValueResponse with similarity insight if applicable."""
    response = ValueResponse.model_validate(value)

    active_rev_obj = next(
        (r for r in value.revisions if r.id == value.active_revision_id),
        None,
    )
    if not active_rev_obj:
        return response

    if not active_rev_obj.similar_value_revision_id:
        return response

    if active_rev_obj.similarity_acknowledged:
        return response

    similar_rev = revision_lookup.get(active_rev_obj.similar_value_revision_id)
    if not similar_rev:
        return response

    insight = build_similarity_insight(
        similar_rev.statement,
        {
            "similar_value_id": str(similar_rev.value_id),
            "similar_value_revision_id": str(similar_rev.id),
            "similarity_score": float(active_rev_obj.similarity_score or 0),
        },
    )

    return response.model_copy(update={"insights": [insight]})


async def process_value_similarity(
    db: AsyncSession,
    user_id: str,
    statement: str,
    revision: ValueRevision,
    exclude_value_id: str,
) -> ValueInsight | None:
    """
    Compute value similarity, update revision, and create embedding if needed.

    Returns a ValueInsight if a similar value was found, None otherwise.
    """
    insight = None

    try:
        match, proposed_embedding = await compute_value_similarity(
            db,
            user_id,
            statement,
            exclude_value_id=exclude_value_id,
        )
        if match:
            revision.similar_value_revision_id = match["similar_value_revision_id"]
            revision.similarity_score = Decimal(str(match["similarity_score"]))
            revision.similarity_acknowledged = False
            insight = build_similarity_insight(match["similar_statement"], match)

        # Check if embedding already exists before creating
        if proposed_embedding:
            existing_embedding = await db.execute(
                select(Embedding).where(
                    Embedding.entity_type == "value_revision",
                    Embedding.entity_id == revision.id,
                    Embedding.model == EMBEDDING_MODEL,
                )
            )
            if not existing_embedding.scalar_one_or_none():
                db.add(
                    Embedding(
                        entity_type="value_revision",
                        entity_id=revision.id,
                        model=EMBEDDING_MODEL,
                        dims=len(proposed_embedding),
                        embedding=proposed_embedding,
                    )
                )
                await db.flush()
    except Exception:
        insight = None

    return insight
