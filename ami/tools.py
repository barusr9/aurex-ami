"""Element 4 of the agent: ACTION — the tools, and the guardrails around them.

Two ideas to notice here:

1. Every tool returns a plain dict. On failure it returns
   {"error": ...} instead of raising, so the model can read the problem
   and explain it to the customer.

2. The guardrails live in the TOOLS, not in the prompt. A prompt rule is
   a suggestion the model can talk itself out of. A check inside
   cancel_order() is a rule it cannot get around.

3. Scope isolation: all tools check that the order belongs to the current user.
   Orders from other users return "error" (not accessible), preventing access
   even if an order ID is guessed or known.
"""

from datetime import date

from ami import knowledge
from ami import observe
from ami import store


# Scope validation: map user_id to email for access control
# For MVP: user_id = email (simple 1:1 mapping)
USER_EMAILS = {
    "raj@example.com": "raj@example.com",
    "mei@example.com": "mei@example.com",
}

# --------------------------------------------------------------------------
# The tools themselves
# --------------------------------------------------------------------------


def find_orders(email=None, scope=None):
    """Look up a customer's orders when they don't know the order number.

    AUTHENTICATION REQUIRED: Unauthenticated users cannot look up orders.

    With scope isolation: only return orders matching the user's scope (email).
    Caller cannot pass a different email.
    """
    # CRITICAL: If no scope, user is NOT authenticated
    # They cannot look up ANY orders, even with email
    if not scope:
        return {"error": "Authentication required. Please log in to view your orders."}

    # With authentication, use ONLY the scope, NEVER accept caller's email param
    # This prevents a user from looking up another user's orders
    lookup_email = scope

    hits = [
        {"order_id": o["order_id"], "item": o["item"],
         "status": o["status"], "ordered_on": o["ordered_on"]}
        for o in store.ORDERS.values()
        if o["email"].lower() == lookup_email.lower().strip()
    ]
    if not hits:
        return {"error": f"No orders found for {lookup_email}."}
    return {"orders": hits}


def get_order(order_id, scope=None):
    """Full detail for one order. AUTHENTICATION REQUIRED.

    Scope checks: order must belong to authenticated user.
    """
    # CRITICAL: Authentication required to view order details
    if not scope:
        return {"error": "Authentication required. Please log in to view order details."}

    order = store.ORDERS.get(order_id.strip())
    if not order:
        # Return 404 (not found), not "access denied" (protects order id guessing)
        return {"error": f"No order found with id {order_id}."}

    # Check scope: order email must match user's scope (user_id = email)
    if order["email"].lower() != scope.lower():
        # User trying to access someone else's order: return 404, not 403
        return {"error": f"No order found with id {order_id}."}

    return {
        "order_id": order["order_id"],
        "item": order["item"],
        "price": order["price"],
        "status": order["status"],
        "ordered_on": order["ordered_on"],
        "delivered_on": order["delivered_on"],
        "eta": order.get("eta"),
    }


def track_package(order_id, scope=None):
    """The carrier scan history for an order. AUTHENTICATION REQUIRED.

    Scope checks: order must belong to authenticated user.
    """
    # CRITICAL: Authentication required for tracking
    if not scope:
        return {"error": "Authentication required. Please log in to view tracking information."}

    order = store.ORDERS.get(order_id.strip())
    if not order:
        return {"error": f"No order found with id {order_id}."}

    # Check scope: order email must match user's scope
    if order["email"].lower() != scope.lower():
        return {"error": f"No order found with id {order_id}."}

    if not order["tracking"]:
        return {"error": "No tracking events yet for this order."}
    return {
        "carrier": order["carrier"],
        "eta": order.get("eta"),
        "events": [{"date": d, "detail": t} for d, t in order["tracking"]],
    }


def eligibility(tool, order):
    """Why this state-changing tool cannot run on this order, or None.

    The business rules only — no auth, no confirmation. Both the tools and
    the policy layer call it, so the policy can refuse an impossible request
    straight away instead of first asking the customer to confirm it.
    """
    oid, status = order["order_id"], order["status"]
    if tool == "cancel_order":
        if status in ("shipped", "delivered"):
            return {"error": f"Order {oid} already {status} and cannot "
                             f"be cancelled. It can be returned instead."}
        if status == "cancelled":
            return {"error": f"Order {oid} is already cancelled."}
    elif tool == "start_return":
        if status != "delivered":
            return {"error": f"Order {oid} is '{status}', not delivered "
                             f"yet, so it can't be returned."}
        days = (date.today() - date.fromisoformat(order["delivered_on"])).days
        if days > store.RETURN_WINDOW_DAYS:
            return {"error": f"Delivered {days} days ago, past the "
                             f"{store.RETURN_WINDOW_DAYS}-day return window. "
                             f"A human agent can review an exception."}
    return None


def cancel_order(order_id, scope=None, confirmed=False):
    """Cancel an order — only allowed before it ships. GUARDRAIL.

    AUTHENTICATION REQUIRED. Also requires explicit user confirmation.

    Args:
        order_id: Order to cancel
        scope: User's authentication scope (REQUIRED)
        confirmed: Must be True for cancellation to proceed (safety check)
    """
    # CRITICAL: Authentication required for order modifications
    if not scope:
        return {"error": "Authentication required. Please log in to cancel an order."}

    order = store.ORDERS.get(order_id.strip())
    if not order:
        return {"error": f"No order found with id {order_id}."}

    # Check scope: order email must match user's scope
    if order["email"].lower() != scope.lower():
        return {"error": f"No order found with id {order_id}."}

    # Eligibility BEFORE confirmation: never ask a customer to confirm
    # something that cannot happen (a shipped order, an old return).
    refusal = eligibility("cancel_order", order)
    if refusal:
        return refusal

    # CRITICAL: Require explicit confirmation before modifying account
    if not confirmed:
        return {
            "error": "Confirmation required. Please explicitly confirm: do you want to cancel this order?",
            "confirmation_required": True,
            "order_id": order_id,
            "item": order["item"],
            "price": order["price"],
        }

    order["status"] = "cancelled"
    return {
        "cancelled": True,
        "order_id": order["order_id"],
        "refund_amount": order["price"],
        "refund_eta": "3-5 business days to the original payment method",
    }


def start_return(order_id, reason, scope=None, confirmed=False):
    """Open a return — only for delivered orders inside the return window. GUARDRAIL.

    AUTHENTICATION REQUIRED. Also requires explicit user confirmation.

    Args:
        order_id: Order to return
        reason: Reason for return (in customer's words)
        scope: User's authentication scope (REQUIRED)
        confirmed: Must be True for return to proceed (safety check)
    """
    # CRITICAL: Authentication required for order modifications
    if not scope:
        return {"error": "Authentication required. Please log in to start a return."}

    order = store.ORDERS.get(order_id.strip())
    if not order:
        return {"error": f"No order found with id {order_id}."}

    # Check scope: order email must match user's scope
    if order["email"].lower() != scope.lower():
        return {"error": f"No order found with id {order_id}."}

    refusal = eligibility("start_return", order)
    if refusal:
        return refusal

    # CRITICAL: Require explicit confirmation before modifying account
    if not confirmed:
        return {
            "error": "Confirmation required. Please explicitly confirm: do you want to return this order?",
            "confirmation_required": True,
            "order_id": order_id,
            "item": order["item"],
            "reason": reason,
        }

    rma = f"RMA-{len(store.RETURNS) + 1001}"
    store.RETURNS[rma] = {"order_id": order["order_id"], "reason": reason}
    order["status"] = "return started"
    return {
        "rma": rma,
        "order_id": order["order_id"],
        "refund_amount": order["price"],
        "instructions": "Drop off at any UPS Store with the QR code emailed "
                        "to you. Refund issues once we scan the item.",
    }


def search_knowledge(question):
    """Look up what is written down. The RAG tool.

    Everything else here reads the order database. This one reads the
    filing cabinet: the rules a human support agent would have been
    trained on, which the agent can now quote instead of guessing at.

    One argument, on purpose — see knowledge.search() for why the
    obvious second one (a category to search within) was removed.
    """
    hits = knowledge.search(question, k=3)
    return {"passages": [{"source": h["source"], "category": h["category"],
                          "policy": h["heading"], "text": h["text"]}
                         for h in hits]}


def escalate(summary, scope=None):
    """Hand off to a human. The honest answer when no other tool fits.

    Each call opens a unique ticket (recorded in state/escalations.jsonl) and
    hands it to the configured backend; see ami/escalations.py. `scope` is
    the logged-in customer, injected by run(), so the ticket names them.
    """
    from ami import escalations                 # local import: avoids a cycle via observe
    record = escalations.open_ticket(summary, customer=scope)
    ref = escalations.deliver(record)
    return {
        "escalated": True,
        "ticket": record["ticket"],
        "message": "A human agent will email you within 24 hours.",
        "summary": summary,
        **({"ref": ref} if ref else {}),
    }


# --------------------------------------------------------------------------
# Descriptions the model reads to decide which tool to call
# --------------------------------------------------------------------------

def _tool(name, description, properties, required):
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


SCHEMAS = [
    _tool("find_orders",
          "List the logged-in customer's orders (when they lack an order number).",
          {"email": {"type": "string", "description": "Customer email address"}},
          ["email"]),

    _tool("get_order",
          "Status and details of one order.",
          {"order_id": {"type": "string", "description": "e.g. 112-1111111-1111111"}},
          ["order_id"]),

    _tool("track_package",
          "Carrier tracking events and delivery estimate.",
          {"order_id": {"type": "string", "description": "Order number"}},
          ["order_id"]),

    _tool("cancel_order",
          "Cancel an unshipped order and refund it.",
          {"order_id": {"type": "string", "description": "Order number"},
           "confirmed": {"type": "string", "enum": ["yes"],
                        "description": "Only after the customer said yes in a later message"}},
          ["order_id"]),

    _tool("start_return",
          "Start a return for a delivered order (issues an RMA).",
          {"order_id": {"type": "string", "description": "Order number"},
           "reason": {"type": "string",
                      "description": "Customer's reason, in their words"},
           "confirmed": {"type": "string", "enum": ["yes"],
                        "description": "Only after the customer said yes in a later message"}},
          ["order_id", "reason"]),

    _tool("search_knowledge",
          "Search the written policies, agent rules, tone guide and regulations. "
          "Use for any question about the rules; quote what it returns.",
          {"question": {"type": "string"}},
          ["question"]),

    _tool("escalate",
          "Hand off to a human agent.",
          {"summary": {"type": "string", "description": "One line for the human agent"}},
          ["summary"]),
]

REGISTRY = {
    "find_orders": find_orders,
    "get_order": get_order,
    "track_package": track_package,
    "cancel_order": cancel_order,
    "start_return": start_return,
    "search_knowledge": search_knowledge,
    "escalate": escalate,
}


def run(name, args, scope=None):
    """Execute a tool the model asked for. Never raises — errors come back as data.

    scope: user's scope (user_id/email) for data isolation. Passed to tools that
           need to validate access (get_order, cancel_order, start_return, etc.)
    """
    with observe.timer() as t:
        result = _dispatch(name, args, scope=scope)
    observe.log("tool", tool=name, args=args, ms=t.ms,
                ok="error" not in result,
                error=result.get("error"),
                retryable=bool(result.get("retry")))
    return result


def _dispatch(name, args, scope=None):
    fn = REGISTRY.get(name)
    if not fn:
        return {"error": f"No such tool: {name}"}
    try:
        # Only inject scope into tools that need it (order access, modifications)
        # search_knowledge doesn't need scope; escalate takes it only to name the customer on the ticket
        scope_required_tools = {"find_orders", "get_order", "track_package",
                                "cancel_order", "start_return", "escalate"}
        if scope and name in scope_required_tools:
            args["scope"] = scope
        return fn(**args)
    except TypeError as e:
        # The agent called its own tool wrongly. That is not a policy
        # refusal — it is a mistake it can fix, so say so explicitly.
        return {"error": f"Bad call to {name}: {e}", "retry": True}
