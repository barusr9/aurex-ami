"""Query classification: PUBLIC (generic) vs PRIVATE (account-specific)."""

import re
from functools import lru_cache

# Keywords that indicate PRIVATE (account-specific) queries
# These must be specific to individual accounts (not general policies)
# SECURITY: Keywords are ordered by specificity - more specific first to reduce false negatives
PRIVATE_KEYWORDS = {
    "order_specific": [
        "my order", "my orders", "order status", "order 1", "order #", "order?",  # specific order references
        "tracking", "track my", "track order", "order tracking",  # tracking queries
        "where is my", "where is the order", "where's my", "where's the order", "where is the orderer",  # location queries
        "delivery date of", "return date of", "delivery window", "eta",  # date queries about orders
        "carrier", "shipping status", "in transit",  # shipping details
    ],
    "account": [
        "account", "my account", "my purchases", "profile",  # account access
        "my email", "email address",  # personal info
    ],
    "action": [
        # Refund/Return actions (highest severity)
        "return my", "return order", "return the order", "return this",
        "i want to return", "can i return", "when can i return",
        "refund", "refund my",
        # Cancel actions
        "cancel my", "cancel order", "cancel the order",
        # Modify actions
        "modify my", "change my", "update my",
        # Quantity queries about personal orders
        "how many orders", "how many", "total orders",
    ],
}

# Asking for a human hand-off. Escalation creates a support ticket that carries
# the customer's identity and conversation, so it is account-specific by
# governance: guests are asked to log in first (see web.py, tools.escalate).
HANDOFF_KEYWORDS = [
    "human", "real person", "live person", "live agent", "a person",
    "speak to someone", "talk to someone", "speak with someone", "talk with someone",
    "representative", "escalate", "supervisor", "support agent", "customer service agent",
    # common typos seen in testing
    "humna", "huamn", "humen", "hooman", "real persn", "live agnet",
]


def is_handoff_request(message: str) -> bool:
    """True when the customer is asking to be handed to a person."""
    m = (message or "").lower()
    return any(k in m for k in HANDOFF_KEYWORDS)


# Keywords that indicate PUBLIC (generic) queries
PUBLIC_KEYWORDS = {
    "policy": ["policy", "return policy", "shipping policy", "refund policy", "warranty"],
    "general": ["what", "how do i", "do you", "can you", "information", "about", "support"],
    "help": ["help", "contact", "customer service", "reach", "payment methods", "shipping"],
}


@lru_cache(maxsize=500)
def classify_query(message: str) -> str:
    """Classify a query as PUBLIC or PRIVATE.

    Args:
        message: User query text

    Returns:
        "PUBLIC" for generic questions
        "PRIVATE" for account-specific questions

    SECURITY NOTE: Any query matching PRIVATE keywords is classified as PRIVATE
    to prevent unauthorized access to account-specific information.
    False positives (classifying PUBLIC as PRIVATE) are acceptable and safe.
    False negatives (classifying PRIVATE as PUBLIC) are SECURITY VULNERABILITIES.

    Caching: Last 500 unique queries are cached for performance (LRU eviction).
    """
    if not message:
        return "PUBLIC"

    message_lower = message.lower()

    # Check for PRIVATE indicators (account-specific)
    private_score = 0
    for category, keywords in PRIVATE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in message_lower:
                private_score += 1

    # Check for PUBLIC indicators (generic)
    public_score = 0
    for category, keywords in PUBLIC_KEYWORDS.items():
        for keyword in keywords:
            if keyword in message_lower:
                public_score += 1

    # CRITICAL SECURITY FIX: If ANY private keyword matches, classify as PRIVATE
    # Changed from >= 2 to >= 1 to prevent account-specific queries from leaking
    # The cost of false positives (blocking a PUBLIC query) is acceptable.
    # The cost of false negatives (allowing PRIVATE queries) is UNACCEPTABLE.
    if private_score >= 1:
        return "PRIVATE"

    # Default to PUBLIC (favor open access for generic questions)
    return "PUBLIC"


# The guest front-door gate (web.py) is NARROWER than classify_query. It only
# fires on unmistakable account references, so "when can I return a product?"
# reaches the agent and is answered from the policies. Anything subtler is
# caught where the data is: every account tool refuses without a logged-in
# scope and returns login_required (tools.py), which shows the Log In button.
# classify_query stays broad on purpose: routing and the shared answer cache
# use it, and there a false PRIVATE only costs a stronger model or a cache miss.
_ORDER_ID = re.compile(r"\b\d{3}-\d{7}-\d{7}\b")
_MY_ACCOUNT_THING = re.compile(
    r"\bmy (orders?|account|purchases?|packages?|deliver(?:y|ies)|shipments?|"
    r"tracking|refunds?|returns?|email|address|profile|payments?|cards?|"
    r"subscriptions?|order history)\b"
    # ...but "my return policy" / "my refund window" asks about the rules, not the account
    r"(?!\s+(?:polic(?:y|ies)|windows?|periods?|rules|terms|options|process)\b)")


def needs_login_upfront(message: str) -> bool:
    """True when a guest's message plainly needs their account: an order
    number, or "my order" / "my account" / "my refund" and the like.
    Whole-word matches only ("details" does not contain the word "eta")."""
    m = (message or "").lower()
    return bool(_ORDER_ID.search(m) or _MY_ACCOUNT_THING.search(m))


def requires_authentication(query_type: str) -> bool:
    """Check if query type requires authentication.

    Args:
        query_type: "PUBLIC" or "PRIVATE"

    Returns:
        True if authentication required, False otherwise
    """
    return query_type == "PRIVATE"


def get_login_prompt() -> str:
    """Get the prompt message for unauthenticated private queries."""
    return (
        "Please log in to access your account information. "
        "You can ask me about policies and general questions without logging in."
    )


def get_handoff_login_prompt() -> str:
    """What a guest sees when they ask for a human."""
    return (
        "I can connect you with a human agent once you're logged in. "
        "Support tickets include your account details and this conversation, "
        "so for confidentiality we only open them for signed-in customers. "
        "Please log in and ask again."
    )

