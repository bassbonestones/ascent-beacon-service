import httpx

from app.core.config import settings
from app.core.logging import logger


class EmailService:
    """Service for sending emails via Resend."""
    
    @staticmethod
    async def send_magic_link(email: str, token: str) -> None:
        """Send a magic link email."""
        link = f"{settings.magic_link_base_url}/email?token={token}"
        
        # Only use Resend for jeremiah.stones@gmail.com (verified email)
        # For other emails, log to console (resend.dev domain restriction)
        if not settings.resend_api_key or email != "jeremiah.stones@gmail.com":
            logger.info("Magic link generated", email=email, link=link)
            return
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {settings.resend_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": settings.magic_link_from or "Ascent Beacon <auth@ascentbeacon.app>",
                        "to": [email],
                        "subject": "Sign in to Ascent Beacon",
                        "html": f"""
                            <p>Click the link below to sign in to Ascent Beacon:</p>
                            <p><a href="{link}">Sign in</a></p>
                            <p>This link will expire in {settings.magic_link_ttl_minutes} minutes.</p>
                            <p>If you didn't request this, you can safely ignore this email.</p>
                        """,
                    },
                )
                
                if not response.is_success:
                    try:
                        error_detail = response.json()
                    except (ValueError, httpx.DecodingError):
                        error_detail = response.text
                    logger.error(
                        "Resend API error",
                        status_code=response.status_code,
                        error=error_detail,
                        email=email,
                    )
                
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.error("Resend HTTP error", error=str(e), email=email)
                raise
    
    @staticmethod
    async def send_verification_code(email: str, code: str) -> None:
        """Send a 6-digit verification code email."""
        # Only use Resend for jeremiah.stones@gmail.com (verified email)
        # For other emails, log to console (resend.dev domain restriction)
        if not settings.resend_api_key or email != "jeremiah.stones@gmail.com":
            logger.info("Verification code generated", email=email, code=code)
            return
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": f"Bearer {settings.resend_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": settings.magic_link_from or "Ascent Beacon <auth@ascentbeacon.app>",
                        "to": [email],
                        "subject": "Verify your email - Ascent Beacon",
                        "html": f"""
                            <h2>Verify your email</h2>
                            <p>Your verification code is:</p>
                            <h1 style="font-size: 32px; letter-spacing: 8px; font-family: monospace;">{code}</h1>
                            <p>This code will expire in {settings.magic_link_ttl_minutes} minutes.</p>
                            <p>If you didn't request this, you can safely ignore this email.</p>
                        """,
                    },
                )
                
                if not response.is_success:
                    try:
                        error_detail = response.json()
                    except (ValueError, httpx.DecodingError):
                        error_detail = response.text
                    logger.error(
                        "Resend API error",
                        status_code=response.status_code,
                        error=error_detail,
                        email=email,
                    )
                
                response.raise_for_status()
            except httpx.HTTPStatusError as e:
                logger.error("Resend HTTP error", error=str(e), email=email)
                raise
