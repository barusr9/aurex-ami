"""Element 2 of the agent: MEMORY.

There are two kinds, and mixing them up is the usual beginner mistake.

CONVERSATION MEMORY — what was SAID.
    The transcript. Grows every turn, gets sent to the model on every call,
    and is the thing that makes turn 5 understand the word "it". Its job is
    recall, and its enemy is length.

WORKING MEMORY — what is KNOWN and DONE.
    The agent's scratchpad for the current task: facts confirmed by tools,
    actions already taken, the goal it is chasing. It is small, structured,
    and rewritten as the agent learns. Its job is not to remember words but
    to stop the agent repeating itself.

You can see the difference in one question: "did I already escalate this?"
The transcript can answer it only by re-reading everything. Working memory
answers it by looking at one field.
"""

import json
import time
from collections import OrderedDict


class ConversationMemory:
    """The dialogue transcript, in the shape the model expects."""

    def __init__(self, system_prompt, max_turns=None):
        self.system = system_prompt
        self.history = []          # everything after the system message
        # How many trailing messages to resend. Lower = cheaper (fewer input
        # tokens on long conversations) at the cost of forgetting older turns.
        # Defaults to config.MAX_CONVERSATION_TURNS so it is tunable in one
        # place rather than hardcoded here. See S1 (cost).
        if max_turns is None:
            from ami.config import config
            max_turns = config.MAX_CONVERSATION_TURNS
        self.max_turns = max_turns

    def add_user(self, text):
        self.history.append({"role": "user", "content": text})

    def add_assistant(self, message):
        """Takes the raw model message (it may carry tool_calls)."""
        self.history.append(message)

    def add_observation(self, tool_call_id, result):
        self.history.append({
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(result),
        })

    def messages(self, extra_system=None):
        """What we actually send. `extra_system` is where working memory rides in."""
        head = [{"role": "system", "content": self.system}]
        if extra_system:
            head.append({"role": "system", "content": extra_system})
        return head + self._trimmed()

    def _trimmed(self):
        """Keep the transcript from growing forever.

        We trim from the front, but never leave a 'tool' message stranded
        without the assistant message that requested it — the API rejects that.
        """
        if len(self.history) <= self.max_turns:
            return self.history
        cut = len(self.history) - self.max_turns
        while cut < len(self.history) and self.history[cut].get("role") == "tool":
            cut += 1
        return self.history[cut:]

    def __len__(self):
        return len(self.history)

    # -- persistence ------------------------------------------------------

    def to_dict(self):
        return {"history": self.history, "max_turns": self.max_turns}

    @classmethod
    def from_dict(cls, system_prompt, data):
        # None -> fall back to config default (see __init__).
        m = cls(system_prompt, max_turns=data.get("max_turns"))
        m.history = data.get("history", [])
        return m


class WorkingMemory:
    """What the agent has established during this task.

    Updated from tool observations, never from the customer's claims —
    a customer saying "my order shipped" is not a fact, a tool saying it is.
    """

    def __init__(self, scope=None):
        self.customer_email = None
        self.orders = {}        # order_id -> what we looked up
        self.actions = []       # things that actually changed something
        self.failures = []      # what we tried that was refused, and why
        self.escalation = None  # ticket number, once we have one
        self.scope = scope      # user's scope (user_id/email) for data isolation
        self.authenticated = bool(scope)  # Track authentication status explicitly
        self.turn = 0           # which turn we're on (for policy layer)
        self.pending = None     # pending confirmation state: {key: [tool, order_id], turn: N}
        self.session_id = None  # session ID (for long-term memory exclusion)

    # -- writing ----------------------------------------------------------

    def record(self, tool, args, result):
        """Fold one Observation into what we know."""
        if tool == "find_orders" and "orders" in result:
            self.customer_email = args.get("email")
            for o in result["orders"]:
                self.orders.setdefault(o["order_id"], {}).update(o)

        elif tool in ("get_order", "track_package") and "error" not in result:
            oid = args.get("order_id")
            if oid:
                self.orders.setdefault(oid, {}).update(
                    {k: v for k, v in result.items() if k != "events"})

        if "error" in result:
            # A retryable error is the agent's own slip, not a decision about
            # the customer. Logging it would poison working memory with a
            # refusal that never happened.
            if not result.get("retry"):
                self.failures.append(f"{tool}({args.get('order_id', '')}) "
                                     f"refused: {result['error']}")
            return

        if tool == "cancel_order":
            self.actions.append(f"Cancelled {result['order_id']}, "
                                f"${result['refund_amount']} refunded")
            self.orders.setdefault(result["order_id"], {})["status"] = "cancelled"
        elif tool == "start_return":
            self.actions.append(f"Return started for {result['order_id']}, "
                                f"{result['rma']}, ${result['refund_amount']}")
            self.orders.setdefault(result["order_id"], {})["status"] = "return started"
        elif tool == "escalate":
            self.escalation = result["ticket"]
            self.actions.append(f"Escalated to a human, ticket {result['ticket']}")

    # -- reading ----------------------------------------------------------

    def brief(self):
        """Working memory as a short note the model reads before every step."""
        if not any([self.customer_email, self.orders, self.actions,
                    self.failures, self.escalation, self.scope]):
            return None

        lines = ["WHAT YOU ALREADY KNOW (do not look these up again):"]
        if self.scope:
            lines.append(f"- User AUTHENTICATED as: {self.scope}")
            lines.append(f"  (This user can access account-specific data)")
        else:
            lines.append(f"- User NOT AUTHENTICATED")
            lines.append(f"  (Cannot access account-specific data. Ask them to log in.)")
        if self.customer_email:
            lines.append(f"- Customer email: {self.customer_email}")
        for oid, o in self.orders.items():
            bits = [f"{oid}: {o.get('item', 'unknown item')}",
                    f"status={o.get('status', '?')}"]
            if o.get("eta"):
                bits.append(f"eta={o['eta']}")
            if o.get("delivered_on"):
                bits.append(f"delivered={o['delivered_on']}")
            lines.append("- " + ", ".join(bits))
        if self.actions:
            lines.append("ALREADY DONE (never do these twice):")
            lines += [f"- {a}" for a in self.actions]
        if self.failures:
            lines.append("ALREADY REFUSED (do not retry):")
            lines += [f"- {f}" for f in self.failures]
        if self.escalation:
            lines.append(f"NOTE: this conversation is already escalated as "
                         f"{self.escalation}. Refer to that ticket rather than "
                         f"escalating again.")
        return "\n".join(lines)

    # -- persistence ------------------------------------------------------

    def to_dict(self):
        return {"customer_email": self.customer_email, "orders": self.orders,
                "actions": self.actions, "failures": self.failures,
                "escalation": self.escalation, "scope": self.scope,
                "authenticated": self.authenticated, "turn": self.turn,
                "pending": self.pending, "session_id": self.session_id}

    @classmethod
    def from_dict(cls, data):
        w = cls(scope=data.get("scope"))
        w.customer_email = data.get("customer_email")
        w.orders = data.get("orders", {})
        w.actions = data.get("actions", [])
        w.failures = data.get("failures", [])
        w.escalation = data.get("escalation")
        w.authenticated = data.get("authenticated", bool(w.scope))
        w.turn = data.get("turn", 0)
        w.pending = data.get("pending")
        w.session_id = data.get("session_id")
        return w

    def __repr__(self):
        return (f"<WorkingMemory orders={len(self.orders)} "
                f"actions={len(self.actions)} escalation={self.escalation}>")


class LongTermMemory:
    """Stage 2: Persistent customer memory across sessions with LRU cache + TTL.

    Caches customer profiles in memory with two eviction policies:
    - LRU (Least Recently Used): cap at MAX_CACHED_CUSTOMERS to prevent unbounded growth
    - TTL (Time-To-Live): entries expire after ENTRY_TTL_HOURS of inactivity
    """

    MAX_CACHED_CUSTOMERS = 5000
    ENTRY_TTL_HOURS = 24

    def __init__(self, customer_id=None):
        self.customer_id = customer_id
        self.history = []      # conversation snippets remembered
        self.preferences = {}  # customer preferences
        self.issues = []       # recurring issues
        self.customers = OrderedDict()  # LRU cache: customer_email -> memory
        self.access_times = {}  # customer_email -> last_access_timestamp (for TTL)

    def add_note(self, note: str):
        """Add a memorable detail about this customer."""
        if note and note not in self.history:
            self.history.append(note)

    def get_summary(self):
        """Return a brief summary for the system prompt."""
        if not self.history:
            return "First conversation with this customer."
        return "; ".join(self.history[:3])  # Last 3 memorable moments

    def recall(self, customer_email, session_id=None):
        """Recall previous context about this customer (from other sessions only).

        Args:
            customer_email: Email to look up memories for
            session_id: Current session ID (used to exclude current session from recall)

        Returns:
            Summary string of previous interactions, or None if no history.

        LRU + TTL eviction: removes stale entries and enforces cache size limit.
        """
        if not customer_email:
            return None

        # Check if entry exists and is not stale
        if customer_email in self.access_times:
            age_seconds = time.time() - self.access_times[customer_email]
            age_hours = age_seconds / 3600
            if age_hours > self.ENTRY_TTL_HOURS:
                # Entry expired: remove it
                del self.customers[customer_email]
                del self.access_times[customer_email]
                return None

        if customer_email not in self.customers:
            return None

        # Update access time (mark as recently used)
        self.access_times[customer_email] = time.time()

        # Move to end of OrderedDict (mark as most recently used)
        self.customers.move_to_end(customer_email)

        # LRU eviction: if cache exceeded, remove oldest (least recently used)
        while len(self.customers) > self.MAX_CACHED_CUSTOMERS:
            evicted_email, _ = self.customers.popitem(last=False)
            if evicted_email in self.access_times:
                del self.access_times[evicted_email]

        # Return the summary from previous sessions
        summary = self.customers.get(customer_email, {}).get("summary")
        return summary if summary else None

    def remember(self, work, session_id=None):
        """Store customer context for future sessions.

        Args:
            work: WorkingMemory object from this session
            session_id: Current session ID (used to avoid recalling current session)

        LRU + TTL: marks entry as recently used and enforces cache limit.
        """
        if not work or not hasattr(work, 'customer_email') or not work.customer_email:
            return

        customer_email = work.customer_email

        if customer_email not in self.customers:
            self.customers[customer_email] = {"notes": [], "summary": None}

        # Store memorable facts about this conversation
        if work.orders:
            note = f"Has {len(work.orders)} orders"
            if note not in self.customers[customer_email]["notes"]:
                self.customers[customer_email]["notes"].append(note)

        if work.escalation:
            note = f"Has escalated tickets"
            if note not in self.customers[customer_email]["notes"]:
                self.customers[customer_email]["notes"].append(note)

        # Update summary with all collected notes
        if self.customers[customer_email]["notes"]:
            self.customers[customer_email]["summary"] = \
                "; ".join(self.customers[customer_email]["notes"][:3])

        # Update access time and mark as recently used
        self.access_times[customer_email] = time.time()
        self.customers.move_to_end(customer_email)

        # LRU eviction: if cache exceeded, remove oldest entry
        while len(self.customers) > self.MAX_CACHED_CUSTOMERS:
            evicted_email, _ = self.customers.popitem(last=False)
            if evicted_email in self.access_times:
                del self.access_times[evicted_email]

    def to_dict(self):
        return {
            "customer_id": self.customer_id,
            "history": self.history,
            "preferences": self.preferences,
            "issues": self.issues,
            "customers": self.customers,
        }

    @classmethod
    def from_dict(cls, data):
        m = cls(customer_id=data.get("customer_id"))
        m.history = data.get("history", [])
        m.preferences = data.get("preferences", {})
        m.issues = data.get("issues", [])
        m.customers = data.get("customers", {})
        return m

    def __repr__(self):
        return f"<LongTermMemory {len(self.history)} notes>"
