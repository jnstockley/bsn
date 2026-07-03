import asyncio
import math
import os
from datetime import datetime

import pytz
from googleapiclient.discovery import Resource
from youtube_notify.rss.rss import get_content

from sqlalchemy import select
from sqlalchemy.orm import Session

from db import engine
from model import (
    YoutubeChannel,
    YoutubeContent,
    QuotaPolicy,
    Service,
    QuotaUsage,
)
from youtube_notify.models import Content
from util.logging import logger


GET_CONTENT_TIMEOUT_SECONDS: int = int(os.getenv("TIMEOUT", default=120))


def sync_subscriptions(youtube: Resource):
    logger.info("Syncing subscriptions")
    request = youtube.subscriptions().list(
        part="snippet,contentDetails",
        mine=True,
        maxResults=50,
    )

    response = __make_request(request)

    with Session(engine) as s:
        for c in response:
            channel_id = c["snippet"]["resourceId"]["channelId"]
            name = c["snippet"]["title"]
            number_of_videos = c["contentDetails"]["totalItemCount"]
            channel = YoutubeChannel(
                id=channel_id, name=name, num_videos=number_of_videos
            )
            s.merge(channel)
        s.commit()


async def get_recent_videos() -> set[Content]:
    with Session(engine) as s:
        stmt = select(YoutubeChannel)
        channels = s.execute(stmt).scalars().all()

    async def fetch_channel_content(channel_id: str):
        try:
            logger.info(f"Fetching recent videos for channel {channel_id}")
            return await asyncio.wait_for(
                get_content(channel_id), timeout=GET_CONTENT_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            logger.warning(
                f"Timed out fetching recent videos for channel {channel_id} after {GET_CONTENT_TIMEOUT_SECONDS} seconds"
            )
        except Exception as exc:
            logger.exception(
                f"Failed to fetch recent videos for channel {channel_id}: {exc}"
            )
        return set()

    tasks = [
        asyncio.create_task(fetch_channel_content(channel.id)) for channel in channels
    ]
    contents = await asyncio.gather(*tasks, return_exceptions=False)
    content = set().union(*contents) if contents else set()
    load_content(content)

    return content


def load_content(contents: set[Content]):
    logger.debug("Start loading contents")
    if not contents:
        logger.warning("No contents to load")
        return

    with Session(engine) as s:
        table_is_empty = s.execute(select(YoutubeContent.id)).first() is None
        logger.debug(f"Table is empty: {table_is_empty}")

        for content in contents:
            existing_content = s.get(YoutubeContent, content.id)
            if existing_content:
                logger.debug(f"Found existing YouTube content {existing_content}")
                continue

            youtube_content = YoutubeContent(
                id=content.id,
                title=content.title,
                published_at=content.published_at,
                thumbnail_url=str(content.thumbnail_url),
                description=content.description,
                content_type=content.content_type,
                youtube_channel_id=content.channel.id,
                notified=table_is_empty,
            )
            logger.debug(f"Found new YouTube content {youtube_content}")
            s.add(youtube_content)

        logger.debug("Starting commit...")
        s.commit()
        logger.debug("Finished commit")


def __make_request(request, units_used: int = 1) -> dict:
    logger.debug(f"Making request {request.uri}")

    root_uri = request.uri

    response = request.execute()
    __increment_quota_usage(units_used)
    response_body = response["items"]

    while response["nextPageToken"] if "nextPageToken" in response else None:
        next_page_token = response["nextPageToken"]

        request.uri = root_uri + f"&pageToken={next_page_token}"

        logger.debug(f"Making request {request.uri}")
        response = request.execute()
        __increment_quota_usage(units_used)
        response_body.extend(response["items"])

    return response_body


def __increment_quota_usage(units_used: int):
    with Session(engine) as s:
        stmt = select(QuotaPolicy).where(QuotaPolicy.service == Service.YOUTUBE)
        policy: QuotaPolicy | None = s.execute(stmt).scalar_one_or_none()
        if not policy:
            logger.warning(
                "Quota policy for YouTube not found when incrementing usage. Call initialize_policy() first."
            )
            raise RuntimeError(
                "Quota policy for YouTube not found. Call initialize_policy() first."
            )

        timezone = (
            "America/Los_Angeles"  # YouTube API quota resets at midnight Pacific Time
        )
        now = datetime.now(pytz.timezone(timezone))

        stmt = select(QuotaUsage).where(
            QuotaUsage.window_start <= now,
            QuotaUsage.window_end >= now,
            QuotaUsage.config_id == policy.id,
        )
        usage: QuotaUsage | None = s.execute(stmt).scalar_one_or_none()
        if not usage:
            logger.warning(
                "Quota usage for YouTube not found when incrementing usage. Call initialize_usage() first."
            )
            raise RuntimeError(
                "Quota usage for YouTube not found. Call initialize_usage() first."
            )

        if usage.quota_remaining < units_used:
            logger.warning(
                "Attempted to use more quota than remaining for YouTube API. This should have been prevented by __check_available_quota()."
            )
            raise RuntimeError(
                "Attempted to use more quota than remaining for YouTube API."
            )

        usage.usage_count += units_used
        usage.quota_remaining -= units_used
        s.flush()
        s.commit()
        s.refresh(usage)


def __check_available_quota() -> bool:
    with Session(engine) as s:
        stmt = select(QuotaPolicy).where(QuotaPolicy.service == Service.YOUTUBE)
        policy: QuotaPolicy | None = s.execute(stmt).scalar_one_or_none()
        if not policy:
            logger.warning(
                "Quota policy for YouTube not found when checking quota. Call initialize_policy() first."
            )
            raise RuntimeError(
                "Quota policy for YouTube not found. Call initialize_policy() first."
            )

        timezone = (
            "America/Los_Angeles"  # YouTube API quota resets at midnight Pacific Time
        )
        now = datetime.now(pytz.timezone(timezone))

        stmt = select(QuotaUsage).where(
            QuotaUsage.window_start <= now,
            QuotaUsage.window_end >= now,
            QuotaUsage.config_id == policy.id,
        )
        usage: QuotaUsage | None = s.execute(stmt).scalar_one_or_none()
        if not usage:
            logger.warning(
                "Quota usage for YouTube not found when checking quota. Call initialize_usage() first."
            )
            raise RuntimeError(
                "Quota usage for YouTube not found. Call initialize_usage() first."
            )

        if usage.quota_remaining <= 0:
            logger.warning(
                "Quota for YouTube API has been exhausted for the current window."
            )
            return False
    return True


def calculate_interval_between_cycles():
    with Session(engine) as s:
        num_channels: int = (
            len(s.execute(select(YoutubeChannel)).scalars().all()) + 1
        )  # Add 1 to account for the healthcheck request that also uses the YouTube API

    total_requests_allowed_per_day = 10_000
    requests_per_cycle = math.ceil((num_channels + 1) / 50)

    # Calculate the number of cycles we can perform in a day
    num_cycles_per_day = total_requests_allowed_per_day // requests_per_cycle

    # Total seconds in a day
    seconds_per_day = 24 * 60 * 60

    # Calculate the interval between each cycle
    interval_between_cycles = seconds_per_day / num_cycles_per_day

    return math.ceil(interval_between_cycles)


def _chunk_list(lst: list[str], chunk_size: int = 50) -> str:
    for i in range(0, len(lst), chunk_size):
        yield ",".join(lst[i : i + chunk_size])
