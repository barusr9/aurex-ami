"""Scope derivation and enforcement for per-user data isolation.

Scope = the set of resources (orders, tickets) a user can access.
For MVP: scope = user_id (1:1 mapping).

Scope is:
1. Embedded in JWT token (immutable)
2. Validated server-side (never accepted from caller)
3. Applied at data access layer (store.py filters by scope)

This module derives scope from token payload and validates it.
Caller cannot override scope via query params, headers, or request body.
"""


class ScopeError(Exception):
    """Scope validation failed."""
    pass


def derive_scope(auth_payload: dict) -> str:
    """Derive scope from authenticated user token.

    For MVP: scope = user_id (1:1 mapping).

    Args:
        auth_payload: Decoded JWT payload with {user_id, scope, exp, iat}

    Returns:
        Scope string (user_id)

    Raises:
        ScopeError: If payload missing required fields
    """
    if not auth_payload:
        raise ScopeError("Missing authentication payload")

    if "scope" not in auth_payload:
        raise ScopeError("Missing 'scope' in token payload")

    if "user_id" not in auth_payload:
        raise ScopeError("Missing 'user_id' in token payload")

    scope = auth_payload["scope"]
    user_id = auth_payload["user_id"]

    # For MVP, scope must equal user_id
    if scope != user_id:
        raise ScopeError(f"Scope mismatch: scope={scope}, user_id={user_id}")

    return scope


def validate_scope_matches_resource(scope: str, resource_owner_id: str) -> bool:
    """Check if scope allows access to resource.

    For MVP: scope = user_id, so check if scope == resource_owner_id.

    Args:
        scope: User's scope (from token)
        resource_owner_id: Owner of the resource (from DB)

    Returns:
        True if access allowed, False otherwise
    """
    if not scope or not resource_owner_id:
        return False

    # For MVP: exact match required
    return scope == resource_owner_id


class RequestScopeValidator:
    """Validates that caller cannot override scope via request parameters.

    Caller might try to override scope via:
    - Query params: ?scope=admin or ?user=other_user
    - Headers: X-Scope: admin
    - Body: {scope: admin}

    This validator rejects all attempts and only uses server-derived scope.
    """

    @staticmethod
    def validate_no_scope_override(query_params: dict, headers: dict, body: dict = None) -> None:
        """Ensure caller is not trying to override scope.

        Args:
            query_params: Query string parameters
            headers: HTTP headers
            body: Request body (dict or None)

        Raises:
            ScopeError: If any scope override attempt detected
        """
        # Check query params
        suspicious_keys = ["scope", "user", "user_id", "owner", "owner_id"]
        for key in query_params:
            if key.lower() in suspicious_keys:
                raise ScopeError(f"Attempt to override scope via query param: {key}={query_params[key]}")

        # Check headers
        suspicious_headers = ["X-Scope", "X-User", "X-User-Id", "X-Owner"]
        for header in headers:
            if header.lower() in [h.lower() for h in suspicious_headers]:
                raise ScopeError(f"Attempt to override scope via header: {header}")

        # Check body
        if body:
            suspicious_body_keys = ["scope", "user_id", "owner_id", "owner"]
            for key in body:
                if key.lower() in suspicious_body_keys:
                    raise ScopeError(f"Attempt to override scope via body: {key}={body[key]}")

    @staticmethod
    def extract_resource_id_safely(path: str, body: dict = None) -> str or None:
        """Extract resource ID from request (e.g., order ID, ticket ID).

        For a request like GET /orders/123, extract 123.

        Args:
            path: URL path
            body: Request body (may contain resource ID)

        Returns:
            Resource ID string, or None if not found
        """
        # Simple extraction: assume last path segment is resource ID
        # e.g., /orders/123 -> 123, /chats/abc -> abc
        parts = path.strip("/").split("/")
        if parts and parts[-1] and parts[-1][0].isalnum():
            return parts[-1]
        return None
