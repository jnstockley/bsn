import asyncio
import math
from datetime import datetime
from urllib.parse import urlparse, parse_qs

import aiohttp
import pytz
from feedparser import FeedParserDict
from googleapiclient.discovery import Resource

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from db import engine
from models import YoutubeChannel, QuotaPolicy, Service, QuotaUsage, YoutubeContent, YoutubeContentType
from rss import rss
from util.logging import logger
from util.version import get_version

def pull_subscriptions(youtube: Resource):
    pass

async def fetch_all_recent_content() -> list[YoutubeContent]:
    with Session(engine) as s:
        channels: list[YoutubeChannel] = s.execute(select(YoutubeChannel)).scalars().all()

    version = get_version()
    async with aiohttp.ClientSession(headers={"User-Agent": f"bsn/{version}"}) as session:
        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(get_recent_content(channel, session)) for channel in channels]

    results: list[YoutubeContent] = []
    for task in tasks:
        results.extend(task.result())

    return results

async def get_recent_content(channel: YoutubeChannel, session: aiohttp.ClientSession) -> list[YoutubeContent]:
    video_playlist_id = f"UULF{channel.id[2:]}"
    livestream_playlist_id = f"UULV{channel.id[2:]}"
    short_playlist_id = f"UUSH{channel.id[2:]}"

    async with asyncio.TaskGroup() as tg:
        video_feed_promise = tg.create_task(rss.get_youtube_feed(video_playlist_id, session))
        livestream_feed_promise = tg.create_task(rss.get_youtube_feed(livestream_playlist_id, session))
        short_feed_promise = tg.create_task(rss.get_youtube_feed(short_playlist_id, session))

    videos: list[YoutubeContent] = __process(video_feed_promise.result())
    livestreams: list[YoutubeContent] = __process(livestream_feed_promise.result())
    shorts: list[YoutubeContent] = __process(short_feed_promise.result())

    return videos + livestreams + shorts

def __process(feed: FeedParserDict) -> list[YoutubeContent]:
    if not feed or "entries" not in feed or len(feed.entries) == 0:
        return []

    entries = feed["entries"]

    content: list[YoutubeContent] = []

    for entry in entries:
        video_id = entry['yt_videoid']
        channel_id = entry['yt_channelid']
        title = entry['title']
        uploaded_at = entry['published']
        url = entry['link']
        thumbnail_url = entry['media_thumbnail'][0]['url']
        content_type = __get_content_type(entry['summary_detail']['base'])
        if content_type:
            content.append(YoutubeContent(
                id=video_id,
                title=title,
                uploaded_at=uploaded_at,
                url=url,
                thumbnail_url=thumbnail_url,
                type=content_type,
                youtube_channel_id=channel_id,
            ))

    return content

def __get_content_type(playlist_url: str) -> YoutubeContentType | None:
    parsed_url = urlparse(playlist_url)
    params = parse_qs(parsed_url.query)
    if "playlist_id" in params:
        playlist_id = params["playlist_id"][0]
        if playlist_id.startswith("UULF"):
            return YoutubeContentType.VIDEO
        elif playlist_id.startswith("UULV"):
            return YoutubeContentType.LIVESTREAM
        elif playlist_id.startswith("UUSH"):
            return YoutubeContentType.SHORT
    return None


def pull_my_subscriptions(youtube: Resource):
    if not __check_available_quota():
        logger.warning(
            "Quota for YouTube API has been exhausted. Skipping subscription check."
        )
        return None, None

    request = youtube.subscriptions().list(
        part="snippet,contentDetails",
        mine=True,
        maxResults=50,
    )

    response = __make_request(request)

    channels, recently_uploaded_channels = __youtube_subs_response_to_channels(response)

    return channels, recently_uploaded_channels


def __youtube_subs_response_to_channels(
    response: dict,
) -> tuple[list[YoutubeChannel], list[YoutubeChannel]]:
    all_channels: list[YoutubeChannel] = []
    recently_uploaded_channels: list[YoutubeChannel] = []

    for c in response:
        with Session(engine) as s:
            channel_id = c["snippet"]["resourceId"]["channelId"]

            stmt = select(YoutubeChannel).where(YoutubeChannel.id == channel_id)

            channel: YoutubeChannel = s.execute(stmt).scalar_one_or_none()

            if not channel:  # New channel, add to db
                channel = YoutubeChannel(
                    id=channel_id,
                    name=c["snippet"]["title"]
                )
                s.add(channel)
                s.commit()
                s.refresh(channel)
            else:
                current_num_videos = int(c["contentDetails"]["totalItemCount"])

                if current_num_videos == channel.num_videos + 1:
                    logger.info(f"Channel {channel.name} has new video(s)")
                    recently_uploaded_channels.append(channel)
                elif current_num_videos > channel.num_videos + 1:
                    logger.warning(
                        f"More than 1 video uploaded since last check, skipping notification for channel {channel.name}"
                    )

                channel.num_videos = current_num_videos
                s.flush()
                s.commit()
                s.refresh(channel)

            all_channels.append(channel)

    current_channel_ids = {c["snippet"]["resourceId"]["channelId"] for c in response}
    with Session(engine) as s:
        stmt = delete(YoutubeChannel).where(
            YoutubeChannel.id.not_in(current_channel_ids)
        )
        s.execute(stmt)
        s.commit()

    return all_channels, recently_uploaded_channels


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
