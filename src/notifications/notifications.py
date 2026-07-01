import os
from datetime import datetime

from apprise import apprise
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from db import engine
from model import YoutubeContent
from notifications import apprise_urls
from youtube_notify import ContentType
from util.logging import logger


def send_notifications():
    logger.info("Sending notifications")
    allow_shorts = os.getenv("ALLOW_SHORTS", "true").lower() == "true"
    allow_livestreams = os.getenv("ALLOW_LIVE_STREAMS", "true").lower() == "true"
    allowed_types = [ContentType.VIDEO]
    if allow_shorts:
        allowed_types.append(ContentType.SHORT)
    if allow_livestreams:
        allowed_types.append(ContentType.LIVESTREAM)

    with Session(engine) as s:
        stmt = (
            select(YoutubeContent)
            .options(selectinload(YoutubeContent.youtube_channel))
            .where(
                YoutubeContent.notified.is_(False),
                YoutubeContent.content_type.in_(allowed_types),
            )
            .order_by(YoutubeContent.published_at.asc())
        )

        contents = s.execute(stmt).scalars().all()

        if not contents:
            logger.info("No pending notifications to send")
            return

        appobj = apprise.Apprise()
        for apprise_url in apprise_urls:
            appobj.add(apprise_url)

        for content in contents:
            if content.content_type == ContentType.LIVESTREAM:
                title = (
                    f"{content.youtube_channel.name} has started streaming on YouTube!"
                )
                body = (
                    f"{content.title}\n"
                    f"{content.youtube_channel.name}\n"
                    f"Started at: {content.published_at.astimezone().strftime('%B %d, %Y %I:%M %p')}"
                )
            elif content.content_type == ContentType.SHORT:
                title = f"{content.youtube_channel.name} has uploaded a new video to YouTube Short!"
                body = (
                    f"{content.title}\n"
                    f"{content.youtube_channel.name}\n"
                    f"Uploaded at: {content.published_at.astimezone().strftime('%B %d, %Y %I:%M %p')}"
                )
            else:
                title = f"{content.youtube_channel.name} has uploaded a new video to YouTube!"
                body = (
                    f"{content.title}\n"
                    f"{content.youtube_channel.name}\n"
                    f"Uploaded at: {content.published_at.astimezone().strftime('%B %d, %Y %I:%M %p')}"
                )

            logger.info(
                f"Sending notification for content {content.title} from channel {content.youtube_channel.name}"
            )
            appobj.notify(title=title, body=body, attach=content.thumbnail_url)
            content.notified = True
            content.notified_at = datetime.now().astimezone()

        s.commit()
