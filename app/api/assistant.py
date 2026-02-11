from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import json

from app.core.db import get_db
from app.core.auth import CurrentUser
from app.core.time import utc_now
from app.models.assistant_session import AssistantSession
from app.models.assistant_turn import AssistantTurn
from app.models.assistant_recommendation import AssistantRecommendation
from app.models.value import Value, ValueRevision
from app.schemas.assistant import (
    CreateSessionRequest,
    SessionResponse,
    SendMessageRequest,
    MessageResponse,
)
from app.services.llm_service import LLMService
from app.core.config import settings

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    request: CreateSessionRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Create a new assistant conversation session."""
    session = AssistantSession(
        user_id=user.id,
        context_mode=request.context_mode,
        is_active=True,
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        context_mode=session.context_mode,
        is_active=session.is_active,
        created_at=session.created_at,
    )


@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(
    session_id: str,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Get a specific session with its turns."""
    result = await db.execute(
        select(AssistantSession)
        .where(AssistantSession.id == session_id, AssistantSession.user_id == user.id)
        .options(selectinload(AssistantSession.turns))
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    return SessionResponse(
        id=session.id,
        user_id=session.user_id,
        context_mode=session.context_mode,
        is_active=session.is_active,
        created_at=session.created_at,
        turns=[
            {
                "id": turn.id,
                "role": turn.role,
                "content": turn.content,
                "created_at": turn.created_at,
                "input_modality": turn.input_modality,
            }
            for turn in sorted(session.turns, key=lambda t: t.created_at)
        ] if session.turns else [],
    )


@router.post("/sessions/{session_id}/message", response_model=MessageResponse)
async def send_message(
    session_id: str,
    request: SendMessageRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    """Send a message in a session and get LLM response."""
    # Verify session exists and belongs to user
    result = await db.execute(
        select(AssistantSession)
        .where(AssistantSession.id == session_id, AssistantSession.user_id == user.id)
        .options(selectinload(AssistantSession.turns))
    )
    session = result.scalar_one_or_none()
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    # Save user message
    user_turn = AssistantTurn(
        session_id=session_id,
        role="user",
        content=request.content,
        input_modality=request.input_modality,
        created_at=utc_now(),
    )
    db.add(user_turn)
    await db.flush()
    
    # Build conversation history
    all_turns = sorted(session.turns + [user_turn], key=lambda t: t.created_at)
    messages = [
        {"role": turn.role, "content": turn.content}
        for turn in all_turns
        if turn.role in ["user", "assistant"]
    ]
    
    # Get LLM response
    try:
        llm_response = await LLMService.get_recommendation(
            messages=messages,
            user_context={
                "context_mode": session.context_mode,
                "user_id": user.id,
            },
        )
        
        # Check if LLM wants to use a tool
        response_message = llm_response["choices"][0]["message"]
        tool_calls = response_message.get("tool_calls")
        recommendation_id = None
        
        if tool_calls:
            # Handle tool calls (create recommendations)
            for tool_call in tool_calls:
                function_name = tool_call["function"]["name"]
                function_args = json.loads(tool_call["function"]["arguments"])
                
                if function_name == "propose_value":
                    proposed_statement = function_args["statement"]

                    # Create a recommendation
                    recommendation = AssistantRecommendation(
                        session_id=session_id,
                        proposed_action="create_value",
                        payload={
                            "statement": function_args["statement"],
                        },
                        rationale=function_args.get("rationale"),
                        status="proposed",
                        llm_provider=settings.llm_provider,
                        llm_model=settings.llm_model,
                    )
                    db.add(recommendation)
                    await db.flush()
                    recommendation_id = recommendation.id
                    assistant_content = (
                        f"I saved this as a proposed value: \"{proposed_statement}\". "
                        "Want to add another, or refine this one?"
                    )
        else:
            assistant_content = response_message["content"]
        
        # Save assistant response
        assistant_turn = AssistantTurn(
            session_id=session_id,
            role="assistant",
            content=assistant_content,
            input_modality="text",
            llm_provider=settings.llm_provider,
            llm_model=settings.llm_model,
            created_at=utc_now(),
        )
        db.add(assistant_turn)
        await db.commit()
        await db.refresh(assistant_turn)
        
        return MessageResponse(
            id=assistant_turn.id,
            session_id=session_id,
            role=assistant_turn.role,
            content=assistant_turn.content,
            created_at=assistant_turn.created_at,
            response=assistant_content,
            recommendation_id=recommendation_id,
        )
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get LLM response: {str(e)}"
        )
