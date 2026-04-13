"""Migrated tests from test_pure_functions.py (slice 1)."""

"""
Pure unit tests for schemas, model methods, and core utilities.
No database or async required - these test pure Python logic.

Target: Branch coverage for non-DB logic.
"""
import pytest
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from unittest.mock import Mock, AsyncMock
from uuid import uuid4

from pydantic import ValidationError as PydanticValidationError

# Schema imports
from app.schemas.dependency import (
    CreateDependencyRuleRequest,
    DependencyBlocker,
    DependencyStatusResponse,
    TaskInfo,
)
from app.schemas.values import ValueResponse, ValueRevisionResponse

# Core utility imports
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_random_token,
    generate_verification_code,
    hash_token,
)
from app.core.exceptions import (
    AscentBeaconError,
    ValidationError,
    NotFoundError,
    AuthenticationError,
    TokenExpiredError,
    InvalidTokenError,
    ForbiddenError,
    OwnershipError,
    BadRequestError,
)

class TestSecurityFunctions:
    """Test core security utility functions."""

    def test_create_and_decode_access_token(self):
        """Create a token and decode it."""
        user_id = str(uuid4())
        token = create_access_token(user_id)
        
        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are long
        
        payload = decode_access_token(token)
        assert payload["sub"] == user_id
        assert payload["type"] == "access"

    def test_decode_invalid_token_raises(self):
        """Invalid token raises ValueError."""
        with pytest.raises(ValueError, match="Invalid token"):
            decode_access_token("invalid.token.here")

    def test_generate_random_token_default_length(self):
        """Generate random token with default length."""
        token = generate_random_token()
        # token_urlsafe(32) produces ~43 characters (base64 encoding)
        assert len(token) >= 40
        assert len(token) <= 50

    def test_generate_random_token_custom_length(self):
        """Generate random token with custom length."""
        token = generate_random_token(length=16)
        # token_urlsafe(16) produces ~22 characters (base64 encoding)
        assert len(token) >= 20
        assert len(token) <= 30

    def test_generate_verification_code(self):
        """Generate 6-digit verification code."""
        code = generate_verification_code()
        assert len(code) == 6
        assert code.isdigit()

    def test_hash_token_consistent(self):
        """Same input produces same hash."""
        token = "test-token-123"
        hash1 = hash_token(token)
        hash2 = hash_token(token)
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 = 64 hex chars

    def test_hash_token_different_inputs(self):
        """Different inputs produce different hashes."""
        hash1 = hash_token("token1")
        hash2 = hash_token("token2")
        assert hash1 != hash2


# =============================================================================
# Exception Tests
# =============================================================================

class TestExceptions:
    """Test custom exception classes."""

    def test_base_exception_defaults(self):
        """Base exception has sensible defaults."""
        exc = AscentBeaconError()
        assert exc.message == "An error occurred"
        assert exc.status_code == 500
        assert exc.error_code == "INTERNAL_ERROR"
        assert exc.details == {}

    def test_base_exception_custom_message(self):
        """Custom message overrides default."""
        exc = AscentBeaconError(message="Custom error", details={"key": "value"})
        assert exc.message == "Custom error"
        assert exc.details == {"key": "value"}

    def test_to_dict_basic(self):
        """to_dict returns proper format."""
        exc = AscentBeaconError(message="Test error")
        result = exc.to_dict()
        assert result["error"] == "INTERNAL_ERROR"
        assert result["message"] == "Test error"
        assert "details" not in result  # Empty details not included

    def test_to_dict_with_details(self):
        """to_dict includes details when present."""
        exc = AscentBeaconError(message="Test", details={"field": "test"})
        result = exc.to_dict()
        assert result["details"] == {"field": "test"}

    def test_validation_error(self):
        """ValidationError with field."""
        exc = ValidationError(message="Invalid input", field="email")
        assert exc.status_code == 400
        assert exc.error_code == "VALIDATION_ERROR"
        assert exc.details["field"] == "email"

    def test_validation_error_without_field(self):
        """ValidationError without field (no details added)."""
        exc = ValidationError(message="Invalid input")
        assert exc.status_code == 400
        assert exc.error_code == "VALIDATION_ERROR"
        # No field should be in details
        assert "field" not in exc.details

    def test_validation_error_without_field_with_existing_details(self):
        """ValidationError without field but with existing details."""
        exc = ValidationError(
            message="Invalid input",
            details={"context": "registration"}
        )
        assert exc.details["context"] == "registration"
        assert "field" not in exc.details

    def test_not_found_error(self):
        """NotFoundError with resource info."""
        resource_id = str(uuid4())
        exc = NotFoundError("User", resource_id)
        assert exc.status_code == 404
        assert "User not found" in exc.message
        assert exc.details["resource_type"] == "User"
        assert exc.details["resource_id"] == resource_id

    def test_not_found_error_no_id(self):
        """NotFoundError without resource_id."""
        exc = NotFoundError("Task")
        assert exc.message == "Task not found"
        assert "resource_id" not in exc.details

    def test_authentication_error(self):
        """AuthenticationError defaults."""
        exc = AuthenticationError()
        assert exc.status_code == 401
        assert exc.error_code == "AUTHENTICATION_ERROR"

    def test_token_expired_error(self):
        """TokenExpiredError inherits from AuthenticationError."""
        exc = TokenExpiredError()
        assert exc.status_code == 401
        assert exc.error_code == "TOKEN_EXPIRED"

    def test_invalid_token_error(self):
        """InvalidTokenError inherits from AuthenticationError."""
        exc = InvalidTokenError()
        assert exc.status_code == 401
        assert exc.error_code == "INVALID_TOKEN"

    def test_forbidden_error(self):
        """ForbiddenError defaults."""
        exc = ForbiddenError()
        assert exc.status_code == 403
        assert exc.error_code == "FORBIDDEN"

    def test_ownership_error(self):
        """OwnershipError inherits from ForbiddenError."""
        exc = OwnershipError()
        assert exc.status_code == 403
        assert exc.error_code == "OWNERSHIP_ERROR"

    def test_bad_request_error(self):
        """BadRequestError defaults."""
        exc = BadRequestError()
        assert exc.status_code == 400
        assert exc.error_code == "BAD_REQUEST"


# =============================================================================
# Model Property Tests (testing without DB by creating instances directly)
# =============================================================================

class TestSecurityTokenOperations:
    """Additional security function tests."""

    def test_decode_invalid_token_format(self):
        """Malformed JWT raises ValueError."""
        from app.core.security import decode_access_token
        
        with pytest.raises(ValueError, match="Invalid token"):
            decode_access_token("not-a-jwt")

    def test_decode_expired_token(self):
        """Expired token raises ValueError with specific message."""
        import jwt
        from datetime import datetime, timezone, timedelta
        from app.core.config import settings
        
        # Create an expired token
        now = datetime.now(timezone.utc)
        expired = now - timedelta(hours=24)
        payload = {
            "sub": str(uuid4()),
            "iat": expired,
            "exp": expired + timedelta(minutes=30),
            "type": "access",
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
        
        with pytest.raises(ValueError, match="Token has expired"):
            decode_access_token(token)

    def test_verify_token_hash(self):
        """Verify token hash function."""
        from app.core.security import hash_token, verify_token_hash
        
        token = "test-token-for-hashing"
        hashed = hash_token(token)
        
        # verify_token_hash should return True
        assert verify_token_hash(token, hashed) is True
        
        # Wrong token should fail
        assert verify_token_hash("wrong-token", hashed) is False


# =============================================================================
# Logging Tests
# =============================================================================

class TestTokenServiceLogic:
    """Tests for token service logic patterns."""

    def test_token_expiry_check(self):
        """Test token expiry checking logic."""
        now = datetime.now(timezone.utc)
        
        valid_expiry = now + timedelta(days=7)
        expired_expiry = now - timedelta(days=1)
        
        is_valid_expired = valid_expiry < now
        is_expired_expired = expired_expiry < now
        
        assert is_valid_expired is False
        assert is_expired_expired is True

    def test_token_revocation_check(self):
        """Test token revocation checking logic."""
        # Token with no revoked_at is valid
        revoked_at_none = None
        is_revoked_none = revoked_at_none is not None
        
        # Token with revoked_at is revoked
        revoked_at_set = datetime.now(timezone.utc)
        is_revoked_set = revoked_at_set is not None
        
        assert is_revoked_none is False
        assert is_revoked_set is True

    def test_token_valid_check_combined(self):
        """Test combined token validity check."""
        now = datetime.now(timezone.utc)
        
        cases = [
            # (revoked_at, expires_at, expected_valid)
            (None, now + timedelta(days=7), True),   # Valid
            (None, now - timedelta(days=1), False),  # Expired
            (now - timedelta(hours=1), now + timedelta(days=7), False),  # Revoked
        ]
        
        for revoked_at, expires_at, expected in cases:
            is_revoked = revoked_at is not None
            is_expired = expires_at < now
            is_valid = not is_revoked and not is_expired
            
            assert is_valid == expected


# =============================================================================
# Email Validation Logic Tests
# =============================================================================

class TestTokenServiceSecurityHelpers:
    """Test token service security helper functions."""

    def test_verification_code_format(self):
        """Verification code is 6 digits."""
        from app.core.security import generate_verification_code
        
        code = generate_verification_code()
        
        assert len(code) == 6
        assert code.isdigit()

    def test_hash_token_returns_string(self):
        """hash_token returns a string hash."""
        from app.core.security import hash_token
        
        token = "abc123"
        hashed = hash_token(token)
        
        assert isinstance(hashed, str)
        assert hashed != token

    def test_verify_token_hash_correct(self):
        """verify_token_hash returns True for correct token."""
        from app.core.security import hash_token, verify_token_hash
        
        token = "test_token_123"
        hashed = hash_token(token)
        
        assert verify_token_hash(token, hashed) is True

    def test_verify_token_hash_incorrect(self):
        """verify_token_hash returns False for wrong token."""
        from app.core.security import hash_token, verify_token_hash
        
        token = "correct_token"
        hashed = hash_token(token)
        
        assert verify_token_hash("wrong_token", hashed) is False

class TestMoreAuthHelpers:
    """Tests for auth helper functions."""

    def test_decode_valid_jwt(self):
        """decode_access_token decodes valid JWT."""
        from app.core.security import create_access_token, decode_access_token
        
        user_id = "user-123"
        token = create_access_token(user_id)
        
        payload = decode_access_token(token)
        
        assert payload["sub"] == user_id

    def test_create_access_token_string(self):
        """create_access_token returns string."""
        from app.core.security import create_access_token
        
        token = create_access_token("user-123")
        
        assert isinstance(token, str)
        assert len(token) > 0


# ---- migrated from tests/utils/test_security.py ----

"""Tests for security utilities."""

import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_random_token,
    generate_verification_code,
    hash_token,
    verify_token_hash,
)


class TestAccessToken:
    """Tests for JWT access token creation and decoding."""
    
    def test_create_access_token(self):
        """Creating access token returns a string."""
        user_id = str(uuid4())
        token = create_access_token(user_id)
        
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_decode_valid_token(self):
        """Valid token can be decoded."""
        user_id = str(uuid4())
        token = create_access_token(user_id)
        
        payload = decode_access_token(token)
        
        assert payload["sub"] == user_id
        assert payload["type"] == "access"
        assert "iat" in payload
        assert "exp" in payload
    
    def test_decode_invalid_token(self):
        """Invalid token raises ValueError."""
        with pytest.raises(ValueError, match="Invalid token"):
            decode_access_token("not-a-valid-token")
    
    def test_decode_wrong_secret(self):
        """Token with wrong secret fails."""
        # Create a token then try to decode with wrong secret
        import jwt
        from app.core.config import settings
        
        # Create with different secret
        token = jwt.encode(
            {"sub": "user123", "type": "access", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
            "wrong-secret-key-for-test-case-1234",
            algorithm=settings.jwt_algorithm,
        )
        
        with pytest.raises(ValueError, match="Invalid token"):
            decode_access_token(token)
    
    def test_decode_expired_token(self):
        """Expired token raises ValueError."""
        import jwt
        from app.core.config import settings
        
        # Create expired token
        token = jwt.encode(
            {
                "sub": "user123",
                "type": "access",
                "exp": datetime.now(timezone.utc) - timedelta(hours=1),
                "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            },
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        
        with pytest.raises(ValueError, match="expired"):
            decode_access_token(token)
    
    def test_decode_wrong_token_type(self):
        """Token with wrong type raises ValueError."""
        import jwt
        from app.core.config import settings
        
        token = jwt.encode(
            {
                "sub": "user123",
                "type": "refresh",  # Wrong type
                "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            },
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )
        
        with pytest.raises(ValueError, match="Invalid token type"):
            decode_access_token(token)


class TestRandomToken:
    """Tests for random token generation."""
    
    def test_generate_random_token(self):
        """Random token is generated."""
        token = generate_random_token()
        
        assert isinstance(token, str)
        assert len(token) > 0
    
    def test_tokens_are_unique(self):
        """Generated tokens are unique."""
        tokens = [generate_random_token() for _ in range(100)]
        assert len(tokens) == len(set(tokens))
    
    def test_token_length(self):
        """Token length can be customized."""
        token_16 = generate_random_token(16)
        token_64 = generate_random_token(64)
        
        # URL-safe base64 is ~4/3 of byte length
        assert len(token_16) > 0
        assert len(token_64) > len(token_16)


class TestVerificationCode:
    """Tests for verification code generation."""
    
    def test_generate_verification_code(self):
        """Verification code is generated."""
        code = generate_verification_code()
        
        assert isinstance(code, str)
        assert len(code) == 6
    
    def test_code_is_numeric(self):
        """Verification code is all digits."""
        code = generate_verification_code()
        assert code.isdigit()
    
    def test_code_in_range(self):
        """Verification code is in valid range."""
        for _ in range(100):
            code = generate_verification_code()
            num = int(code)
            assert 100000 <= num <= 999999


class TestHashToken:
    """Tests for token hashing."""
    
    def test_hash_token(self):
        """Token can be hashed."""
        token = "test-token"
        hashed = hash_token(token)
        
        assert isinstance(hashed, str)
        assert len(hashed) == 64  # SHA-256 hex digest is 64 chars
    
    def test_same_input_same_hash(self):
        """Same input produces same hash."""
        token = "test-token"
        assert hash_token(token) == hash_token(token)
    
    def test_different_input_different_hash(self):
        """Different inputs produce different hashes."""
        assert hash_token("token1") != hash_token("token2")
    
    def test_verify_token_hash_valid(self):
        """Verification succeeds for matching token."""
        token = "my-secret-token"
        token_hash = hash_token(token)
        
        assert verify_token_hash(token, token_hash) is True
    
    def test_verify_token_hash_invalid(self):
        """Verification fails for non-matching token."""
        token = "my-secret-token"
        token_hash = hash_token(token)
        
        assert verify_token_hash("wrong-token", token_hash) is False
