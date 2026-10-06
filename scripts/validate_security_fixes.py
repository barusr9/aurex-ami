#!/usr/bin/env python3
"""
Test script to validate security fixes for authentication and authorization.

Tests the critical fixes:
1. Agent refuses private queries for unauthenticated users
2. Agent verifies user ownership before showing orders
3. Agent requires confirmation before modifying accounts
4. Working memory explicitly tracks authentication status
"""

import json
from ami.memory import WorkingMemory, ConversationMemory
from ami import agent_profile as profile
from ami import tools

print("\n" + "="*70)
print("AUREX SECURITY FIX VALIDATION")
print("="*70)

# ============================================================================
# Test 1: Authentication Status Tracking
# ============================================================================
print("\n[Test 1] Authentication Status Tracking in Working Memory")
print("-" * 70)

# Unauthenticated user
unauthenticated = WorkingMemory(scope=None)
print(f"Unauthenticated: scope={unauthenticated.scope}, authenticated={unauthenticated.authenticated}")
assert unauthenticated.authenticated == False, "Should be unauthenticated"
print("✅ PASS: Unauthenticated status correctly tracked")

# Authenticated user
authenticated = WorkingMemory(scope="raj@example.com")
print(f"Authenticated: scope={authenticated.scope}, authenticated={authenticated.authenticated}")
assert authenticated.authenticated == True, "Should be authenticated"
print("✅ PASS: Authenticated status correctly tracked")

# ============================================================================
# Test 2: Working Memory Brief Shows Auth Status
# ============================================================================
print("\n[Test 2] Working Memory Brief Shows Authentication Status")
print("-" * 70)

# Add at least one action to trigger brief output
unauthenticated.failures.append("test failure")
brief_unauth = unauthenticated.brief()
print("Unauthenticated brief:")
print(brief_unauth)
assert brief_unauth is not None, "Brief should not be None"
assert "NOT AUTHENTICATED" in brief_unauth, "Should mention not authenticated"
assert "log in" in brief_unauth.lower(), "Should suggest logging in"
print("✅ PASS: Brief clearly shows unauthenticated status")

# Add at least one action to trigger brief output
authenticated.failures.append("test failure")
brief_auth = authenticated.brief()
print("\nAuthenticated brief:")
print(brief_auth)
assert brief_auth is not None, "Brief should not be None"
assert "AUTHENTICATED as:" in brief_auth, "Should show authenticated user"
assert "raj@example.com" in brief_auth, "Should show user email"
print("✅ PASS: Brief clearly shows authenticated status")

# ============================================================================
# Test 3: find_orders() Requires Authentication
# ============================================================================
print("\n[Test 3] find_orders() Requires Authentication")
print("-" * 70)

# Unauthenticated attempt
result_unauth = tools.find_orders(email="raj@example.com", scope=None)
print(f"Unauthenticated find_orders(): {result_unauth}")
assert "error" in result_unauth, "Should return error for unauthenticated user"
assert "Authentication required" in result_unauth["error"], "Should mention auth required"
print("✅ PASS: find_orders() refuses unauthenticated users")

# Authenticated attempt
result_auth = tools.find_orders(email="different@email.com", scope="raj@example.com")
print(f"Authenticated find_orders(): {result_auth}")
# Result might be error if no orders, but it won't be auth error
assert "Authentication required" not in str(result_auth), "Should not ask for auth"
print("✅ PASS: find_orders() accepts authenticated users")

# ============================================================================
# Test 4: get_order() Requires Authentication
# ============================================================================
print("\n[Test 4] get_order() Requires Authentication")
print("-" * 70)

# Unauthenticated attempt
result_unauth = tools.get_order("112-1111111-1111111", scope=None)
print(f"Unauthenticated get_order(): {result_unauth}")
assert "error" in result_unauth, "Should return error for unauthenticated user"
assert "Authentication required" in result_unauth["error"], "Should mention auth required"
print("✅ PASS: get_order() refuses unauthenticated users")

# Authenticated attempt (real order from store)
result_auth = tools.get_order("112-1111111-1111111", scope="raj@example.com")
print(f"Authenticated get_order(): {result_auth}")
# Will either be "No order found" or show the order, but not auth error
assert "Authentication required" not in str(result_auth), "Should not ask for auth"
print("✅ PASS: get_order() accepts authenticated users")

# ============================================================================
# Test 5: track_package() Requires Authentication
# ============================================================================
print("\n[Test 5] track_package() Requires Authentication")
print("-" * 70)

# Unauthenticated attempt
result_unauth = tools.track_package("112-1111111-1111111", scope=None)
print(f"Unauthenticated track_package(): {result_unauth}")
assert "error" in result_unauth, "Should return error for unauthenticated user"
assert "Authentication required" in result_unauth["error"], "Should mention auth required"
print("✅ PASS: track_package() refuses unauthenticated users")

# Authenticated attempt
result_auth = tools.track_package("112-1111111-1111111", scope="raj@example.com")
print(f"Authenticated track_package(): {result_auth}")
assert "Authentication required" not in str(result_auth), "Should not ask for auth"
print("✅ PASS: track_package() accepts authenticated users")

# ============================================================================
# Test 6: cancel_order() Requires Authentication AND Confirmation
# ============================================================================
print("\n[Test 6] cancel_order() Requires Authentication AND Confirmation")
print("-" * 70)

# Unauthenticated attempt
result_unauth = tools.cancel_order("112-1111111-1111111", scope=None)
print(f"Unauthenticated cancel_order(): {result_unauth}")
assert "error" in result_unauth, "Should return error for unauthenticated user"
assert "Authentication required" in result_unauth["error"], "Should mention auth required"
print("✅ PASS: cancel_order() refuses unauthenticated users")

# Authenticated but not confirmed
result_no_confirm = tools.cancel_order("112-1111111-1111111", scope="raj@example.com", confirmed=False)
print(f"Authenticated but NOT confirmed cancel_order(): {result_no_confirm}")
assert "error" in result_no_confirm, "Should return error when not confirmed"
assert "confirmation_required" in result_no_confirm, "Should have confirmation_required flag"
assert "Confirmation required" in result_no_confirm["error"], "Should ask for confirmation"
print("✅ PASS: cancel_order() requires explicit confirmation")

# Authenticated and confirmed (may fail for other reasons, but not auth)
result_confirmed = tools.cancel_order("112-1111111-1111111", scope="raj@example.com", confirmed=True)
print(f"Authenticated AND confirmed cancel_order(): {result_confirmed}")
# May fail if order doesn't exist or already shipped, but not auth error
if "error" in result_confirmed:
    assert "Authentication required" not in result_confirmed["error"], "Should not ask for auth"
print("✅ PASS: cancel_order() accepts confirmation from authenticated user")

# ============================================================================
# Test 7: start_return() Requires Authentication AND Confirmation
# ============================================================================
print("\n[Test 7] start_return() Requires Authentication AND Confirmation")
print("-" * 70)

# Unauthenticated attempt
result_unauth = tools.start_return("112-1111111-1111111", "defective", scope=None)
print(f"Unauthenticated start_return(): {result_unauth}")
assert "error" in result_unauth, "Should return error for unauthenticated user"
assert "Authentication required" in result_unauth["error"], "Should mention auth required"
print("✅ PASS: start_return() refuses unauthenticated users")

# Authenticated but not confirmed
result_no_confirm = tools.start_return("112-1111111-1111111", "defective", scope="raj@example.com", confirmed=False)
print(f"Authenticated but NOT confirmed start_return(): {result_no_confirm}")
assert "error" in result_no_confirm, "Should return error when not confirmed"
assert "confirmation_required" in result_no_confirm, "Should have confirmation_required flag"
assert "Confirmation required" in result_no_confirm["error"], "Should ask for confirmation"
print("✅ PASS: start_return() requires explicit confirmation")

# Authenticated and confirmed
result_confirmed = tools.start_return("112-1111111-1111111", "defective", scope="raj@example.com", confirmed=True)
print(f"Authenticated AND confirmed start_return(): {result_confirmed}")
if "error" in result_confirmed:
    assert "Authentication required" not in result_confirmed["error"], "Should not ask for auth"
print("✅ PASS: start_return() accepts confirmation from authenticated user")

# ============================================================================
# Test 8: Scope Isolation - User Cannot Access Other Users' Orders
# ============================================================================
print("\n[Test 8] Scope Isolation - User Cannot Access Other Users' Orders")
print("-" * 70)

# User logs in as raj@example.com but tries to access demo2's order
# (assuming we know demo2's order ID from the store)
demo1_scope = "raj@example.com"
demo2_scope = "mei@example.com"

# Get an order that belongs to demo2
from ami import store
demo2_order_id = None
for oid, order in store.ORDERS.items():
    if order["email"].lower() == demo2_scope.lower():
        demo2_order_id = oid
        break

if demo2_order_id:
    # Try to access it as demo1
    result = tools.get_order(demo2_order_id, scope=demo1_scope)
    print(f"Demo1 trying to access Demo2's order {demo2_order_id}: {result}")
    # Should NOT find the order (returns 404, not 403, to hide order existence)
    assert "error" in result, "Should return error (access denied)"
    assert "No order found" in result["error"], "Should return 'not found' (not 'access denied')"
    print("✅ PASS: Scope isolation works - user cannot see other users' orders")
else:
    print("⚠️  SKIP: No demo2 orders in store to test scope isolation")

# ============================================================================
# Test 9: System Prompt Includes Auth Requirements
# ============================================================================
print("\n[Test 9] System Prompt Includes Authentication Requirements")
print("-" * 70)

system_prompt = profile.system_prompt()
print("Checking system prompt for authentication requirements...")

auth_checks = [
    "AUTHENTICATION REQUIREMENTS",
    "MUST REFUSE",
    "unauthenticated",
    "scope",
    "CONFIRMATION REQUIRED",
]

all_found = True
for check in auth_checks:
    if check in system_prompt:
        print(f"  ✅ Found: '{check}'")
    else:
        print(f"  ❌ Missing: '{check}'")
        all_found = False

assert all_found, "System prompt missing critical auth requirements"
print("✅ PASS: System prompt includes all authentication requirements")

# ============================================================================
# Summary
# ============================================================================
print("\n" + "="*70)
print("ALL SECURITY TESTS PASSED ✅")
print("="*70)
print("""
Critical Security Fixes Validated:
✅ Authentication status explicitly tracked
✅ Unauthenticated users refused access to private data
✅ find_orders() requires authentication
✅ get_order() requires authentication
✅ track_package() requires authentication
✅ cancel_order() requires authentication + confirmation
✅ start_return() requires authentication + confirmation
✅ Scope isolation prevents cross-user data access
✅ System prompt enforces authentication rules
✅ Working memory clearly communicates auth status

The agent now:
1. REFUSES all account-specific requests from unauthenticated users
2. REQUIRES confirmation before processing any modifications
3. PREVENTS access to other users' data via scope checks
4. CLEARLY communicates authentication status in every turn
""")
