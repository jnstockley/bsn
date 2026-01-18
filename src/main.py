import sys

from dotenv import load_dotenv

from auth import oauth
from util.healthcheck import healthcheck
import time

from models import database
from models.models import YouTubeChannel, OAuthCredentials
from util.logging import logger
from youtube.youtube import (
    check_for_new_videos,
    calculate_interval_between_cycles,
    pull_youtube_subscriptions,
)


def main():
    logger.info("Staring BSN...")
    if not database.table_exists("youtubechannel") or not database.table_exists(
        "oauthcredentials"
    ):
        logger.info("YouTube Channels table does not exist. Creating table...")
        database.create_tables([YouTubeChannel])
    if not database.table_exists("oauthcredentials"):
        logger.info("OAuth Credentials table does not exist. Creating table...")
        database.create_tables([OAuthCredentials])
        oauth.get_authenticated_youtube_service(force_auth=True)

    interval_between_checks: int = calculate_interval_between_cycles()

    while True:
        youtube = oauth.get_authenticated_youtube_service(force_auth=True)
        if youtube:
            pull_youtube_subscriptions(youtube)
            # TODO More work could be done to reduce API calls, by using `subscription` to check video counts
            check_for_new_videos(youtube)
            logger.info(f"Sleeping for {interval_between_checks} seconds...")
            time.sleep(interval_between_checks)
        else:
            logger.error("No valid credentials available. Exiting.")
            exit(1)


if __name__ == "__main__":
    load_dotenv()
    if len(sys.argv) > 1 and sys.argv[1] == "healthcheck":
        healthcheck()
    else:
        main()
