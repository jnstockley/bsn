import os
import string
import random
import pandas as pd

from googleapiclient.errors import HttpError

from auth.youtube import get_youtube_service
from models import database
from models.models import YouTubeChannel
from notifications.notifications import send_youtube_channels_notifications

from src import logger

def import_subscriptions(subscriptions_file: str):
    if os.path.exists(subscriptions_file):
        subscriptions: list[str] = pd.read_csv(subscriptions_file)['Channel Id'].tolist()
        channels = get_channels_by_id(subscriptions)
        for channel in channels:
            YouTubeChannel.create(id=channel['id'], num_videos=int(channel['statistics']['videoCount']))
    else:
        logger.error(f'File {subscriptions_file} not found')
        return

def get_channels_by_id(channel_ids: list[str]) -> list[dict] | None:
    channels: list[dict] = []

    for channel_str in _chunk_list(channel_ids):
        youtube = get_youtube_service()

        request = youtube.channels().list(
            part='statistics,snippet',
            id=channel_str
        )

        try:
            logger.info(f"Making request {request.uri}")
            response = request.execute()
            if 'items' not in response:
                logger.warning(f'No items found with channel_ids: {channel_str}')
                return None
            channels.extend(response['items'])
        except HttpError as e:
            logger.error(f'An HTTP error {e.resp.status} occurred: {e.content} with channel_ids: {channel_str}')
            return None

    return channels

def get_channels_with_new_videos(previous_channels: list[YouTubeChannel], current_channels: list[dict]) -> list[dict]:
    new_video_channels = []

    for channel in current_channels:
        previous_channel = next((c for c in previous_channels if c.id == channel['id']), None)
        if int(channel['statistics']['videoCount']) > previous_channel.num_videos:
            logger.info(f"Channel {channel['id']} has new videos")
            new_video_channels.append(channel)
        elif int(channel['statistics']['videoCount']) < previous_channel.num_videos:
            logger.info(f"Video removed for channel {channel['id']}, updating channel")
            YouTubeChannel.update(num_videos=int(channel['statistics']['videoCount'])).where(
                YouTubeChannel.id == channel['id']).execute()

    return new_video_channels

def update_channels(channels: list[dict]):
    for channel in channels:
        logger.info(f"Updating channel {channel['id']} with {channel['statistics']['videoCount']} videos")
        YouTubeChannel.update(num_videos=int(channel['statistics']['videoCount'])).where(YouTubeChannel.id == channel['id']).execute()

def check_for_new_videos():
    channels = YouTubeChannel.select()
    current_channels = get_channels_by_id([channel.id for channel in channels])
    new_video_channels = get_channels_with_new_videos(channels, current_channels)
    update_channels(new_video_channels)

    if len(new_video_channels) > 0:
        send_youtube_channels_notifications(new_video_channels)

def _chunk_list(lst: list[str], chunk_size: int = 50) -> str:
    for i in range(0, len(lst), chunk_size):
        yield ','.join(lst[i:i + chunk_size])
