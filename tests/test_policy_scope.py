"""Data isolation at the POLICY layer: the session decides who is asking.

The model writes its own tool-call arguments, so a `scope` it supplies is
untrusted input (prompt injection is a tested threat here). guarded_run must
drop it and use the session's scope. Found in review of PR #2, where
`args.pop("scope") or work.scope` let an injected scope read another
customer's order; the tools.run-level isolation tests did not cover this path.
"""

from ami import policy
from ami.memory import WorkingMemory

RAJ, MEI = "raj@example.com", "mei@example.com"
MEI_ORDER = "112-3333333-3333333"      # mei's Kindle


def test_injected_scope_in_tool_args_is_ignored(fresh_store):
    """Logged in as raj, a tool call claiming mei's scope must still be refused."""
    work = WorkingMemory(scope=RAJ)
    r = policy.guarded_run("get_order", {"order_id": MEI_ORDER, "scope": MEI}, work)
    assert "error" in r
    assert "kindle" not in str(r).lower()


def test_injected_scope_cannot_unlock_a_state_change(fresh_store):
    """Same for cancel: no confirmation preview, no action, for someone else's order."""
    work = WorkingMemory(scope=RAJ)
    work.turn = 1
    r = policy.guarded_run("cancel_order", {"order_id": MEI_ORDER, "scope": MEI}, work)
    assert "error" in r and not r.get("needs_confirmation")
    assert work.pending is None


def test_session_scope_still_works(fresh_store):
    """Control: the session's own scope is honoured as before."""
    work = WorkingMemory(scope=MEI)
    r = policy.guarded_run("get_order", {"order_id": MEI_ORDER}, work)
    assert r.get("order_id") == MEI_ORDER


def test_no_session_scope_means_no_access_even_if_args_claim_one(fresh_store):
    work = WorkingMemory(scope=None)
    r = policy.guarded_run("get_order", {"order_id": MEI_ORDER, "scope": MEI}, work)
    assert "error" in r
