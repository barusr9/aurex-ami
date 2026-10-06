"""Tests for authentication module (ami/auth.py)."""

import pytest
import time
from ami.auth import (
    generate_token,
    validate_token,
    extract_token_from_header,
    authenticate_request,
    AuthError,
)

SECRET_KEY = "test-secret-key-12345"


class TestTokenGeneration:
    """Test token generation."""

    def test_generate_token_valid(self):
        """Valid token generation."""
        token = generate_token("user_123", secret_key=SECRET_KEY)
        assert token
        assert isinstance(token, str)
        assert len(token) > 0

    def test_generate_token_different_users(self):
        """Different users get different tokens."""
        token1 = generate_token("user_1", secret_key=SECRET_KEY)
        token2 = generate_token("user_2", secret_key=SECRET_KEY)
        assert token1 != token2

    def test_generate_token_payload(self):
        """Generated token contains correct payload."""
        token = generate_token("user_abc", secret_key=SECRET_KEY)
        payload = validate_token(token, secret_key=SECRET_KEY)
        assert payload["user_id"] == "user_abc"
        assert payload["scope"] == "user_abc"
        assert "exp" in payload
        assert "iat" in payload


class TestTokenValidation:
    """Test token validation."""

    def test_validate_token_valid(self):
        """Valid token passes validation."""
        token = generate_token("user_123", secret_key=SECRET_KEY)
        payload = validate_token(token, secret_key=SECRET_KEY)
        assert payload["user_id"] == "user_123"
        assert payload["scope"] == "user_123"

    def test_validate_token_expired(self):
        """Expired token fails validation."""
        # Generate with custom expiry (past, more than 10s ago)
        import jwt
        from datetime import datetime, timedelta
        import time

        now_time = time.time()
        past_time = now_time - 120  # 2 minutes ago (more than 10s leeway)
        payload = {
            "user_id": "user_123",
            "scope": "user_123",
            "iat": int(now_time),
            "exp": int(past_time),
            "iss": "ami-auth",
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")

        with pytest.raises(AuthError, match="expired"):
            validate_token(token, secret_key=SECRET_KEY)

    def test_validate_token_tampered(self):
        """Tampered token fails validation."""
        token = generate_token("user_123", secret_key=SECRET_KEY)
        # Modify token (last char)
        tampered = token[:-1] + ("x" if token[-1] != "x" else "y")

        with pytest.raises(AuthError, match="invalid"):
            validate_token(tampered, secret_key=SECRET_KEY)

    def test_validate_token_wrong_secret(self):
        """Token fails validation with wrong secret."""
        token = generate_token("user_123", secret_key=SECRET_KEY)

        with pytest.raises(AuthError):
            validate_token(token, secret_key="wrong-secret")

    def test_validate_token_empty(self):
        """Empty token fails validation."""
        with pytest.raises(AuthError):
            validate_token("", secret_key=SECRET_KEY)


class TestHeaderExtraction:
    """Test Authorization header extraction."""

    def test_extract_token_valid(self):
        """Valid bearer token extracted."""
        token = "eyJhbGc.eyJ1c2V.SflKxw"
        header = f"Bearer {token}"
        extracted = extract_token_from_header(header)
        assert extracted == token

    def test_extract_token_case_insensitive(self):
        """Bearer keyword is case-insensitive."""
        token = "eyJhbGc.eyJ1c2V.SflKxw"
        for variant in ["Bearer", "bearer", "BEARER", "BeArEr"]:
            header = f"{variant} {token}"
            extracted = extract_token_from_header(header)
            assert extracted == token

    def test_extract_token_missing_header(self):
        """Missing Authorization header raises error."""
        with pytest.raises(AuthError, match="Missing"):
            extract_token_from_header("")

    def test_extract_token_missing_bearer(self):
        """Missing 'Bearer' keyword raises error."""
        with pytest.raises(AuthError, match="Invalid"):
            extract_token_from_header("eyJhbGc.eyJ1c2V.SflKxw")

    def test_extract_token_extra_parts(self):
        """Extra parts in header raises error."""
        with pytest.raises(AuthError, match="Invalid"):
            extract_token_from_header("Bearer token extra")

    def test_extract_token_none(self):
        """None header raises error."""
        with pytest.raises(AuthError):
            extract_token_from_header(None)


class TestFullAuthentication:
    """Test full authentication flow."""

    def test_authenticate_request_valid(self):
        """Valid Authorization header authenticates."""
        token = generate_token("user_123", secret_key=SECRET_KEY)
        header = f"Bearer {token}"
        payload = authenticate_request(header, secret_key=SECRET_KEY)
        assert payload["user_id"] == "user_123"
        assert payload["scope"] == "user_123"

    def test_authenticate_request_missing_header(self):
        """Missing header fails."""
        with pytest.raises(AuthError):
            authenticate_request("", secret_key=SECRET_KEY)

    def test_authenticate_request_invalid_format(self):
        """Invalid header format fails."""
        with pytest.raises(AuthError):
            authenticate_request("Bearer", secret_key=SECRET_KEY)

    def test_authenticate_request_expired_token(self):
        """Expired token fails."""
        import jwt
        import time

        now_time = time.time()
        past_time = now_time - 120  # 2 minutes ago
        payload = {
            "user_id": "user_123",
            "scope": "user_123",
            "iat": int(now_time),
            "exp": int(past_time),
            "iss": "ami-auth",
        }
        token = jwt.encode(payload, SECRET_KEY, algorithm="HS256")
        header = f"Bearer {token}"

        with pytest.raises(AuthError):
            authenticate_request(header, secret_key=SECRET_KEY)

    def test_authenticate_request_tampered_token(self):
        """Tampered token fails."""
        token = generate_token("user_123", secret_key=SECRET_KEY)
        tampered = token[:-1] + ("x" if token[-1] != "x" else "y")
        header = f"Bearer {tampered}"

        with pytest.raises(AuthError):
            authenticate_request(header, secret_key=SECRET_KEY)
