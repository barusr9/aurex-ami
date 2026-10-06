"""Rate limiting using token bucket algorithm.

Per-user rate limiting: 60 requests per minute per user.
Uses token bucket with sliding 60-second window.

Algorithm:
  - Bucket capacity: 60 tokens
  - Refill rate: 1 token/second (60 tokens/minute)
  - Sliding window: 60 seconds (not fixed minute boundary)
  - On each request: refill based on time elapsed, then consume 1 token

Storage: In-memory dict (reset on server restart, OK for MVP).
"""

import time
from threading import Lock

RATE_LIMIT_REQUESTS_PER_MINUTE = 60
RATE_LIMIT_WINDOW_SECONDS = 60
TOKENS_PER_SECOND = RATE_LIMIT_REQUESTS_PER_MINUTE / RATE_LIMIT_WINDOW_SECONDS


class RateLimitError(Exception):
    """Rate limit exceeded."""
    pass


class TokenBucket:
    """Token bucket for one user.

    Attributes:
        user_id: User this bucket belongs to
        tokens: Current number of tokens available
        last_refill_time: Unix timestamp of last refill
    """

    def __init__(self, user_id: str):
        self.user_id = user_id
        self.tokens = RATE_LIMIT_REQUESTS_PER_MINUTE  # Start full
        self.last_refill_time = time.time()

    def refill(self) -> None:
        """Add tokens based on time elapsed since last refill."""
        now = time.time()
        time_elapsed = now - self.last_refill_time

        # Add tokens: 1 token per second
        new_tokens = time_elapsed * TOKENS_PER_SECOND
        self.tokens = min(
            RATE_LIMIT_REQUESTS_PER_MINUTE,  # Cap at max
            self.tokens + new_tokens,
        )

        self.last_refill_time = now

    def try_consume(self, count: int = 1) -> bool:
        """Try to consume tokens. If available, consume and return True.

        Args:
            count: Number of tokens to consume (default 1)

        Returns:
            True if consumed, False if insufficient tokens
        """
        self.refill()

        if self.tokens >= count:
            self.tokens -= count
            return True
        return False

    def get_tokens_remaining(self) -> int:
        """Get current token count (after refill)."""
        self.refill()
        return int(self.tokens)


class RateLimiter:
    """Rate limiter for multiple users.

    Maintains a token bucket per user. Thread-safe.
    """

    def __init__(self):
        self.buckets = {}  # {user_id: TokenBucket}
        self.lock = Lock()

    def check_and_consume(self, user_id: str) -> bool:
        """Check if user is under rate limit. If yes, consume 1 token and return True.

        Args:
            user_id: User identifier

        Returns:
            True if request allowed, False if rate limited

        Raises:
            ValueError: If user_id is empty
        """
        if not user_id:
            raise ValueError("user_id cannot be empty")

        with self.lock:
            if user_id not in self.buckets:
                self.buckets[user_id] = TokenBucket(user_id)

            bucket = self.buckets[user_id]
            return bucket.try_consume()

    def get_tokens_remaining(self, user_id: str) -> int:
        """Get tokens remaining for a user (after refill).

        Args:
            user_id: User identifier

        Returns:
            Number of tokens remaining
        """
        with self.lock:
            if user_id not in self.buckets:
                self.buckets[user_id] = TokenBucket(user_id)
            return self.buckets[user_id].get_tokens_remaining()

    def reset_user(self, user_id: str) -> None:
        """Reset rate limit for a user (useful for testing).

        Args:
            user_id: User identifier
        """
        with self.lock:
            if user_id in self.buckets:
                del self.buckets[user_id]

    def reset_all(self) -> None:
        """Reset all rate limits (useful for testing and server restart)."""
        with self.lock:
            self.buckets.clear()

    def get_status(self, user_id: str) -> dict:
        """Get rate limit status for a user.

        Returns:
            {
              "user_id": "user_abc",
              "tokens_remaining": 45,
              "limit": 60,
              "window_seconds": 60,
              "requests_until_limit": 45
            }
        """
        with self.lock:
            if user_id not in self.buckets:
                self.buckets[user_id] = TokenBucket(user_id)

            bucket = self.buckets[user_id]
            bucket.refill()

            return {
                "user_id": user_id,
                "tokens_remaining": int(bucket.tokens),
                "limit": RATE_LIMIT_REQUESTS_PER_MINUTE,
                "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
                "requests_until_limit": int(bucket.tokens),
            }


# Global rate limiter instance
_rate_limiter = RateLimiter()


def check_and_consume(user_id: str) -> bool:
    """Check and consume 1 token for a user.

    Args:
        user_id: User identifier

    Returns:
        True if allowed, False if rate limited
    """
    return _rate_limiter.check_and_consume(user_id)


def get_rate_limit_status(user_id: str) -> dict:
    """Get rate limit status for a user."""
    return _rate_limiter.get_status(user_id)


def reset_rate_limit(user_id: str = None) -> None:
    """Reset rate limit for user or all users."""
    if user_id:
        _rate_limiter.reset_user(user_id)
    else:
        _rate_limiter.reset_all()
