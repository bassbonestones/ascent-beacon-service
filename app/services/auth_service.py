from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.time import utc_now
from app.core.security import (
    generate_verification_code,
    hash_token,
)
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.models.email_login_token import EmailLoginToken
from app.services.provider_auth import ProviderAuthService
from app.services.email_service import EmailService
from app.services.token_service import TokenService
from app.services.email_auth_service import EmailAuthService
from app.core.config import settings


class AuthService:
    """Service for authentication operations."""

    @staticmethod
    async def _find_or_create_user_for_oauth(
        db: AsyncSession,
        provider: str,
        provider_subject: str,
        email: str | None,
    ) -> tuple[User, bool]:
        """
        Find or create user for OAuth authentication.
        Returns (user, is_new_user).
        """
        # Find existing identity
        result = await db.execute(
            select(UserIdentity).where(
                UserIdentity.provider == provider,
                UserIdentity.provider_subject == provider_subject,
            )
        )
        identity = result.scalar_one_or_none()

        if identity:
            # Load existing user
            loaded_user = await db.get(User, identity.user_id)
            if not loaded_user:
                raise ValueError("User not found for identity")
            return loaded_user, False

        # Check if user with this email already exists
        found_user: User | None = None
        if email:
            user_result = await db.execute(
                select(User).where(User.primary_email == email)
            )
            found_user = user_result.scalar_one_or_none()

        if not found_user:
            # Create new user
            found_user = User(
                display_name=None,
                primary_email=email,
            )
            db.add(found_user)
            await db.flush()

        # Create identity
        identity = UserIdentity(
            user_id=found_user.id,
            provider=provider,
            provider_subject=provider_subject,
            email=email,
        )
        db.add(identity)

        return found_user, True

    @staticmethod
    async def authenticate_with_google(
        db: AsyncSession,
        id_token: str,
        device_id: str | None = None,
        device_name: str | None = None,
    ) -> dict[str, Any]:
        """Authenticate user with Google ID token."""
        # Verify token
        payload = await ProviderAuthService.verify_google_token(id_token)
        email = payload.get("email") if payload.get("email_verified") else None

        # Find or create user
        user, _ = await AuthService._find_or_create_user_for_oauth(
            db, "google", payload["sub"], email
        )

        # Create tokens
        tokens = await TokenService.create_tokens_for_user(db, user, device_id, device_name)

        await db.commit()

        return {
            **tokens,
            "user": user,
        }

    @staticmethod
    async def authenticate_with_apple(
        db: AsyncSession,
        id_token: str,
        device_id: str | None = None,
        device_name: str | None = None,
    ) -> dict[str, Any]:
        """Authenticate user with Apple ID token."""
        # Verify token
        payload = await ProviderAuthService.verify_apple_token(id_token)
        email = payload.get("email") if payload.get("email_verified") else None

        # Find or create user
        user, _ = await AuthService._find_or_create_user_for_oauth(
            db, "apple", payload["sub"], email
        )

        # Create tokens
        tokens = await TokenService.create_tokens_for_user(db, user, device_id, device_name)

        await db.commit()

        return {
            **tokens,
            "user": user,
        }

    @staticmethod
    async def request_magic_link(db: AsyncSession, email: str) -> None:
        """Request a 6-digit code for email authentication."""
        return await EmailAuthService.request_magic_link(db, email)
    
    @staticmethod
    async def verify_magic_link(
        db: AsyncSession,
        token: str,
        email: str | None = None,
        device_id: str | None = None,
        device_name: str | None = None,
    ) -> dict[str, Any]:
        """Verify magic link token and authenticate user."""
        return await EmailAuthService.verify_magic_link(db, token, email, device_id, device_name)

    @staticmethod
    async def refresh_access_token(db: AsyncSession, refresh_token: str) -> dict[str, Any]:
        """Refresh access token using refresh token."""
        return await TokenService.refresh_access_token(db, refresh_token)

    @staticmethod
    async def logout(db: AsyncSession, refresh_token: str) -> None:
        """Logout by revoking refresh token."""
        return await TokenService.logout(db, refresh_token)

    @staticmethod
    async def update_display_name(db: AsyncSession, user_id: str, display_name: str) -> User:
        """Update user's display name."""
        user = await db.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        user.display_name = display_name
        user.updated_at = utc_now()
        await db.commit()
        await db.refresh(user)

        return user

    @staticmethod
    async def update_and_verify_email(db: AsyncSession, user_id: str, new_email: str, force_verification: bool = False) -> User:
        """Update primary email and send verification if different from OAuth email."""
        user = await db.get(User, user_id)
        if not user:
            raise ValueError("User not found")
        
        # Check if email is already taken
        check_result = await db.execute(
            select(User).where(
                User.primary_email == new_email,
                User.id != user_id,
            )
        )
        if check_result.scalar_one_or_none():
            raise ValueError("Email already in use")
        
        # Get the OAuth email (from any identity)
        identity_result = await db.execute(
            select(UserIdentity).where(UserIdentity.user_id == user_id)
        )
        identities = identity_result.scalars().all()
        oauth_emails = [i.email for i in identities if i.email]
        
        # If force_verification is False and email matches OAuth, auto-verify
        # If force_verification is True, always require verification
        if not force_verification and new_email in oauth_emails:
            user.primary_email = new_email
            user.is_email_verified = True
            user.updated_at = utc_now()
            await db.commit()
        else:
            # Send verification email
            user.primary_email = new_email
            user.is_email_verified = False
            user.updated_at = utc_now()
            await db.flush()
            
            # Generate 6-digit verification code
            token = generate_verification_code()
            
            # Create login token record (reuse existing magic link mechanism)
            login_token = EmailLoginToken(
                email=new_email,
                token_hash=hash_token(token),
                expires_at=utc_now() + timedelta(minutes=settings.magic_link_ttl_minutes),
            )
            db.add(login_token)
            
            await db.commit()
            
            # Send verification code email
            await EmailService.send_verification_code(new_email, token)
        
        return user
    
    @staticmethod
    async def verify_onboarding_email(db: AsyncSession, user_id: str, token: str) -> User:
        """Verify email during onboarding."""
        return await EmailAuthService.verify_onboarding_email(db, user_id, token)

