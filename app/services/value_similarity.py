from typing import Any
import json
import numpy as np
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.llm import llm_client
from app.models.value import Value
from app.models.embedding import Embedding

EMBEDDING_MODEL = "text-embedding-3-large"
SIMILARITY_THRESHOLD = 0.75
LLM_FALLBACK_THRESHOLD = 0.6


async def llm_overlap_check(
    proposed_statement: str,
    existing_statements: list[str],
) -> dict[str, Any] | None:
    if not existing_statements:
        return None

    prompt = (
        "Decide if the new value clearly overlaps in meaning with any existing value. "
        "Return JSON with keys: overlap (true/false) and most_similar (string or null).\n\n"
        f"New value: {proposed_statement}\n"
        "Existing values:\n"
        + "\n".join([f"- {statement}" for statement in existing_statements])
    )

    messages = [
        {
            "role": "system",
            "content": "You detect obvious semantic overlap between value statements.",
        },
        {"role": "user", "content": prompt},
    ]

    response = await llm_client.chat_completion(
        messages=messages,
        temperature=0,
        response_format={"type": "json_object"},
        max_tokens=200,
    )

    content = response["choices"][0]["message"].get("content") or "{}"
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        return None

    overlap = bool(parsed.get("overlap"))
    most_similar = parsed.get("most_similar")
    if overlap and isinstance(most_similar, str) and most_similar.strip():
        return {"overlap": True, "most_similar": most_similar.strip()}

    return None


async def compute_value_similarity(
    db: AsyncSession,
    user_id: str,
    proposed_statement: str,
    exclude_value_id: str | None = None,
) -> tuple[dict[str, Any] | None, list[float]]:
    """Compute similarity against existing values and return best match plus embedding."""
    result = await db.execute(
        select(Value)
        .where(Value.user_id == user_id)
        .options(selectinload(Value.revisions))
    )
    existing_values = result.scalars().all()

    proposed_embedding = await llm_client.create_embedding(
        proposed_statement,
        model=EMBEDDING_MODEL,
    )
    proposed_vec = np.array(proposed_embedding)

    if not existing_values:
        return None, proposed_embedding

    best_match = None
    existing_statements = []

    for value in existing_values:
        if exclude_value_id and value.id == exclude_value_id:
            continue
        if not value.active_revision_id:
            continue

        active_rev = next((r for r in value.revisions if r.id == value.active_revision_id), None)
        if not active_rev:
            continue

        existing_statements.append(active_rev.statement)

        embedding_result = await db.execute(
            select(Embedding)
            .where(
                Embedding.entity_type == "value_revision",
                Embedding.entity_id == active_rev.id,
            )
        )
        existing_embedding_obj = embedding_result.scalar_one_or_none()

        if not existing_embedding_obj:
            existing_emb = await llm_client.create_embedding(
                active_rev.statement,
                model=EMBEDDING_MODEL,
            )
            existing_embedding_obj = Embedding(
                entity_type="value_revision",
                entity_id=active_rev.id,
                model=EMBEDDING_MODEL,
                dims=len(existing_emb),
                embedding=existing_emb,
            )
            db.add(existing_embedding_obj)
            await db.flush()

        existing_vec = np.array(existing_embedding_obj.embedding)
        similarity = np.dot(proposed_vec, existing_vec) / (
            np.linalg.norm(proposed_vec) * np.linalg.norm(existing_vec)
        )

        if best_match is None or similarity > best_match["similarity_score"]:
            best_match = {
                "similar_value_id": value.id,
                "similar_value_revision_id": active_rev.id,
                "similarity_score": float(similarity),
                "similar_statement": active_rev.statement,
            }

    if not best_match:
        return None, proposed_embedding

    if best_match["similarity_score"] >= SIMILARITY_THRESHOLD:
        return best_match, proposed_embedding

    if best_match["similarity_score"] >= LLM_FALLBACK_THRESHOLD:
        try:
            llm_result = await llm_overlap_check(proposed_statement, existing_statements)
        except Exception:
            llm_result = None

        if llm_result:
            most_similar = llm_result["most_similar"]
            matched = None
            for value in existing_values:
                if not value.active_revision_id:
                    continue
                active_rev = next((r for r in value.revisions if r.id == value.active_revision_id), None)
                if active_rev and active_rev.statement == most_similar:
                    matched = {
                        "similar_value_id": value.id,
                        "similar_value_revision_id": active_rev.id,
                        "similarity_score": float(best_match["similarity_score"]),
                        "similar_statement": active_rev.statement,
                    }
                    break

            if matched:
                return matched, proposed_embedding

    return None, proposed_embedding
