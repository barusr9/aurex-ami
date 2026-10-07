"""Tests for per-user data isolation.

Verifies that User A cannot access, list, or modify User B's data.
This is the core requirement for the deployment: data isolation.
"""

import pytest
from ami.auth import generate_token
from ami import tools
from ami.scope import derive_scope, validate_scope_matches_resource
import jwt

SECRET_KEY = "test-secret-key-12345"


class TestScopeIsolation:
    """Test that scope rules prevent cross-user access."""

    def test_scope_derivation_user_a(self):
        """User A's scope is their email."""
        token = generate_token("raj@example.com", secret_key=SECRET_KEY)
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"],
                            options={"verify_iat": False})
        scope = derive_scope(payload)
        assert scope == "raj@example.com"

    def test_scope_derivation_user_b(self):
        """User B's scope is their email."""
        token = generate_token("mei@example.com", secret_key=SECRET_KEY)
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"],
                            options={"verify_iat": False})
        scope = derive_scope(payload)
        assert scope == "mei@example.com"

    def test_scope_matches_resource_same_user(self):
        """User can access their own orders."""
        assert validate_scope_matches_resource("raj@example.com", "raj@example.com") is True
        assert validate_scope_matches_resource("mei@example.com", "mei@example.com") is True

    def test_scope_matches_resource_different_user(self):
        """User cannot access other users' orders."""
        assert validate_scope_matches_resource("raj@example.com", "mei@example.com") is False
        assert validate_scope_matches_resource("mei@example.com", "raj@example.com") is False


class TestOrderIsolation:
    """Test that tools return 404 (not 403) when user accesses another's data."""

    def test_get_order_own_order(self):
        """User can get their own order."""
        # raj@example.com owns orders 112-1111111-1111111 and 112-2222222-2222222
        result = tools.get_order("112-1111111-1111111", scope="raj@example.com")
        assert "error" not in result
        assert result["order_id"] == "112-1111111-1111111"

    def test_get_order_other_user_order_returns_404(self):
        """User gets 404 (not 403) when fetching another user's order."""
        # mei@example.com owns orders 112-3333333-3333333 and 112-4444444-4444444
        # raj@example.com tries to fetch mei's order
        result = tools.get_order("112-3333333-3333333", scope="raj@example.com")
        assert "error" in result
        assert "No order found" in result["error"]  # 404 message, not 403

    def test_get_order_nonexistent_returns_404(self):
        """Nonexistent order returns 404 regardless of user."""
        result = tools.get_order("000-0000000-0000000", scope="raj@example.com")
        assert "error" in result
        assert "No order found" in result["error"]

    def test_track_package_own_order(self):
        """User can track their own package."""
        result = tools.track_package("112-1111111-1111111", scope="raj@example.com")
        assert "error" not in result
        assert "carrier" in result

    def test_track_package_other_user_returns_404(self):
        """User gets 404 when tracking another's package."""
        result = tools.track_package("112-3333333-3333333", scope="raj@example.com")
        assert "error" in result
        assert "No order found" in result["error"]

    def test_cancel_order_own_order(self, fresh_store):
        """User can cancel their own order (if it's cancellable)."""
        # Order 112-3333333-3333333 (mei's) is in "preparing" state, cancellable.
        # cancel_order now needs an explicit string confirmation ("yes"/"confirm")
        # to actually perform the action; without it it only returns a preview.
        result = tools.cancel_order(
            "112-3333333-3333333", scope="mei@example.com", confirmed="yes")
        assert "error" not in result
        assert result["cancelled"] is True

    def test_cancel_order_other_user_returns_404(self):
        """User gets 404 when canceling another's order."""
        # Order 112-3333333-3333333 belongs to mei, raj tries to cancel it
        result = tools.cancel_order("112-3333333-3333333", scope="raj@example.com")
        assert "error" in result
        assert "No order found" in result["error"]

    def test_start_return_own_order(self, fresh_store):
        """User can start return for their own delivered order (if in window)."""
        # Create a fresh order that's delivered but within return window
        # For testing, we just verify scope isolation — the business logic errors are expected
        # Order 112-1111111-1111111 (raj's) is delivered, test isolation not business logic
        result = tools.start_return("112-1111111-1111111", "defective", scope="raj@example.com")
        # Either succeeds (RMA created) or fails with business logic error (past window),
        # but should NOT fail with "no order found" (404 from scope check)
        if "error" in result:
            # Should be business logic error, not scope error
            assert "No order found" not in result["error"]
        else:
            assert result["rma"]

    def test_start_return_other_user_returns_404(self):
        """User gets 404 when returning another's order."""
        result = tools.start_return("112-4444444-4444444", "defective", scope="raj@example.com")
        assert "error" in result
        assert "No order found" in result["error"]

    def test_find_orders_own_email(self):
        """User can find their own orders."""
        # When scope is used, caller's email parameter should be ignored
        result = tools.find_orders(email="other@example.com", scope="raj@example.com")
        # Scope should override email — should get raj's orders, not "other"'s
        assert "error" not in result
        assert len(result["orders"]) == 2  # raj has 2 orders

    def test_find_orders_no_scope_no_email(self):
        """find_orders without scope or email returns error."""
        result = tools.find_orders()
        assert "error" in result

    def test_find_orders_scope_overrides_email(self):
        """Scope parameter overrides email parameter."""
        # Caller tries to ask for mei's orders but their scope is raj
        result = tools.find_orders(email="mei@example.com", scope="raj@example.com")
        # Should return raj's orders (scope), not mei's (email)
        assert "error" not in result
        assert len(result["orders"]) == 2  # raj's orders


class TestCrossUserScenarios:
    """Multi-user scenarios to verify isolation is complete."""

    def test_user_a_cannot_see_user_b_data_in_sequence(self):
        """Simulates two users accessing system sequentially."""
        # User A (raj) finds their orders
        result_a = tools.find_orders(scope="raj@example.com")
        assert len(result_a["orders"]) == 2

        # User B (mei) finds their orders
        result_b = tools.find_orders(scope="mei@example.com")
        assert len(result_b["orders"]) == 2

        # Confirm they're different
        order_ids_a = {o["order_id"] for o in result_a["orders"]}
        order_ids_b = {o["order_id"] for o in result_b["orders"]}
        assert order_ids_a != order_ids_b
        assert len(order_ids_a & order_ids_b) == 0  # No overlap

    def test_guessed_order_id_returns_404_not_403(self):
        """Guessing order IDs should never confirm existence via 403."""
        # This is important: a 403 would confirm "yes, this order exists"
        # A 404 should be returned even if the order exists but belongs to someone else
        result = tools.get_order("112-3333333-3333333", scope="raj@example.com")
        assert "error" in result
        # The error message should not say "forbidden" — it should say "not found"
        assert "forbidden" not in result["error"].lower()
        assert "not found" in result["error"].lower() or "no order" in result["error"].lower()

    def test_scope_cannot_be_overridden_by_caller(self):
        """Caller cannot override scope via email parameter."""
        # Even if caller passes email="mei@example.com", scope="raj@example.com"
        # should take precedence
        result = tools.find_orders(email="mei@example.com", scope="raj@example.com")
        # Should return raj's orders
        assert "error" not in result
        assert len(result["orders"]) == 2  # raj has 2 orders

        # Verify they're raj's orders by checking order IDs
        order_ids = {o["order_id"] for o in result["orders"]}
        # raj's orders are: 112-1111111-1111111 and 112-2222222-2222222
        assert "112-1111111-1111111" in order_ids or "112-2222222-2222222" in order_ids
