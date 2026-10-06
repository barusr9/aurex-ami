"""Authentication module for per-user identity validation.

Handles JWT token validation, identity extraction, and scope derivation.
Every request must include a valid Authorization header with a Bearer token.

Token format (JWT HS256):
  {user_id, scope, exp, iat}

Scope = user_id (1:1 mapping for MVP). Cannot be overridden by caller.
"""

import os
import time
from datetime import datetime, timedelta

import jwt
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.environ.get("AUTH_SECRET_KEY", "dev-secret-key-12345")
ALGORITHM = "HS256"
TOKEN_EXPIRY_MINUTES = 15


class AuthError(Exception):
    """Auth validation failed."""
    pass


def generate_token(user_id: str, secret_key: str = None) -> str:
    """Generate a JWT token for a user.

    Args:
        user_id: Unique identifier for the user
        secret_key: Secret key for signing (uses AUTH_SECRET_KEY if None)

    Returns:
        JWT token string
    """
    if secret_key is None:
        secret_key = SECRET_KEY

    now = datetime.utcnow()
    exp = now + timedelta(minutes=TOKEN_EXPIRY_MINUTES)

    payload = {
        "user_id": user_id,
        "scope": user_id,  # Scope = user_id for now
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": "ami-auth",
    }

    token = jwt.encode(payload, secret_key, algorithm=ALGORITHM)
    return token


def validate_token(token: str, secret_key: str = None) -> dict:
    """Validate and decode a JWT token.

    Args:
        token: JWT token string
        secret_key: Secret key for validation (uses AUTH_SECRET_KEY if None)

    Returns:
        Decoded payload dict with {user_id, scope, exp, iat}

    Raises:
        AuthError: If token is invalid, expired, or tampered with
    """
    if secret_key is None:
        secret_key = SECRET_KEY

    try:
        payload = jwt.decode(
            token, secret_key, algorithms=[ALGORITHM],
            options={"verify_iat": False}  # Skip iat check for MVP (can add back later)
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthError("Token expired")
    except jwt.InvalidSignatureError:
        raise AuthError("Token signature invalid")
    except jwt.InvalidTokenError as e:
        raise AuthError(f"Token invalid: {e}")


def extract_token_from_header(auth_header: str) -> str:
    """Extract token from Authorization header.

    Expected format: "Bearer <token>"

    Args:
        auth_header: Authorization header value

    Returns:
        Token string

    Raises:
        AuthError: If header format is invalid or missing
    """
    if not auth_header:
        raise AuthError("Missing Authorization header")

    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError("Invalid Authorization header format. Expected: Bearer <token>")

    return parts[1]


def authenticate_request(auth_header: str, secret_key: str = None) -> dict:
    """Full authentication flow: extract + validate token.

    Args:
        auth_header: Authorization header value
        secret_key: Secret key for validation

    Returns:
        Decoded payload with {user_id, scope, exp, iat}

    Raises:
        AuthError: If authentication fails at any step
    """
    try:
        token = extract_token_from_header(auth_header)
        payload = validate_token(token, secret_key)
        return payload
    except AuthError:
        raise
    except Exception as e:
        raise AuthError(f"Authentication failed: {e}")
