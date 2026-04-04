"""Service for email-based authentication."""

from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.time import utc_now
from app.core.security import (
    generate_verification_code,
    hash_token,
    verify_token_hash,
)
from app.core.config import settings
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.models.email_login_token import EmailLoginToken
from app.services.email_service import EmailService
from app.services.token_service import TokenService


class EmailAuthService:
    """Service for email/magic link authentication."""

    @staticmethod
    async def request_magic_link(db: AsyncSession, email: str) -> None:
        """Request a 6-digit code for email authentication."""
        normalized_email = email.lower().strip()
        code = generate_verification_code()
        
        login_token = EmailLoginToken(
            email=normalized_email,
            token_hash=hash_token(code),
            expires_at=utc_now() + timedelta(minutes=settings.magic_link_ttl_minutes),
        )
        db.add(login_token)
        await db.commit()
        
        await EmailService.send_verification_code(normalized_email, code)

    @staticmethod
    async def verify_magic_link(
        db: AsyncSession,
        token: str,
        email: str | None = None,
        device_id: str | None = None,
        device_name: str | None = None,
    ) -> dict[str, Any]:
        """Verify magic link token and authenticate user."""
        result = await db.execute(
            select(EmailLoginToken).where(
                EmailLoginToken.used_at.is_(None),
                EmailLoginToken.expires_at > utc_now(),
            )
        )
        login_tokens = result.scalars().all()
        
        login_token: EmailLoginToken | None = None
        for lt in login_tokens:
            if verify_token_hash(token, lt.token_hash):
                if email and lt.email.lower() != email.lower():
                    continue
                login_token = lt
                break
        
        if not login_token:
            raise ValueError("Invalid or expired token")
        
        login_token.used_at = utc_now()
        
        identity_result = await db.execute(
            select(UserIdentity).where(
                UserIdentity.provider == "email",
                UserIdentity.provider_subject == login_token.email,
            )
        )
        identity = identity_result.scalar_one_or_none()
        
        if identity:
            loaded_user = await db.get(User, identity.user_id)
            if not loaded_user:
                raise ValueError("User not found for identity")
            user: User = loaded_user
            if not user.is_email_verified:
                user.is_email_verified = True
        else:
            user_result = await db.execute(
                select(User).where(User.primary_email == login_token.email)
            )
            found_user = user_result.scalar_one_or_none()
            
            if not found_user:
                found_user = User(
                    display_name=None,
                    primary_email=login_token.email,
                    is_email_verified=True,
                )
                db.add(found_user)
                await db.flush()
            else:
                if not found_user.is_email_verified:
                    found_user.is_email_verified = True
            
            user = found_user
            
            identity = UserIdentity(
                user_id=user.id,
                provider="email",
                provider_subject=login_token.email,
                email=login_token.email,
            )
            db.add(identity)

        tokens = await TokenService.create_tokens_for_user(db, user, device_id, device_name)
        await db.commit()

        return {**tokens, "user": user}

    @staticmethod
    async def verify_onboarding_email(db: AsyncSession, user_id: str, token: str) -> User:
        """Verify email during onboarding."""
        user = await db.get(User, user_id)
        if not user:
            raise ValueError("User not found")
        
        result = await db.execute(
            select(EmailLoginToken).where(
                EmailLoginToken.email == user.primary_email,
                EmailLoginToken.used_at.is_(None),
                EmailLoginToken.expires_at > utc_now(),
            )
        )
        login_tokens = result.scalars().all()
        
        login_token = None
        for lt in login_tokens:
            if verify_token_hash(token, lt.token_hash):
                login_token = lt
                break
        
        if not login_token:
            raise ValueError("Invalid or expired verification token")
        
        login_token.used_at = utc_now()
        user.is_email_verified = True
        user.updated_at = utc_now()
        
        await db.commit()
        await db.refresh(user)
        
        return user
