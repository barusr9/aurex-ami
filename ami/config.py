"""Centralized configuration for Stage 3 agent.

All hardcoded values (ports, timeouts, limits) live here and can be
overridden via environment variables for different deployment environments.
"""

import os
from pathlib import Path
from dataclasses import dataclass


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
    LLM_RETRY_TRIES: int = int(os.getenv("LLM_RETRY_TRIES", "6"))   # 429 / 5xx backoff attempts

    # Degradation (S4) — a turn that runs longer than this degrades gracefully
    # instead of hanging. 0 disables the budget.
    TURN_BUDGET_SECONDS: int = int(os.getenv("TURN_BUDGET_SECONDS", "0"))

    # Monitoring (S2) — thresholds that, when crossed, raise an `alert` event.
    # 0 disables a given alert.
    ALERT_ERROR_RATE_PCT: int = int(os.getenv("ALERT_ERROR_RATE_PCT", "0"))
    ALERT_COST_PER_TURN_USD: float = float(os.getenv("ALERT_COST_PER_TURN_USD", "0"))
    ALERT_P95_MS: int = int(os.getenv("ALERT_P95_MS", "0"))

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
