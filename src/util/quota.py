from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo


def next_daily_reset_utc(
    reset_hour: int = 0,
    reset_minute: int = 0,
    reset_timezone: str = "America/Los_Angeles",
    now_utc: Optional[datetime] = None,
) -> datetime:
    """Return the next daily reset time in UTC for the given local reset time.

    Args:
        reset_hour: hour (0-23) in the local timezone when reset occurs.
        reset_minute: minute (0-59) in the local timezone when reset occurs.
        reset_timezone: tz database name for the local timezone (e.g. 'America/Los_Angeles').
        now_utc: optional current time in UTC; if None, uses current UTC now().

    Returns:
        A timezone-aware datetime in UTC representing the next reset time.
    """
    if now_utc is None:
        now_utc = datetime.now(timezone.utc)

    local_tz = ZoneInfo(reset_timezone)
    now_local = now_utc.astimezone(local_tz)

    # Candidate reset at today's local date/time
    candidate_local = datetime(
        year=now_local.year,
        month=now_local.month,
        day=now_local.day,
        hour=reset_hour,
        minute=reset_minute,
        tzinfo=local_tz,
    )

    if candidate_local <= now_local:
        candidate_local = candidate_local + timedelta(days=1)

    return candidate_local.astimezone(timezone.utc)


def current_reset_window_utc(
    reset_hour: int = 0,
    reset_minute: int = 0,
    reset_timezone: str = "America/Los_Angeles",
    now_utc: Optional[datetime] = None,
) -> Tuple[datetime, datetime]:
    """Return the current window (window_start_utc, window_end_utc) for the daily reset.

    The window_end is the next reset UTC time; window_start is the previous reset UTC time.
    """
    next_reset = next_daily_reset_utc(reset_hour, reset_minute, reset_timezone, now_utc)
    prev_reset = next_reset - timedelta(days=1)
    return prev_reset, next_reset


# Convenience function that accepts a QuotaConfig-like object (duck-typed)
def next_reset_for_config_utc(config, now_utc: Optional[datetime] = None) -> datetime:
    """Compute next reset UTC for a config-like object with attributes reset_hour, reset_minute and reset_timezone."""
    return next_daily_reset_utc(
        reset_hour=getattr(config, "reset_hour", 0) or 0,
        reset_minute=getattr(config, "reset_minute", 0) or 0,
        reset_timezone=getattr(config, "reset_timezone", "America/Los_Angeles") or "America/Los_Angeles",
        now_utc=now_utc,
    )

