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
            "wrong-secret",
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
