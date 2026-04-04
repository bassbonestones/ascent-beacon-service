from fastapi import APIRouter

from app.core.auth import CurrentUser
from app.schemas.auth import UserResponse

router = APIRouter(tags=["user"])


@router.get("/me", response_model=UserResponse, summary="Get current user")
async def get_current_user(user: CurrentUser) -> UserResponse:
    """Get current authenticated user."""
    return UserResponse.model_validate(user)
