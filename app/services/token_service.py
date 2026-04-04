"""Token management service for authentication.

Handles refresh tokens, access tokens, and logout operations.
"""

from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.time import utc_now
from app.core.security import (
    create_access_token,
    generate_random_token,
    hash_token,
    verify_token_hash,
)
from app.models.user import User
from app.models.refresh_token import RefreshToken
from app.core.config import settings


class TokenService:
    """Service for token management operations."""

    @staticmethod
    async def create_tokens_for_user(
        db: AsyncSession,
        user: User,
        device_id: str | None = None,
        device_name: str | None = None,
    ) -> dict[str, str]:
        """Create access and refresh tokens for a user."""
        access_token = create_access_token(user.id)
        refresh_token = generate_random_token()

        # Store refresh token
        refresh_token_record = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(refresh_token),
            expires_at=utc_now() + timedelta(minutes=settings.refresh_token_ttl_minutes),
            device_id=device_id,
            device_name=device_name,
        )
        db.add(refresh_token_record)

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    @staticmethod
    async def refresh_access_token(db: AsyncSession, refresh_token: str) -> dict[str, Any]:
        """Refresh access token using refresh token."""
        # Find valid refresh token
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.revoked_at.is_(None),
                RefreshToken.expires_at > utc_now(),
            )
        )
        refresh_tokens = result.scalars().all()

        # Find matching token
        refresh_token_record: RefreshToken | None = None
        for rt in refresh_tokens:
            if verify_token_hash(refresh_token, rt.token_hash):
                refresh_token_record = rt
                break

        if not refresh_token_record:
            raise ValueError("Invalid or expired refresh token")

        # Load user
        user = await db.get(User, refresh_token_record.user_id)
        if not user:
            raise ValueError("User not found")

        # Create new access token
        access_token = create_access_token(user.id)

        # Optionally rotate refresh token
        new_refresh_token = generate_random_token()

        # Revoke old refresh token
        refresh_token_record.revoked_at = utc_now()

        # Create new refresh token
        new_refresh_token_record = RefreshToken(
            user_id=user.id,
            token_hash=hash_token(new_refresh_token),
            expires_at=utc_now() + timedelta(minutes=settings.refresh_token_ttl_minutes),
            device_id=refresh_token_record.device_id,
            device_name=refresh_token_record.device_name,
        )
        db.add(new_refresh_token_record)

        await db.commit()

        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
        }

    @staticmethod
    async def logout(db: AsyncSession, refresh_token: str) -> None:
        """Logout by revoking refresh token."""
        # Find refresh token
        result = await db.execute(
            select(RefreshToken).where(
                RefreshToken.revoked_at.is_(None),
            )
        )
        refresh_tokens = result.scalars().all()

        # Find matching token and revoke it
        for rt in refresh_tokens:
            if verify_token_hash(refresh_token, rt.token_hash):
                rt.revoked_at = utc_now()
                await db.commit()
                return

        raise ValueError("Refresh token not found")
