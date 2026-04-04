import secrets
from datetime import datetime, timedelta, timezone
from hashlib import sha256

from typing import Any

import jwt

from app.core.config import settings


def create_access_token(user_id: str) -> str:
    """Create a JWT access token."""
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.access_token_ttl_minutes)
    
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": expires,
        "type": "access",
    }
    
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT access token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        if payload.get("type") != "access":
            raise ValueError("Invalid token type")
        return payload
    except jwt.ExpiredSignatureError:
        raise ValueError("Token has expired")
    except jwt.InvalidTokenError as e:
        raise ValueError(f"Invalid token: {e}")


def generate_random_token(length: int = 32) -> str:
    """Generate a cryptographically secure random token."""
    return secrets.token_urlsafe(length)


def generate_verification_code() -> str:
    """Generate a 6-digit verification code."""
    return str(secrets.randbelow(900000) + 100000)


def hash_token(token: str) -> str:
    """Hash a token for secure storage."""
    return sha256(token.encode()).hexdigest()


def verify_token_hash(token: str, token_hash: str) -> bool:
    """Verify a token against its hash."""
    return hash_token(token) == token_hash
