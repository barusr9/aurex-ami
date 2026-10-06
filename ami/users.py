"""Demo users with credentials for testing."""

import hashlib

# Demo users - all have password "demo123"
DEMO_USERS = {
    "demo1@cofy.ai": "demo123",
    "demo2@cofy.ai": "demo123",
    "demo3@cofy.ai": "demo123",
    "demo4@cofy.ai": "demo123",
    "demo5@cofy.ai": "demo123",
}

def verify_credentials(email: str, password: str) -> bool:
    """Verify user email and password.

    Args:
        email: User email
        password: User password

    Returns:
        True if credentials are valid, False otherwise
    """
    if email not in DEMO_USERS:
        return False

    stored_password = DEMO_USERS[email]
    return password == stored_password

def get_all_demo_users() -> dict:
    """Get all demo users (for testing)."""
    return DEMO_USERS.copy()

def user_exists(email: str) -> bool:
    """Check if user exists."""
    return email in DEMO_USERS
