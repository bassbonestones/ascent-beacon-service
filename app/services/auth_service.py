from datetime import timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.time import utc_now
from app.core.security import (
    create_access_token,
    generate_random_token,
    generate_verification_code,
    hash_token,
    verify_token_hash,
)
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.models.email_login_token import EmailLoginToken
from app.models.refresh_token import RefreshToken
from app.services.provider_auth import ProviderAuthService
from app.services.email_service import EmailService
from app.core.config import settings


class AuthService:
    """Service for authentication operations."""
    
    @staticmethod
    async def authenticate_with_google(
        db: AsyncSession,
        id_token: str,
        device_id: str | None = None,
        device_name: str | None = None,
    ) -> dict:
        """Authenticate user with Google ID token."""
        # Verify token
        payload = await ProviderAuthService.verify_google_token(id_token)
        
        # Find or create identity
        result = await db.execute(
            select(UserIdentity).where(
                UserIdentity.provider == "google",
                UserIdentity.provider_subject == payload["sub"],
            )
        )
        identity = result.scalar_one_or_none()
        
        if identity:
            # Load existing user
            user = await db.get(User, identity.user_id)
        else:
            # Check if user with this email already exists
            email = payload.get("email") if payload.get("email_verified") else None
            user = None
            
            if email:
                result = await db.execute(
                    select(User).where(User.primary_email == email)
                )
                user = result.scalar_one_or_none()
            
            if not user:
                # Create new user
                user = User(
                    display_name=None,
                    primary_email=email,
                )
                db.add(user)
                await db.flush()
            
            # Create identity
            identity = UserIdentity(
                user_id=user.id,
                provider="google",
                provider_subject=payload["sub"],
                email=payload.get("email"),
            )
            db.add(identity)
        
        # Create tokens
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
        
        await db.commit()
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user,
        }
    
    @staticmethod
    async def authenticate_with_apple(
        db: AsyncSession,
        id_token: str,
        device_id: str | None = None,
        device_name: str | None = None,
    ) -> dict:
        """Authenticate user with Apple ID token."""
        # Verify token
        payload = await ProviderAuthService.verify_apple_token(id_token)
        
        # Find or create identity
        result = await db.execute(
            select(UserIdentity).where(
                UserIdentity.provider == "apple",
                UserIdentity.provider_subject == payload["sub"],
            )
        )
        identity = result.scalar_one_or_none()
        
        if identity:
            # Load existing user
            user = await db.get(User, identity.user_id)
        else:
            # Check if user with this email already exists
            email = payload.get("email") if payload.get("email_verified") else None
            user = None
            
            if email:
                result = await db.execute(
                    select(User).where(User.primary_email == email)
                )
                user = result.scalar_one_or_none()
            
            if not user:
                # Create new user
                user = User(
                    display_name=None,
                    primary_email=email,
                )
                db.add(user)
                await db.flush()
            
            # Create identity
            identity = UserIdentity(
                user_id=user.id,
                provider="apple",
                provider_subject=payload["sub"],
                email=payload.get("email"),
            )
            db.add(identity)
        
        # Create tokens
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
        
        await db.commit()
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user,
        }
    
    @staticmethod
    async def request_magic_link(db: AsyncSession, email: str) -> None:
        """Request a 6-digit code for email authentication."""
        # Normalize email
        normalized_email = email.lower().strip()
        
        # Generate 6-digit code
        code = generate_verification_code()
        
        # Create login token record
        login_token = EmailLoginToken(
            email=normalized_email,
            token_hash=hash_token(code),
            expires_at=utc_now() + timedelta(minutes=settings.magic_link_ttl_minutes),
        )
        db.add(login_token)
        await db.commit()
        
        # Send email with verification code
        await EmailService.send_verification_code(normalized_email, code)
    
    @staticmethod
    async def verify_magic_link(
        db: AsyncSession,
        token: str,
        email: str | None = None,
        device_id: str | None = None,
        device_name: str | None = None,
    ) -> dict:
        """Verify magic link token and authenticate user."""
        # Find valid token
        result = await db.execute(
            select(EmailLoginToken).where(
                EmailLoginToken.used_at.is_(None),
                EmailLoginToken.expires_at > utc_now(),
            )
        )
        login_tokens = result.scalars().all()
        
        # Find matching token
        login_token = None
        for lt in login_tokens:
            if verify_token_hash(token, lt.token_hash):
                # If email provided, verify it matches
                if email and lt.email.lower() != email.lower():
                    continue
                login_token = lt
                break
        
        if not login_token:
            raise ValueError("Invalid or expired token")
        
        # Mark token as used
        login_token.used_at = utc_now()
        
        # Find or create identity
        result = await db.execute(
            select(UserIdentity).where(
                UserIdentity.provider == "email",
                UserIdentity.provider_subject == login_token.email,
            )
        )
        identity = result.scalar_one_or_none()
        
        if identity:
            # Load existing user
            user = await db.get(User, identity.user_id)
            # Mark email as verified since they just proved access
            if not user.is_email_verified:
                user.is_email_verified = True
        else:
            # Check if user with this email already exists
            result = await db.execute(
                select(User).where(User.primary_email == login_token.email)
            )
            user = result.scalar_one_or_none()
            
            if not user:
                # Create new user with verified email
                user = User(
                    display_name=None,
                    primary_email=login_token.email,
                    is_email_verified=True,
                )
                db.add(user)
                await db.flush()
            else:
                # Mark email as verified
                if not user.is_email_verified:
                    user.is_email_verified = True
            
            # Create identity
            identity = UserIdentity(
                user_id=user.id,
                provider="email",
                provider_subject=login_token.email,
                email=login_token.email,
            )
            db.add(identity)
        
        # Create tokens
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
        
        await db.commit()
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": user,
        }
    
    @staticmethod
    async def refresh_access_token(db: AsyncSession, refresh_token: str) -> dict:
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
        refresh_token_record = None
        for rt in refresh_tokens:
            if verify_token_hash(refresh_token, rt.token_hash):
                refresh_token_record = rt
                break
        
        if not refresh_token_record:
            raise ValueError("Invalid or expired refresh token")
        
        # Load user
        user = await db.get(User, refresh_token_record.user_id)
        
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
        result = await db.execute(
            select(User).where(
                User.primary_email == new_email,
                User.id != user_id,
            )
        )
        if result.scalar_one_or_none():
            raise ValueError("Email already in use")
        
        # Get the OAuth email (from any identity)
        result = await db.execute(
            select(UserIdentity).where(UserIdentity.user_id == user_id)
        )
        identities = result.scalars().all()
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
        user = await db.get(User, user_id)
        if not user:
            raise ValueError("User not found")
        
        # Find valid token for this user's email
        result = await db.execute(
            select(EmailLoginToken).where(
                EmailLoginToken.email == user.primary_email,
                EmailLoginToken.used_at.is_(None),
                EmailLoginToken.expires_at > utc_now(),
            )
        )
        login_tokens = result.scalars().all()
        
        # Find matching token
        login_token = None
        for lt in login_tokens:
            if verify_token_hash(token, lt.token_hash):
                login_token = lt
                break
        
        if not login_token:
            raise ValueError("Invalid or expired verification token")
        
        # Mark token as used
        login_token.used_at = utc_now()
        
        # Mark email as verified
        user.is_email_verified = True
        user.updated_at = utc_now()
        
        await db.commit()
        await db.refresh(user)
        
        return user

