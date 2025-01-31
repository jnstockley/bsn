from apprise import apprise
from src import logger

from notifications import apprise_urls


def send_youtube_channels_notifications(channels: list[dict], video: dict = None):
    apobj = apprise.Apprise()

    for apprise_url in apprise_urls:
        apobj.add(apprise_url)

    if len(channels) > 1:
        title = f"{','.join([channel['snippet']['title'] for channel in channels])} have uploaded new videos to YouTube!"
        body = "Check them out here: https://www.youtube.com/feed/subscriptions"
    elif video:
        video_title = video["snippet"]["title"]
        video_url = f"https://www.youtube.com/watch?v={video['snippet']['resourceId']['videoId']}"
        title = (
            f"{channels[0]['snippet']['title']} has uploaded a new video to YouTube!"
        )
        body = f"{video_title}\n{video_url}"
    else:
        logger.warning("No video found")
        return

    logger.info(f"Sending notifications for {channels} channels")
    apobj.notify(title=title, body=body)
