from datetime import datetime

import pytz
from sqlalchemy import select
from sqlalchemy.orm import Session

from db import engine
from models import QuotaPolicy, Service, QuotaUsage
from util.logging import logger


def initialize_policy() -> QuotaPolicy:
    with Session(engine) as s:
        stmt = select(QuotaPolicy).where(QuotaPolicy.service == Service.YOUTUBE)
        policy: QuotaPolicy | None = s.execute(stmt).scalar_one_or_none()
        if not policy:
            logger.debug("No quota policy found for YouTube, creating a new one...")

            policy = QuotaPolicy(
                service=Service.YOUTUBE,
                limit=10_000,  # Each API key has a quota of 10,000 units per day
            )

            s.add(policy)
            s.commit()
            s.refresh(policy)
        return policy


def initialize_usage() -> QuotaUsage:
    timezone = (
        "America/Los_Angeles"  # YouTube API quota resets at midnight Pacific Time
    )
    current_date = datetime.now(pytz.timezone(timezone))

    start_time = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = current_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    with Session(engine) as s:
        stmt = select(QuotaUsage).where(
            QuotaUsage.window_start == start_time, QuotaUsage.window_end == end_time
        )
        usage: QuotaUsage | None = s.execute(stmt).scalar_one_or_none()
        if usage:
            logger.debug("Quota usage for the current window already initialized.")
            return usage

        stmt = select(QuotaPolicy).where(QuotaPolicy.service == Service.YOUTUBE)
        policy: QuotaPolicy | None = s.execute(stmt).scalar_one_or_none()
        if not policy:
            logger.warning(
                "Quota policy for YouTube not found when initializing usage. Call initialize_policy() first."
            )
            raise RuntimeError(
                "Quota policy for YouTube not found. Call initialize_policy() first."
            )

        usage = QuotaUsage(
            config_id=policy.id,
            timestamp=datetime.now(pytz.utc),
            window_start=start_time,
            window_end=end_time,
            usage_count=0,
            quota_remaining=policy.limit,
            reset_at=end_time.astimezone(pytz.utc),  # Store reset_at in UTC
        )
        s.add(usage)
        s.commit()
        s.refresh(usage)

    return usage
