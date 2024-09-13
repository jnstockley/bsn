import os
import string
import random
import pandas as pd

from googleapiclient.errors import HttpError

from auth.youtube import get_youtube_service
from models.models import YouTubeChannel


def import_subscriptions(subscriptions_file: str):
    if os.path.exists(subscriptions_file):
        subscriptions: list[str] = pd.read_csv(subscriptions_file)['Channel Id'].tolist()
        channels = get_channels_by_id(subscriptions)
        for channel in channels:
            YouTubeChannel.create(id=channel['id'], num_videos=int(channel['statistics']['videoCount']))
    else:
        print(f'File {subscriptions_file} not found')
        return

def get_channels_by_id(channel_ids: list[str]) -> list[dict] | None:
    channels: list[dict] = []

    youtube = get_youtube_service()

    for channel_str in _chunk_list(channel_ids):
        request = youtube.channels().list(
            part='statistics',
            id=channel_str
        )

        try:
            print(f"Making request {request.uri}")
            response = request.execute()
            if 'items' not in response:
                print(f'No items found with channel_ids: {channel_str}')
                return None
            channels.extend(response['items'])
        except HttpError as e:
            print(f'An HTTP error {e.resp.status} occurred: {e.content} with channel_ids: {channel_str}')
            return None

    return channels


def _chunk_list(lst: list[str], chunk_size: int = 50) -> str:
    for i in range(0, len(lst), chunk_size):
        yield ','.join(lst[i:i + chunk_size])


def generate_list(x, y):
    def random_string(size):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=size))

    return [random_string(y) for _ in range(x)]

def main():
    channel_ids = os.environ['YOUTUBE_CHANNEL_IDS'].split(',')
    print(channel_ids)
    channels = get_channels_by_id(channel_ids)
    print(channels)
    print(len(channels))
