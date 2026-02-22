from apprise import apprise

from models import YoutubeVideo
from notifications import apprise_urls
from util.logging import logger


def send_upload_notification(videos: list[YoutubeVideo]):
    appobj = apprise.Apprise()

    for apprise_url in apprise_urls:
        appobj.add(apprise_url)

    for video in videos:
        title = f"{video.youtube_channel.name} has uploaded a new video to YouTube!"
        body = f"{video.title}\n{video.url}\nUploaded at: {video.uploaded_at}"
        logger.info(
            f"Sending notification for video {video.title} from channel {video.youtube_channel.name}"
        )
        appobj.notify(title=title, body=body, attach=video.thumbnail_url)
