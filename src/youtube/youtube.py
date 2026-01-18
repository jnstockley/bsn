import math
from datetime import datetime, timedelta

from googleapiclient.discovery import Resource

from googleapiclient.errors import HttpError

from models.models import YouTubeChannel, OAuthCredentials
from notifications.notifications import send_youtube_channels_notifications
from util.logging import logger


def pull_youtube_subscriptions(youtube: Resource):
    request = youtube.subscriptions().list(
        part="snippet,contentDetails",
        mine=True,
        maxResults=50,
    )
    response = request.execute()

    channels = response["items"]

    while response["nextPageToken"] if "nextPageToken" in response else None:
        request = youtube.subscriptions().list(
            part="snippet,contentDetails",
            mine=True,
            maxResults=50,
            pageToken=response["nextPageToken"],
        )
        response = request.execute()
        channels.extend(response["items"])

    assert len(channels) == response["pageInfo"]["totalResults"]

    for channel in channels:
        channel_id = channel["snippet"]["resourceId"]["channelId"]
        if not YouTubeChannel.select().where(YouTubeChannel.id == channel_id).exists():
            logger.info(
                f"Importing channel {channel_id} with {channel['contentDetails']['totalItemCount']} videos"
            )
            YouTubeChannel.create(
                id=channel_id,
                num_videos=int(channel["contentDetails"]["totalItemCount"]),
            )

    # delete channels that are no longer subscribed
    existing_channel_ids = [
        channel["snippet"]["resourceId"]["channelId"] for channel in channels
    ]
    for channel in YouTubeChannel.select():
        if channel.id not in existing_channel_ids:
            logger.info(f"Deleting channel {channel.id} as it is no longer subscribed")
            YouTubeChannel.delete_by_id(channel.id)


def get_channels_by_id(youtube: Resource, channel_ids: list[str]) -> list[dict] | None:
    channels: list[dict] = []

    for channel_str in _chunk_list(channel_ids):
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


def check_for_new_videos(youtube: Resource):
    channels = YouTubeChannel.select()
    current_channels = get_channels_by_id(youtube, [channel.id for channel in channels])
    new_video_channels = get_channels_with_new_videos(channels, current_channels)
    update_channels(new_video_channels)

    video = None
    if len(new_video_channels) > 0:
        if len(new_video_channels) == 1:
            video = get_most_recent_video(youtube, new_video_channels[0]["id"])

        send_youtube_channels_notifications(new_video_channels, video)


def get_most_recent_video(youtube: Resource, channel_id: str) -> dict | None:
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
    num_api_keys: int = len(OAuthCredentials.select())
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
