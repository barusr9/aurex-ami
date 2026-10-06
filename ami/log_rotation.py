"""Log rotation utility for JSONL files.

Rotates logs hourly, compressing old files and preventing unbounded growth.
Used by observe.py (trace logs) and audit.py (audit logs).
"""

import gzip
import os
from datetime import datetime
from pathlib import Path


def rotate_log_if_needed(log_file: Path, rotation_interval_hours: int = 1):
    """Rotate JSONL log file if it has reached the rotation interval.

    Args:
        log_file: Path to .jsonl log file
        rotation_interval_hours: Rotate after this many hours (default 1 hour)

    Rotates by:
    1. Renaming current log to .YYYYMMDD-HHMM format
    2. Gzipping the old file
    3. Creating a new log file for current writes

    Returns:
        True if rotation occurred, False otherwise
    """
    if not log_file.exists():
        return False

    # Check file age
    stat = log_file.stat()
    file_age_seconds = (datetime.now().timestamp() - stat.st_mtime)
    file_age_hours = file_age_seconds / 3600

    if file_age_hours < rotation_interval_hours:
        return False

    try:
        # Generate rotation timestamp: YYYYMMDD-HHMM
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d-%H%M")
        rotated_name = f"{log_file.stem}.{timestamp}.jsonl"
        rotated_path = log_file.parent / rotated_name

        # Rename current log
        log_file.rename(rotated_path)

        # Gzip the rotated file in background (free up space immediately)
        gzip_path = Path(str(rotated_path) + ".gz")
        with open(rotated_path, "rb") as f_in:
            with gzip.open(gzip_path, "wb") as f_out:
                f_out.write(f_in.read())

        # Delete the original after gzip succeeds
        rotated_path.unlink()

        return True
    except (OSError, IOError):
        return False


def cleanup_old_logs(log_dir: Path, keep_days: int = 7):
    """Clean up compressed log files older than keep_days.

    Args:
        log_dir: Directory containing log files
        keep_days: Keep logs from the last N days
    """
    try:
        now = datetime.now().timestamp()
        cutoff_seconds = keep_days * 86400

        for gz_file in log_dir.glob("*.jsonl.*.gz"):
            if (now - gz_file.stat().st_mtime) > cutoff_seconds:
                try:
                    gz_file.unlink()
                except OSError:
                    pass
    except (OSError, IOError):
        pass
