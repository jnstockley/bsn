import math
import os
from datetime import datetime, timedelta

import pandas as pd

from googleapiclient.errors import HttpError

from auth.youtube import get_youtube_service
from models.models import YouTubeChannel
from notifications.notifications import send_youtube_channels_notifications

from src import logger


def import_subscriptions(yt_df: pd.DataFrame):
    channel_ids = yt_df["Channel Id"].tolist()
    channels = get_channels_by_id(channel_ids)

    for channel in channels:
        channel_id = channel["id"]
        if not YouTubeChannel.select().where(YouTubeChannel.id == channel_id).exists():
            logger.info(
                f"Importing channel {channel_id} with {channel['statistics']['videoCount']} videos"
            )
            YouTubeChannel.create(
                id=channel["id"],
                num_videos=int(channel["statistics"]["videoCount"]),
            )


def get_channels_by_id(channel_ids: list[str]) -> list[dict] | None:
    channels: list[dict] = []

    for channel_str in _chunk_list(channel_ids):
        youtube = get_youtube_service()

        request = youtube.channels().list(part="statistics,snippet", id=channel_str)

        try:
            logger.info(f"Making request {request.uri}")
            response = request.execute()
            if "items" not in response:
                logger.warning(f"No items found with channel_ids: {channel_str}")
                return None
            channels.extend(response["items"])
        except HttpError as e:
            logger.error(
                f"An HTTP error {e.resp.status} occurred: {e.content.decode()} with channel_ids: {channel_str}"
            )
            return None

    return channels


def get_channels_with_new_videos(
    previous_channels: list[YouTubeChannel], current_channels: list[dict]
) -> list[dict]:
    new_video_channels = []

    for channel in current_channels:
        previous_channel = next(
            (c for c in previous_channels if c.id == channel["id"]), None
        )
        if int(channel["statistics"]["videoCount"]) > previous_channel.num_videos:
            logger.info(f"Channel {channel['id']} has new videos")
            new_video_channels.append(channel)
        elif int(channel["statistics"]["videoCount"]) < previous_channel.num_videos:
            logger.info(f"Video removed for channel {channel['id']}, updating channel")
            YouTubeChannel.update(
                num_videos=int(channel["statistics"]["videoCount"])
            ).where(YouTubeChannel.id == channel["id"]).execute()

    return new_video_channels


def update_channels(channels: list[dict]):
    for channel in channels:
        logger.info(
            f"Updating channel {channel['id']} with {channel['statistics']['videoCount']} videos"
        )
        YouTubeChannel.update(
            num_videos=int(channel["statistics"]["videoCount"])
        ).where(YouTubeChannel.id == channel["id"]).execute()


def check_for_new_videos():
    channels = YouTubeChannel.select()
    current_channels = get_channels_by_id([channel.id for channel in channels])
    new_video_channels = get_channels_with_new_videos(channels, current_channels)
    update_channels(new_video_channels)

    video = None
    if len(new_video_channels) > 0:
        if len(new_video_channels) == 1:
            video = get_most_recent_video(new_video_channels[0]["id"])

        send_youtube_channels_notifications(new_video_channels, video)


def get_most_recent_video(channel_id: str) -> dict | None:
    youtube = get_youtube_service()

    playlist_id = f"UU{channel_id[2:]}"

    request = youtube.playlistItems().list(
        part="snippet,status", maxResults=1, playlistId=playlist_id
    )

    try:
        logger.info(f"Making request {request.uri}")
        response = request.execute()
        if "items" not in response:
            logger.warning(f"No items found with channel_id: {channel_id}")
            return None

        video = response["items"][0]
        published_at = datetime.strptime(
            video["snippet"]["publishedAt"], "%Y-%m-%dT%H:%M:%SZ"
        )

        if (
            video["status"]["privacyStatus"] == "public"
            and video["snippet"]["position"] == 0
            and published_at >= (datetime.now() - timedelta(minutes=2))
        ):
            return video

    except HttpError as e:
        logger.error(
            f"An HTTP error {e.resp.status} occurred: {e.content} with channel_id: {channel_id}"
        )
        return None


def calculate_interval_between_cycles():
    num_channels: int = len(YouTubeChannel.select())
    num_api_keys: int = len(os.environ["YOUTUBE_API_KEYS"].split(","))
    max_requests_per_key_per_day = 10000
    total_requests_allowed_per_day = num_api_keys * max_requests_per_key_per_day
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
