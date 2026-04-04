from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.auth import CurrentUser
from app.core.config import settings
from app.schemas.auth import (
    GoogleAuthRequest,
    AppleAuthRequest,
    EmailAuthRequest,
    EmailVerifyRequest,
    RefreshRequest,
    LogoutRequest,
    AuthResponse,
    RefreshResponse,
    UserResponse,
    SetDisplayNameRequest,
    UpdatePrimaryEmailRequest,
    OnboardingStatusResponse,
)
from app.schemas.common import SuccessResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/google", response_model=AuthResponse, summary="Authenticate with Google")
async def auth_google(
    request: GoogleAuthRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthResponse:
    """Authenticate with Google ID token."""
    try:
        result = await AuthService.authenticate_with_google(
            db,
            request.id_token,
            request.device_id,
            request.device_name,
        )
        
        return AuthResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            user=UserResponse.model_validate(result["user"]),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.post("/apple", response_model=AuthResponse, summary="Authenticate with Apple")
async def auth_apple(
    request: AppleAuthRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthResponse:
    """Authenticate with Apple ID token."""
    try:
        result = await AuthService.authenticate_with_apple(
            db,
            request.id_token,
            request.device_id,
            request.device_name,
        )
        
        return AuthResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            user=UserResponse.model_validate(result["user"]),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.post("/email/request", response_model=SuccessResponse, summary="Request magic link")
async def request_magic_link(
    request: EmailAuthRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse:
    """Request a magic link for email authentication."""
    await AuthService.request_magic_link(db, request.email)
    return SuccessResponse()


@router.post("/email/verify", response_model=AuthResponse, summary="Verify magic link")
async def verify_magic_link(
    request: EmailVerifyRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthResponse:
    """Verify magic link token and authenticate."""
    try:
        result = await AuthService.verify_magic_link(
            db,
            request.token,
            request.email,
            request.device_id,
            request.device_name,
        )
        
        return AuthResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
            user=UserResponse.model_validate(result["user"]),
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.post("/refresh", response_model=RefreshResponse, summary="Refresh access token")
async def refresh_token(
    request: RefreshRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RefreshResponse:
    """Refresh access token using refresh token."""
    try:
        result = await AuthService.refresh_access_token(db, request.refresh_token)
        
        return RefreshResponse(
            access_token=result["access_token"],
            refresh_token=result["refresh_token"],
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.post("/logout", response_model=SuccessResponse, summary="Logout user")
async def logout(
    request: LogoutRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SuccessResponse:
    """Logout by revoking refresh token."""
    try:
        await AuthService.logout(db, request.refresh_token)
        return SuccessResponse()
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.get("/onboarding/status", response_model=OnboardingStatusResponse, summary="Get onboarding status")
async def get_onboarding_status(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> OnboardingStatusResponse:
    """Get onboarding status for current user."""
    # Reload user to get latest data
    from app.models.user import User
    refreshed_user = await db.get(User, user.id)
    if not refreshed_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    user = refreshed_user
    
    return OnboardingStatusResponse(
        user=UserResponse.model_validate(user),
        needs_display_name=user.display_name is None,
        needs_email_verification=not user.is_email_verified,
    )


@router.post("/onboarding/display-name", response_model=UserResponse, summary="Set display name")
async def set_display_name(
    request: SetDisplayNameRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Set display name for current user."""
    try:
        result = await AuthService.update_display_name(db, user.id, request.display_name)
        return UserResponse.model_validate(result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/onboarding/email", response_model=UserResponse, summary="Update primary email")
async def update_primary_email(
    request: UpdatePrimaryEmailRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Update primary email and send verification if different from OAuth email."""
    try:
        updated_user = await AuthService.update_and_verify_email(
            db, user.id, request.primary_email, request.force_verification
        )
        return UserResponse.model_validate(updated_user)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/onboarding/verify-email", response_model=UserResponse, summary="Verify onboarding email")
async def verify_onboarding_email(
    request: EmailVerifyRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    """Verify email during onboarding."""
    try:
        result = await AuthService.verify_onboarding_email(db, user.id, request.token)
        return UserResponse.model_validate(result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


@router.post("/dev-login", response_model=AuthResponse, summary="Dev login (local only)")
async def dev_login(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthResponse:
    """DEV ONLY: Auto-login as jeremiah.stones@gmail.com for testing."""
    if settings.env != "local":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dev login only available in local environment",
        )
    
    try:
        from app.models.user import User
        from app.models.user_identity import UserIdentity
        from app.models.refresh_token import RefreshToken
        from app.core.security import create_access_token, generate_random_token, hash_token
        from app.core.time import utc_now
        from datetime import timedelta
        from sqlalchemy import select
        
        email = "jeremiah.stones@gmail.com"
        
        # Find or create user with this email
        result = await db.execute(
            select(User).where(User.primary_email == email)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            # Create user if doesn't exist
            user = User(primary_email=email)
            db.add(user)
            await db.flush()
            
            # Create Google identity
            identity = UserIdentity(
                user_id=user.id,
                provider="google",
                provider_subject="dev-user-id",
                email=email,
            )
            db.add(identity)
        
        # Create tokens (same as authenticate_with_google)
        access_token = create_access_token(user.id)
        refresh_token = generate_random_token()
        
        # Store refresh token
        refresh_token_record = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=utc_now() + timedelta(minutes=settings.refresh_token_ttl_minutes),
            device_id="dev-device",
            device_name="Dev Browser",
        )
        db.add(refresh_token_record)
        
        await db.commit()
        
        return AuthResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse.model_validate(user),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


