import os

from apprise import apprise

from models import YoutubeVideo
from notifications import apprise_urls
from util.logging import logger


def send_upload_notification(videos: list[YoutubeVideo]):
    allow_shorts = os.getenv("ALLOW_SHORTS", "true").lower() == "true"
    allow_livestreams = os.getenv("ALLOW_LIVE_STREAMS", "true").lower() == "true"
    appobj = apprise.Apprise()

    for apprise_url in apprise_urls:
        appobj.add(apprise_url)

    for video in videos:
        if video.is_livestream:
            if not allow_livestreams:
                logger.info(
                    f"Skipping livestream {video.title} from channel {video.youtube_channel.name} due to configuration"
                )
                continue
            title = f"{video.youtube_channel.name} has started streaming on YouTube!"
            body = f"{video.title}\n{video.url}\nStarted at: {video.uploaded_at.strftime('%B %d, %Y %I:%M %p')}"
        elif video.is_short:
            if not allow_shorts:
                logger.info(
                    f"Skipping short {video.title} from channel {video.youtube_channel.name} due to configuration"
                )
                continue
            title = f"{video.youtube_channel.name} has uploaded a new video to YouTube Short!"
            body = f"{video.title}\n{video.url}\nUploaded at: {video.uploaded_at.strftime('%B %d, %Y %I:%M %p')}"
        else:
            title = f"{video.youtube_channel.name} has uploaded a new video to YouTube!"
            body = f"{video.title}\n{video.url}\nUploaded at: {video.uploaded_at.strftime('%B %d, %Y %I:%M %p')}"
        logger.info(
            f"Sending notification for video/livestream {video.title} from channel {video.youtube_channel.name}"
        )
        appobj.notify(title=title, body=body, attach=video.thumbnail_url)
