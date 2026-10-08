"""Centralized configuration for Stage 3 agent.

All hardcoded values (ports, timeouts, limits) live here and can be
overridden via environment variables for different deployment environments.
"""

import os
from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv

# Load .env BEFORE the Config fields read os.getenv. llm.py used to load it
# later, so every value set only in .env (MODEL, LLM_*, ALERT_*) was ignored
# here and the defaults won — e.g. runs reported MODEL as gpt-4o-mini.
load_dotenv()


@dataclass(frozen=True)
class Config:
    """Immutable configuration object."""

    # Server
    PORT: int = int(os.getenv("PORT", "9001"))
    HOST: str = os.getenv("HOST", "127.0.0.1")

    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-only-for-local-dev")

    # Authentication
    TOKEN_EXPIRY_MINUTES: int = int(os.getenv("TOKEN_EXPIRY_MINUTES", "15"))

    # Sessions
    SESSION_TIMEOUT_HOURS: int = int(os.getenv("SESSION_TIMEOUT_HOURS", "24"))
    SESSION_SAVE_INTERVAL_SECONDS: int = int(os.getenv("SESSION_SAVE_INTERVAL_SECONDS", "5"))

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "60"))

    # Model — the knobs that drive cost (S1) and routing (S6). MODEL lived in
    # llm.py and MAX_STEPS in agent.py/planner.py, bypassing this file; they
    # are centralized here so a deployment can tune them without a code edit.
    MODEL: str = os.getenv("MODEL", "gpt-4o-mini")
    MODEL_CHEAP: str = os.getenv("MODEL_CHEAP", "")       # S6: cheap tier for simple turns ("" = disabled)
    MODEL_STRONG: str = os.getenv("MODEL_STRONG", "")     # S6: strong tier for hard turns ("" = use MODEL)
    MAX_STEPS: int = int(os.getenv("MAX_STEPS", "6"))      # tool-loop ceiling in the ReAct planner
    # S1: when an authenticated customer's message names an order id, look
    # it up BEFORE the first model call instead of spending a whole round-trip
    # to have the model ask for it. Set PREFETCH_ORDERS=0 to reproduce the
    # pre-fix behaviour.
    PREFETCH_ORDERS: bool = os.getenv("PREFETCH_ORDERS", "1") not in ("0", "false", "False")
    LLM_RETRY_TRIES: int = int(os.getenv("LLM_RETRY_TRIES", "6"))   # 429 / 5xx backoff attempts
    LLM_RETRY_MAX_SECONDS: int = int(os.getenv("LLM_RETRY_MAX_SECONDS", "75"))  # total backoff per call
    LLM_GATEWAY_RETRY_SECONDS: int = int(os.getenv("LLM_GATEWAY_RETRY_SECONDS", "15"))  # 502/503/504 backoff
    LLM_TIMEOUT_SECONDS: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "60"))      # one request
    LLM_FORCE_IPV4: bool = os.getenv("LLM_FORCE_IPV4", "") == "1"                 # skip a black-holed IPv6 route

    # Degradation (S4) — a turn that runs longer than this degrades gracefully
    # instead of hanging. 0 disables the budget.
    TURN_BUDGET_SECONDS: int = int(os.getenv("TURN_BUDGET_SECONDS", "0"))

    # Monitoring (S2) — thresholds that, when crossed, raise an `alert` event.
    # 0 disables a given alert.
    # Shipped ARMED (S2 / readout §6). A monitor that defaults to off is a
    # demo, not production. These are the thresholds the readout commits to;
    # set one to 0 to silence it. Note p95 is deliberately above today's
    # measured value's neighbourhood but below the worst runs (15–18 s), so
    # it fires on a bad day — that is the point of setting it.
    ALERT_ERROR_RATE_PCT: int = int(os.getenv("ALERT_ERROR_RATE_PCT", "15"))
    ALERT_COST_PER_TURN_USD: float = float(os.getenv("ALERT_COST_PER_TURN_USD", "0.02"))
    ALERT_P95_MS: int = int(os.getenv("ALERT_P95_MS", "12000"))

    # Memory
    MAX_CONVERSATION_TURNS: int = int(os.getenv("MAX_CONVERSATION_TURNS", "40"))
    LONGTERM_MEMORY_CACHE_SIZE: int = int(os.getenv("LONGTERM_MEMORY_CACHE_SIZE", "5000"))
    LONGTERM_MEMORY_TTL_HOURS: int = int(os.getenv("LONGTERM_MEMORY_TTL_HOURS", "24"))

    # Planning
    MAX_PLANNER_STEPS: int = int(os.getenv("MAX_PLANNER_STEPS", "6"))
    MAX_PLAN_ROUNDS: int = int(os.getenv("MAX_PLAN_ROUNDS", "3"))

    # Observability
    MAX_TRACE_EVENTS: int = int(os.getenv("MAX_TRACE_EVENTS", "500"))
    TRACE_FLUSH_INTERVAL_SECONDS: int = int(os.getenv("TRACE_FLUSH_INTERVAL_SECONDS", "5"))

    # Storage
    DATA_DIR: Path = Path(os.getenv("DATA_DIR", ".")) / "state"
    CACHE_DIR: Path = Path(os.getenv("CACHE_DIR", ".")) / ".cache"

    def __post_init__(self):
        """Ensure required configs are set."""
        if self.SECRET_KEY == "dev-secret-key-only-for-local-dev":
            # OK for development only; production must set explicitly
            pass


# Global config instance
config = Config()
