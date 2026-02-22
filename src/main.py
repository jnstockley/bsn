import sys

from dotenv import load_dotenv

from auth import oauth as oauth
from notifications.notifications import send_upload_notification
from util.healthcheck import healthcheck
import time

from util.logging import logger
from youtube.quota import initialize_policy, initialize_usage
from youtube.youtube import (
    calculate_interval_between_cycles,
    pull_my_subscriptions,
    get_recent_videos,
)


def main():
    logger.info("Staring BSN...")

    oauth.get_authenticated_youtube_service()

    initialize_policy()

    while True:
        initialize_usage()
        youtube = oauth.get_authenticated_youtube_service()
        if youtube:
            _, recently_uploaded_channels = pull_my_subscriptions(youtube)
            interval_between_checks: int = calculate_interval_between_cycles()
            if recently_uploaded_channels:
                videos = get_recent_videos(recently_uploaded_channels, youtube)
                send_upload_notification(videos)

            logger.info(f"Sleeping for {interval_between_checks} seconds...")
            time.sleep(interval_between_checks)
        else:
            logger.error("No valid credentials available. Exiting.")
            exit(1)


if __name__ == "__main__":
    try:
        load_dotenv()
        if len(sys.argv) > 1 and sys.argv[1] == "healthcheck":
            healthcheck()
        else:
            main()
    except KeyboardInterrupt:
        logger.info("Shutting down BSN...")
        exit(0)
