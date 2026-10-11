"""Audit logging for compliance and debugging.

Every action is logged to an immutable JSONL file with:
  timestamp, user_id, action, resource_id, status, http_status, details

Entries are append-only (never modified or deleted).
Queryable by: user_id, date range, action type, status.
"""

from ami import STATE_DIR
import json
import time
from datetime import datetime
from pathlib import Path
from threading import Lock

from ami.log_rotation import rotate_log_if_needed, cleanup_old_logs

# Audit log location: stage1/state/audit.jsonl
LOG_DIR = STATE_DIR
LOG_FILE = LOG_DIR / "audit.jsonl"

_write_lock = Lock()

# Rotate logs hourly on startup
rotate_log_if_needed(LOG_FILE, rotation_interval_hours=1)
cleanup_old_logs(LOG_DIR, keep_days=30)


def ensure_log_file() -> None:
    """Ensure log directory and file exist."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if not LOG_FILE.exists():
        LOG_FILE.touch()


def log_action(
    user_id: str = None,
    action: str = None,
    resource_id: str = None,
    status: str = "success",
    http_status: int = 200,
    query_type: str = None,
    details: dict = None,
) -> None:
    """Log an action to the audit file.

    Args:
        user_id: User who performed the action (None for unauthenticated)
        action: Type of action (e.g., 'fetch_order', 'list_orders', 'chat', 'login')
        resource_id: Resource affected (e.g., order_123)
        status: 'success', 'denied', 'rate_limited', 'error', 'login_required', 'security_violation'
        http_status: HTTP response code
        query_type: 'PUBLIC' or 'PRIVATE' (classification tracking)
        details: Additional context (reason, ip, user_agent, duration_ms, model_cost_usd, message_preview)
    """
    ensure_log_file()

    now = datetime.utcnow()
    entry = {
        "timestamp": now.isoformat() + "Z",
        "user_id": user_id,
        "action": action,
        "resource_id": resource_id,
        "status": status,
        "http_status": http_status,
        "query_type": query_type,
        "details": details or {},
    }

    # Append to JSONL file (thread-safe)
    with _write_lock:
        try:
            with open(LOG_FILE, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except IOError as e:
            # Logging failed, but don't crash the request
            print(f"Warning: Failed to write audit log: {e}")


def log_request(
    user_id: str,
    action: str,
    resource_id: str = None,
    http_status: int = 200,
    ip: str = None,
    user_agent: str = None,
    duration_ms: float = None,
    model_cost_usd: float = None,
) -> None:
    """Log a request with standard details.

    Determines status from HTTP status code.

    Args:
        user_id: User who made the request
        action: Action type
        resource_id: Resource affected
        http_status: HTTP response code
        ip: Client IP
        user_agent: User-Agent header
        duration_ms: Request duration in milliseconds
        model_cost_usd: Cost of LLM calls
    """
    # Determine status from HTTP code
    if http_status == 200:
        status = "success"
    elif http_status in (401, 403, 404):
        status = "denied"
    elif http_status == 429:
        status = "rate_limited"
    else:
        status = "error"

    # Determine reason for denied
    reason = None
    if status == "denied":
        if http_status == 401:
            reason = "unauthorized"
        elif http_status == 403:
            reason = "forbidden"
        elif http_status == 404:
            reason = "not_found"

    details = {}
    if reason:
        details["reason"] = reason
    if ip:
        details["ip"] = ip
    if user_agent:
        details["user_agent"] = user_agent
    if duration_ms:
        details["duration_ms"] = duration_ms
    if model_cost_usd:
        details["model_cost_usd"] = model_cost_usd

    log_action(
        user_id=user_id,
        action=action,
        resource_id=resource_id,
        status=status,
        http_status=http_status,
        details=details,
    )


def query_audit_log(
    user_id: str = None,
    action: str = None,
    status: str = None,
    start_time: datetime = None,
    end_time: datetime = None,
) -> list:
    """Query audit log by various filters.

    Args:
        user_id: Filter by user (None = all users)
        action: Filter by action type
        status: Filter by status (success, denied, rate_limited, error)
        start_time: Filter by start timestamp
        end_time: Filter by end timestamp

    Returns:
        List of matching audit entries (dicts)
    """
    ensure_log_file()

    results = []
    try:
        with open(LOG_FILE, "r") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    if _matches_filters(entry, user_id, action, status, start_time, end_time):
                        results.append(entry)
                except json.JSONDecodeError:
                    # Skip malformed lines
                    pass
    except IOError as e:
        print(f"Warning: Failed to read audit log: {e}")

    return results


def _matches_filters(
    entry: dict,
    user_id: str = None,
    action: str = None,
    status: str = None,
    start_time: datetime = None,
    end_time: datetime = None,
) -> bool:
    """Check if entry matches all filters."""
    if user_id and entry.get("user_id") != user_id:
        return False
    if action and entry.get("action") != action:
        return False
    if status and entry.get("status") != status:
        return False

    if start_time or end_time:
        try:
            entry_time = datetime.fromisoformat(entry.get("timestamp", "").rstrip("Z"))
            if start_time and entry_time < start_time:
                return False
            if end_time and entry_time > end_time:
                return False
        except ValueError:
            return False

    return True


def clear_audit_log() -> None:
    """Clear all audit logs (careful! only for testing)."""
    with _write_lock:
        try:
            LOG_FILE.unlink()
            ensure_log_file()
        except Exception as e:
            print(f"Warning: Failed to clear audit log: {e}")
