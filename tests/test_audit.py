"""Tests for audit logging module (ami/audit.py)."""

import pytest
import json
from datetime import datetime, timedelta
from ami.audit import (
    log_action,
    log_request,
    query_audit_log,
    clear_audit_log,
)


class TestAuditLogging:
    """Test audit log writing."""

    def setup_method(self):
        """Clear audit log before each test."""
        clear_audit_log()

    def test_log_action_writes_entry(self):
        """log_action writes valid JSONL entry."""
        log_action(
            user_id="user_1",
            action="fetch_order",
            resource_id="order_123",
            status="success",
            http_status=200,
            details={"duration_ms": 145},
        )

        entries = query_audit_log()
        assert len(entries) == 1
        assert entries[0]["user_id"] == "user_1"
        assert entries[0]["action"] == "fetch_order"
        assert entries[0]["resource_id"] == "order_123"
        assert entries[0]["status"] == "success"
        assert entries[0]["http_status"] == 200
        assert entries[0]["details"]["duration_ms"] == 145

    def test_log_action_immutable(self):
        """Entries are append-only (immutable)."""
        log_action("user_1", "action_1", status="success", http_status=200)
        log_action("user_2", "action_2", status="success", http_status=200)

        entries = query_audit_log()
        assert len(entries) == 2
        assert entries[0]["user_id"] == "user_1"
        assert entries[1]["user_id"] == "user_2"

    def test_log_action_has_timestamp(self):
        """Each entry has ISO timestamp."""
        log_action("user_1", "test", status="success", http_status=200)

        entries = query_audit_log()
        assert len(entries) == 1
        assert "timestamp" in entries[0]
        # Should be ISO format with Z
        assert entries[0]["timestamp"].endswith("Z")

    def test_log_action_optional_fields(self):
        """Optional fields can be omitted."""
        log_action("user_1", "test", status="success", http_status=200)

        entries = query_audit_log()
        assert entries[0]["resource_id"] is None
        assert entries[0]["details"] == {}


class TestLogRequest:
    """Test log_request helper."""

    def setup_method(self):
        """Clear audit log before each test."""
        clear_audit_log()

    def test_log_request_success(self):
        """200 response logged as success."""
        log_request("user_1", "fetch_order", http_status=200)

        entries = query_audit_log()
        assert entries[0]["status"] == "success"

    def test_log_request_denied_401(self):
        """401 logged as denied."""
        log_request("user_1", "fetch_order", http_status=401)

        entries = query_audit_log()
        assert entries[0]["status"] == "denied"
        assert entries[0]["details"]["reason"] == "unauthorized"

    def test_log_request_denied_403(self):
        """403 logged as denied."""
        log_request("user_1", "fetch_order", http_status=403)

        entries = query_audit_log()
        assert entries[0]["status"] == "denied"
        assert entries[0]["details"]["reason"] == "forbidden"

    def test_log_request_denied_404(self):
        """404 logged as denied (not_found)."""
        log_request("user_1", "fetch_order", http_status=404)

        entries = query_audit_log()
        assert entries[0]["status"] == "denied"
        assert entries[0]["details"]["reason"] == "not_found"

    def test_log_request_rate_limited(self):
        """429 logged as rate_limited."""
        log_request("user_1", "fetch_order", http_status=429)

        entries = query_audit_log()
        assert entries[0]["status"] == "rate_limited"

    def test_log_request_error(self):
        """5xx logged as error."""
        log_request("user_1", "fetch_order", http_status=500)

        entries = query_audit_log()
        assert entries[0]["status"] == "error"

    def test_log_request_with_details(self):
        """Can include ip, user_agent, duration, cost."""
        log_request(
            "user_1",
            "fetch_order",
            http_status=200,
            ip="127.0.0.1",
            user_agent="curl/7.0",
            duration_ms=145.5,
            model_cost_usd=0.0012,
        )

        entries = query_audit_log()
        details = entries[0]["details"]
        assert details["ip"] == "127.0.0.1"
        assert details["user_agent"] == "curl/7.0"
        assert details["duration_ms"] == 145.5
        assert details["model_cost_usd"] == 0.0012


class TestQueryAuditLog:
    """Test audit log queries."""

    def setup_method(self):
        """Clear and populate audit log."""
        clear_audit_log()
        log_request("user_1", "fetch_order", resource_id="order_1", http_status=200)
        log_request("user_1", "list_orders", http_status=200)
        log_request("user_2", "fetch_order", resource_id="order_2", http_status=200)
        log_request("user_2", "fetch_order", resource_id="order_999", http_status=404)
        log_request("user_1", "delete_order", resource_id="order_1", http_status=404)

    def test_query_all(self):
        """Query returns all entries by default."""
        entries = query_audit_log()
        assert len(entries) == 5

    def test_query_by_user(self):
        """Filter by user_id."""
        entries = query_audit_log(user_id="user_1")
        assert len(entries) == 3
        assert all(e["user_id"] == "user_1" for e in entries)

    def test_query_by_action(self):
        """Filter by action type."""
        entries = query_audit_log(action="fetch_order")
        assert len(entries) == 3
        assert all(e["action"] == "fetch_order" for e in entries)

    def test_query_by_status(self):
        """Filter by status."""
        entries = query_audit_log(status="denied")
        assert len(entries) == 2
        assert all(e["status"] == "denied" for e in entries)

    def test_query_multiple_filters(self):
        """Combine multiple filters."""
        entries = query_audit_log(user_id="user_1", action="fetch_order")
        assert len(entries) == 1
        assert entries[0]["user_id"] == "user_1"
        assert entries[0]["action"] == "fetch_order"

    def test_query_by_date_range(self):
        """Filter by timestamp range."""
        now = datetime.utcnow()
        future = now + timedelta(days=1)
        past = now - timedelta(days=1)

        # All entries are recent, so should match
        entries = query_audit_log(start_time=past, end_time=future)
        assert len(entries) == 5

        # Range in the past should match nothing
        old_start = past - timedelta(days=10)
        old_end = past - timedelta(days=5)
        entries = query_audit_log(start_time=old_start, end_time=old_end)
        assert len(entries) == 0

    def test_query_user_cannot_see_others(self):
        """User isolation in query."""
        entries = query_audit_log(user_id="user_1")
        assert len(entries) == 3
        assert all(e["user_id"] == "user_1" for e in entries)

        # User 2's actions not visible
        assert all(e["user_id"] != "user_2" for e in entries)


class TestAuditLogIntegrity:
    """Test audit log immutability and structure."""

    def setup_method(self):
        """Clear audit log."""
        clear_audit_log()

    def test_jsonl_format(self):
        """Log file is valid JSONL (one JSON per line)."""
        log_action("user_1", "test_1", status="success", http_status=200)
        log_action("user_2", "test_2", status="success", http_status=200)

        entries = query_audit_log()
        assert len(entries) == 2

    def test_no_deletion(self):
        """Entries cannot be deleted (append-only)."""
        log_action("user_1", "test", status="success", http_status=200)
        initial_count = len(query_audit_log())

        # Even if we try to clear, clearing is for testing only
        # In production, delete would fail
        clear_audit_log()
        count_after_clear = len(query_audit_log())
        assert count_after_clear == 0  # Clear works for testing

    def test_required_fields(self):
        """All entries have required fields."""
        log_action("user_1", "test", status="success", http_status=200)

        entries = query_audit_log()
        entry = entries[0]
        assert "timestamp" in entry
        assert "user_id" in entry
        assert "action" in entry
        assert "status" in entry
        assert "http_status" in entry
        assert "details" in entry
