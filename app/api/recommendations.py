from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from decimal import Decimal

from app.core.db import get_db
from app.core.auth import CurrentUser
from app.core.time import utc_now
from app.models.assistant_recommendation import AssistantRecommendation
from app.models.assistant_session import AssistantSession
from app.models.embedding import Embedding
from app.models.value import Value, ValueRevision
from app.schemas.recommendation_schema import (
    RecommendationResponse,
    AcceptRecommendationRequest,
    RejectRecommendationRequest,
)
from app.services.value_service import normalize_value_weights
from app.services.value_similarity import compute_value_similarity, EMBEDDING_MODEL

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("/session/{session_id}", response_model=list[RecommendationResponse], summary="Get session recommendations")
async def get_session_recommendations(
    session_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RecommendationResponse]:
    """Get all recommendations for a session."""
    # Verify session belongs to user
    session = await db.get(AssistantSession, session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Session not found")
    
    result = await db.execute(
        select(AssistantRecommendation)
        .where(AssistantRecommendation.session_id == session_id)
        .order_by(AssistantRecommendation.created_at.desc())
    )
    recommendations = result.scalars().all()
    
    return [RecommendationResponse.model_validate(r) for r in recommendations]


@router.get("/pending", response_model=list[RecommendationResponse], summary="Get pending recommendations")
async def get_pending_recommendations(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[RecommendationResponse]:
    """Get all pending recommendations for the user across all sessions."""
    result = await db.execute(
        select(AssistantRecommendation)
        .join(AssistantSession)
        .where(
            AssistantSession.user_id == user.id,
            AssistantRecommendation.status == "proposed",
        )
        .order_by(AssistantRecommendation.created_at.desc())
    )
    recommendations = result.scalars().all()
    
    return [RecommendationResponse.model_validate(r) for r in recommendations]


@router.post("/{recommendation_id}/accept", response_model=RecommendationResponse, summary="Accept recommendation")
async def accept_recommendation(
    recommendation_id: str,
    request: AcceptRecommendationRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecommendationResponse:
    """Accept and execute a recommendation."""
    try:
        # Get recommendation and verify ownership
        rec = await db.get(AssistantRecommendation, recommendation_id)
        if not rec:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        
        # Verify session belongs to user
        session = await db.get(AssistantSession, rec.session_id)
        if not session or session.user_id != user.id:
            raise HTTPException(status_code=404, detail="Recommendation not found")
        
        # Check if already processed
        if rec.status != "proposed":
            raise HTTPException(
                status_code=400,
                detail=f"Recommendation already {rec.status}",
            )
        
        # Execute the action based on proposed_action
        if rec.proposed_action == "create_value":
            # Extract payload
            statement = rec.payload.get("statement")
            if not statement:
                raise HTTPException(status_code=400, detail="Invalid payload: missing statement")
            
            # Get existing values count to determine weight
            existing_result = await db.execute(
                select(Value).where(Value.user_id == user.id)
            )
            existing_values = existing_result.scalars().all()
            
            # Check max values
            if len(existing_values) >= 6:
                rec.status = "rejected"
                await db.commit()
                raise HTTPException(status_code=400, detail="Maximum 6 values allowed")
            
            # Calculate equal weight
            new_count = len(existing_values) + 1
            equal_weight = 100 / new_count
            
            # Update all existing active revisions to equal weight
            for value in existing_values:
                if value.active_revision_id:
                    revision = await db.get(ValueRevision, value.active_revision_id)
                    if revision:
                        revision.weight_raw = Decimal(str(equal_weight))
            
            # Create value
            value = Value(user_id=user.id)
            db.add(value)
            await db.flush()
            
            # Create first revision
            revision = ValueRevision(
                value_id=value.id,
                statement=statement,
                weight_raw=Decimal(str(equal_weight)),
                origin="explored",  # Values from assistant are 'explored'
                is_active=True,
            )
            db.add(revision)
            await db.flush()

            try:
                match, proposed_embedding = await compute_value_similarity(
                    db,
                    user.id,
                    statement,
                )
                if match:
                    revision.similar_value_revision_id = match["similar_value_revision_id"]
                    revision.similarity_score = Decimal(str(match["similarity_score"]))
                    revision.similarity_acknowledged = False
                if proposed_embedding:
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
                pass
            
            # Set active revision
            value.active_revision_id = revision.id
            
            # Normalize weights
            await normalize_value_weights(db, user.id)
            
            # Update recommendation
            rec.status = "accepted"
            rec.result_entity_type = "value"
            rec.result_entity_id = str(value.id)  # Ensure string
            
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported action: {rec.proposed_action}",
            )
        
        await db.commit()
        await db.refresh(rec)
        
        return RecommendationResponse.model_validate(rec)
    
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to accept recommendation: {str(e)}"
        )


@router.post("/{recommendation_id}/reject", response_model=RecommendationResponse, summary="Reject recommendation")
async def reject_recommendation(
    recommendation_id: str,
    request: RejectRecommendationRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RecommendationResponse:
    """Reject a recommendation."""
    # Get recommendation and verify ownership
    rec = await db.get(AssistantRecommendation, recommendation_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    
    # Verify session belongs to user
    session = await db.get(AssistantSession, rec.session_id)
    if not session or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    
    # Check if already processed
    if rec.status != "proposed":
        raise HTTPException(
            status_code=400,
            detail=f"Recommendation already {rec.status}",
        )
    
    # Mark as rejected
    rec.status = "rejected"
    
    await db.commit()
    await db.refresh(rec)
    
    return RecommendationResponse.model_validate(rec)
