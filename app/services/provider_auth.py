import httpx
import jwt
from jwt import PyJWKClient

from app.core.config import settings


class ProviderAuthService:
    """Service for validating OAuth provider tokens."""
    
    @staticmethod
    async def verify_google_token(id_token: str) -> dict:
        """Verify Google ID token and return payload."""
        try:
            audiences = []
            if settings.google_client_ids:
                audiences = [
                    value.strip()
                    for value in settings.google_client_ids.split(",")
                    if value.strip()
                ]
            if not audiences:
                raise ValueError("Google client IDs are not configured")

            # Google's public keys endpoint
            jwks_url = "https://www.googleapis.com/oauth2/v3/certs"
            jwks_client = PyJWKClient(jwks_url)
            
            # Get signing key
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)
            
            # Verify and decode token
            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=audiences,
                issuer="https://accounts.google.com",
            )
            
            return {
                "sub": payload["sub"],
                "email": payload.get("email"),
                "email_verified": payload.get("email_verified", False),
            }
            
        except Exception as e:
            raise ValueError(f"Invalid Google token: {e}")
    
    @staticmethod
    async def verify_apple_token(id_token: str) -> dict:
        """Verify Apple ID token and return payload."""
        try:
            # Apple's public keys endpoint
            jwks_url = "https://appleid.apple.com/auth/keys"
            jwks_client = PyJWKClient(jwks_url)
            
            # Get signing key
            signing_key = jwks_client.get_signing_key_from_jwt(id_token)
            
            # Verify and decode token
            payload = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=["RS256"],
                audience=settings.apple_audience,
                issuer=settings.apple_issuer,
            )
            
            return {
                "sub": payload["sub"],
                "email": payload.get("email"),
                "email_verified": payload.get("email_verified", False),
            }
            
        except Exception as e:
            raise ValueError(f"Invalid Apple token: {e}")
