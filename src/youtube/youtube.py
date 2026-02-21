import math
from datetime import datetime, timezone

from googleapiclient.discovery import Resource

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from db import engine
from models import YoutubeChannel, OauthCredential, YoutubeVideo
from util.logging import logger


def pull_my_subscriptions(youtube: Resource):
    request = youtube.subscriptions().list(
        part="snippet,contentDetails",
        mine=True,
        maxResults=50,
    )

    response = __make_request(request)

    channels, recently_uploaded_channels = __youtube_subs_response_to_channels(response)

    return channels, recently_uploaded_channels


def get_recent_videos(
    channels: list[YoutubeChannel], youtube: Resource
) -> list[YoutubeVideo]:
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

        body = response["items"][0]

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

        video = YoutubeVideo(
            id=body["contentDetails"]["videoId"],
            title=body["snippet"]["title"],
            url=f"https://www.youtube.com/watch?v={body['contentDetails']['videoId']}",
            thumbnail_url=body["snippet"]["thumbnails"]["high"]["url"],
            is_short=False,
            is_livestream=False,
            uploaded_at=local_time,
            youtube_channel_id=channel_id,
        )

        logger.info(f"Found new video: {video}")

        stmt = delete(YoutubeVideo).where(YoutubeVideo.youtube_channel_id == channel_id)

        with Session(engine) as s:
            s.execute(stmt)
            s.add(video)
            s.commit()
            s.refresh(video)
            # Eager load the youtube_channel relationship to prevent DetachedInstanceError
            _ = video.youtube_channel
            s.expunge(video)

        videos.append(video)

    return videos


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
                channel.name = c["snippet"]["title"]
                s.flush()
                s.commit()
                s.refresh(channel)

            all_channels.append(channel)

    return all_channels, recently_uploaded_channels


def __make_request(request) -> dict:
    logger.debug(f"Making request {request.uri}")

    root_uri = request.uri

    response = request.execute()
    response_body = response["items"]

    while response["nextPageToken"] if "nextPageToken" in response else None:
        next_page_token = response["nextPageToken"]

        request.uri = root_uri + f"&pageToken={next_page_token}"

        logger.debug(f"Making request {request.uri}")
        response = request.execute()
        response_body.extend(response["items"])

    return response_body


def calculate_interval_between_cycles():
    with Session(engine) as s:
        num_channels: int = len(s.execute(select(YoutubeChannel)).scalars().all())
        num_api_keys: int = len(s.execute(select(OauthCredential)).scalars().all())

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
