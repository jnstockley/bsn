import asyncio
import math
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

import aiohttp
import pytz
from googleapiclient.discovery import Resource
from googleapiclient.errors import HttpError

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from db import engine
from models import YoutubeChannel, YoutubeVideo, QuotaPolicy, Service, QuotaUsage
from util.logging import logger


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

    remaining_channels = [
        channel for channel in channels if channel not in recently_uploaded_channels
    ]
    recently_uploaded_channels += check_rss_for_new_videos(remaining_channels)

    return channels, recently_uploaded_channels


def get_recent_videos(
    channels: list[YoutubeChannel], youtube: Resource
) -> list[YoutubeVideo]:
    if not __check_available_quota():
        logger.warning(
            "Quota for YouTube API has been exhausted. Skipping recent video check."
        )
        return []

    playlist_ids = [f"UU{channel.id[2:]}" for channel in channels]

    videos = []

    for playlist_id in playlist_ids:
        channel_id = f"UC{playlist_id[2:]}"
        request = youtube.playlistItems().list(
            part="snippet,status,contentDetails",
            playlistId=playlist_id,
            maxResults=1,
        )

        logger.debug(f"Making request {request.uri}")

        response = request.execute()
        __increment_quota_usage(1)

        body: dict = response["items"][0]

        # Update Channel Name, reference #293
        channel_name = body["snippet"]["channelTitle"]
        with Session(engine) as s:
            stmt = select(YoutubeChannel).where(YoutubeChannel.id == channel_id)
            channel: YoutubeChannel | None = s.execute(stmt).scalar_one_or_none()
            if channel:
                channel.name = channel_name
                s.commit()
                s.refresh(channel)

        if body["status"]["privacyStatus"] != "public":
            logger.info(
                f"Skipping video {body['snippet']['title']} from channel {channel_id} because it is not public"
            )
            continue

        # Parse ISO 8601 UTC timestamp and convert to local timezone
        utc_time = datetime.strptime(
            body["contentDetails"]["videoPublishedAt"], "%Y-%m-%dT%H:%M:%SZ"
        )
        utc_time = utc_time.replace(tzinfo=timezone.utc)
        local_time = utc_time.astimezone()

        is_live: bool = __is_live(body, youtube)

        video = YoutubeVideo(
            id=body["contentDetails"]["videoId"],
            title=body["snippet"]["title"],
            url=f"https://www.youtube.com/watch?v={body['contentDetails']['videoId']}",
            thumbnail_url=body["snippet"]["thumbnails"]["high"]["url"],
            is_short=__is_short(body, youtube),
            is_livestream=is_live,
            uploaded_at=datetime.now(tz=timezone.utc).astimezone() if is_live else local_time,
            youtube_channel_id=channel_id,
        )

        with Session(engine) as s:
            stmt = select(YoutubeVideo).where(YoutubeVideo.id == video.id)
            existing_video = s.execute(stmt).scalar_one_or_none()

            if existing_video:
                logger.warning(
                    f"Skipping video {video.title} from channel {existing_video.youtube_channel.name} because it already exists in the database"
                )
                continue

            stmt = delete(YoutubeVideo).where(
                YoutubeVideo.youtube_channel_id == channel_id
            )

            s.execute(stmt)
            s.add(video)
            s.commit()
            s.refresh(video)
            # Eager load the youtube_channel relationship to prevent DetachedInstanceError
            _ = video.youtube_channel
            s.expunge(video)
            logger.debug(
                f"Added video to database and detached from session: {video.title} from channel {video.youtube_channel.name}"
            )

        # Skip check since livestream published/updated times are inconsistent
        if not is_live:
            interval_between_cycles = (
                calculate_interval_between_cycles() * 3
            )  # Multiply by 3 to add some buffer time in case the check runs a bit later than scheduled
            now = datetime.now().astimezone()
            if (now - local_time).total_seconds() > interval_between_cycles:
                logger.warning(
                    f"Skipping video {body['snippet']['title']} from channel {channel_id} because it was uploaded more than {interval_between_cycles} seconds ago"
                )
                continue

        logger.info(f"Found new video: {video}")

        videos.append(video)

    return videos


async def _fetch_rss_feed(
    session: aiohttp.ClientSession, channel: YoutubeChannel
) -> tuple[YoutubeChannel, bytes | None]:
    """Fetch the RSS feed for a single channel asynchronously.

    Returns ``(channel, content)`` on success or ``(channel, None)`` on error.
    """
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel.id}"
    try:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return channel, await resp.read()
    except Exception as e:
        logger.warning(f"Error fetching RSS feed for channel {channel.name}: {e}")
        return channel, None


async def _fetch_all_rss_feeds(
    channels: list[YoutubeChannel],
) -> list[tuple[YoutubeChannel, bytes | None]]:
    """Concurrently fetch RSS feeds for all given channels."""
    async with aiohttp.ClientSession() as session:
        tasks = [_fetch_rss_feed(session, channel) for channel in channels]
        return await asyncio.gather(*tasks)


def check_rss_for_new_videos(
    channels: list[YoutubeChannel],
) -> list[YoutubeChannel]:
    """Check YouTube RSS feeds for channels not already detected as having new videos.

    Note: YouTube RSS feeds are per-channel — each feed URL covers exactly one channel
    and returns up to 15 of the most recent videos. All feeds are fetched concurrently.

    Returns a list of channels where their most recent video:
    - is NOT already present in our DB, AND
    - was published within 3 check cycles (recent enough to warrant a notification).
    """
    _ATOM_NS = "http://www.w3.org/2005/Atom"
    _YT_NS = "http://www.youtube.com/xml/schemas/2015"

    if not channels:
        return []

    interval_between_cycles = calculate_interval_between_cycles() * 3
    now = datetime.now().astimezone()

    # Fetch all RSS feeds concurrently
    feed_results: list[tuple[YoutubeChannel, bytes | None]] = asyncio.run(
        _fetch_all_rss_feeds(channels)
    )

    channels_with_new_videos: list[YoutubeChannel] = []

    for channel, feed_content in feed_results:
        if feed_content is None:
            continue

        root = ET.fromstring(feed_content)
        entries = root.findall(f"{{{_ATOM_NS}}}entry")

        if not entries:
            logger.debug(f"No entries found in RSS feed for channel {channel.name}")
            continue

        # The first entry is the most recently published video
        entry = entries[0]

        video_id_el = entry.find(f"{{{_YT_NS}}}videoId")

        if (
            video_id_el is None
            or not video_id_el.text
        ):
            logger.warning(f"Could not parse RSS entry for channel {channel.name}")
            continue

        video_id = video_id_el.text

        # Skip if the video is already in our DB
        with Session(engine) as s:
            stmt = select(YoutubeVideo).where(YoutubeVideo.id == video_id)
            existing_video = s.execute(stmt).scalar_one_or_none()

        if existing_video:
            logger.debug(
                f"Most recent video from channel {channel.name} is already in DB, skipping"
            )
            continue

        logger.info(
            f"Channel {channel.name} has a new video not yet in DB (detected via RSS)"
        )
        channels_with_new_videos.append(channel)

    return channels_with_new_videos


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
                    name=c["snippet"]["title"],
                    num_videos=int(c["contentDetails"]["totalItemCount"]),
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


def __is_short(body: dict, youtube: Resource) -> bool:
    shorts_playlist_id: str = body["snippet"]["channelId"].replace("UC", "UUSH")
    short_id: str = body["contentDetails"]["videoId"]

    request = youtube.playlistItems().list(
        part="snippet,status,contentDetails",
        playlistId=shorts_playlist_id,
        videoId=short_id,
        maxResults=1,
    )

    logger.debug(f"Making request {request.uri}")
    try:
        response = request.execute()
    except HttpError as err:
        logger.warning(f"Error checking if video {short_id} is a short: {err}")
        return False
    __increment_quota_usage(1)
    return response["pageInfo"]["totalResults"] > 0


def __is_live(body: dict, youtube: Resource) -> bool:
    livestream_id: str = body["contentDetails"]["videoId"]

    request = youtube.videos().list(
        part="snippet,liveStreamingDetails",
        id=livestream_id,
    )

    logger.debug(f"Making request {request.uri}")
    response = request.execute()
    __increment_quota_usage(1)

    body = response["items"][0]

    if "liveBroadcastContent" in body["snippet"]:
        return body["snippet"]["liveBroadcastContent"] == "live"
    return False


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
