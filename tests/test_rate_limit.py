"""Tests for rate limiting module (ami/rate_limit.py)."""

import pytest
import time
from ami.rate_limit import (
    TokenBucket,
    RateLimiter,
    check_and_consume,
    get_rate_limit_status,
    reset_rate_limit,
)


class TestTokenBucket:
    """Test token bucket algorithm."""

    def test_bucket_starts_full(self):
        """New bucket starts with full capacity."""
        bucket = TokenBucket("user_123")
        assert bucket.tokens == 60

    def test_bucket_consume_success(self):
        """Can consume token when available."""
        bucket = TokenBucket("user_123")
        assert bucket.try_consume() is True
        assert bucket.tokens == 59

    def test_bucket_consume_multiple(self):
        """Can consume multiple tokens."""
        bucket = TokenBucket("user_123")
        assert bucket.try_consume(10) is True
        assert bucket.tokens == 50

    def test_bucket_consume_fails_when_empty(self):
        """Cannot consume when empty."""
        bucket = TokenBucket("user_123")
        bucket.tokens = 0
        bucket.last_refill_time = time.time() + 1  # Set to future, so no refill happens
        assert bucket.try_consume() is False
        # Tokens won't refill since last_refill_time is in the future
        assert bucket.tokens < 1

    def test_bucket_consume_partial_fails(self):
        """Cannot consume more than available."""
        bucket = TokenBucket("user_123")
        bucket.tokens = 5
        bucket.last_refill_time = time.time() + 1  # Set to future to prevent refill
        assert bucket.try_consume(10) is False
        # After refill, tokens might be slightly different due to time, so just check < 10
        assert bucket.tokens < 10

    def test_bucket_refill(self):
        """Tokens refill over time."""
        bucket = TokenBucket("user_123")
        bucket.tokens = 0
        bucket.last_refill_time = time.time() - 10  # 10 seconds ago

        bucket.refill()
        # Should have ~10 tokens (1 per second)
        assert bucket.tokens >= 9
        assert bucket.tokens <= 11


class TestRateLimiter:
    """Test rate limiter for multiple users."""

    def test_limiter_separate_buckets(self):
        """Different users have separate buckets."""
        limiter = RateLimiter()
        assert limiter.check_and_consume("user_1") is True
        assert limiter.check_and_consume("user_2") is True
        # Each user has 59 tokens left
        assert limiter.get_tokens_remaining("user_1") == 59
        assert limiter.get_tokens_remaining("user_2") == 59

    def test_limiter_exhausts_bucket(self):
        """Bucket exhaustion after 60 requests."""
        limiter = RateLimiter()
        for i in range(60):
            assert limiter.check_and_consume("user_1") is True

        # 61st request fails
        assert limiter.check_and_consume("user_1") is False

    def test_limiter_reset_user(self):
        """Can reset one user's limit."""
        limiter = RateLimiter()
        limiter.check_and_consume("user_1")
        assert limiter.get_tokens_remaining("user_1") == 59

        limiter.reset_user("user_1")
        assert limiter.get_tokens_remaining("user_1") == 60

    def test_limiter_reset_all(self):
        """Can reset all limits."""
        limiter = RateLimiter()
        limiter.check_and_consume("user_1")
        limiter.check_and_consume("user_2")
        assert limiter.get_tokens_remaining("user_1") == 59
        assert limiter.get_tokens_remaining("user_2") == 59

        limiter.reset_all()
        assert limiter.get_tokens_remaining("user_1") == 60
        assert limiter.get_tokens_remaining("user_2") == 60

    def test_limiter_status(self):
        """Status includes all relevant fields."""
        limiter = RateLimiter()
        limiter.check_and_consume("user_1")
        status = limiter.get_status("user_1")

        assert status["user_id"] == "user_1"
        assert status["tokens_remaining"] == 59
        assert status["limit"] == 60
        assert status["window_seconds"] == 60

    def test_limiter_invalid_user(self):
        """Empty user_id raises error."""
        limiter = RateLimiter()
        with pytest.raises(ValueError):
            limiter.check_and_consume("")

    def test_limiter_thread_safety(self):
        """Limiter is thread-safe (basic check)."""
        import threading

        limiter = RateLimiter()
        limiter.reset_all()
        results = []

        def consume_tokens():
            for _ in range(30):
                result = limiter.check_and_consume("user_1")
                results.append(result)

        # Run in 3 threads
        threads = [threading.Thread(target=consume_tokens) for _ in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Should have exactly 60 True, rest False
        assert results.count(True) == 60
        assert results.count(False) == 30


class TestGlobalRateLimiter:
    """Test module-level rate limiter functions."""

    def test_check_and_consume(self):
        """Global check_and_consume works."""
        reset_rate_limit()
        assert check_and_consume("user_1") is True
        assert check_and_consume("user_1") is True

    def test_get_status(self):
        """Global get_status works."""
        reset_rate_limit()
        check_and_consume("user_1")
        status = get_rate_limit_status("user_1")
        assert status["tokens_remaining"] == 59

    def test_reset(self):
        """Global reset works."""
        reset_rate_limit()
        check_and_consume("user_1")
        reset_rate_limit("user_1")
        assert get_rate_limit_status("user_1")["tokens_remaining"] == 60


class TestRateLimitRefill:
    """Test refill behavior with time delays."""

    def test_refill_one_second(self):
        """One second adds one token."""
        bucket = TokenBucket("user_1")
        bucket.tokens = 0
        bucket.last_refill_time = time.time() - 1.0

        bucket.refill()
        assert bucket.tokens >= 0.9  # Allow small precision loss

    def test_refill_capped_at_max(self):
        """Tokens don't exceed max capacity."""
        bucket = TokenBucket("user_1")
        bucket.tokens = 50
        bucket.last_refill_time = time.time() - 60  # 60 seconds ago

        bucket.refill()
        # Should cap at 60, not 110
        assert bucket.tokens == 60

    def test_sliding_window(self):
        """Sliding window behavior."""
        bucket = TokenBucket("user_1")
        bucket.tokens = 0
        bucket.last_refill_time = time.time() - 2.0  # 2 seconds ago

        bucket.refill()
        assert bucket.tokens >= 1.9  # ~2 tokens

        # Consume 2 tokens
        assert bucket.try_consume(2) is True

        # Move forward 1 second
        bucket.last_refill_time = time.time() - 1.0
        bucket.refill()
        assert bucket.tokens >= 0.8  # ~1 new token
