import asyncio
import argparse
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.orm import Session

from alembic import command
from alembic.config import Config

from auth import oauth as oauth
from db import engine
from models import YoutubeChannel
from notifications.notifications import send_upload_notification
from rss import rss
from util.healthcheck import healthcheck
import time

from util.logging import logger
from youtube.quota import initialize_policy, initialize_usage
from youtube.youtube import (
    calculate_interval_between_cycles,
    pull_my_subscriptions,
    get_recent_content, fetch_all_recent_content,
)

def main():
    logger.info("Staring BSN...")

    alembic_cfg = Config(Path(__file__).parent.parent / "alembic.ini")
    command.upgrade(alembic_cfg, "head")
    logger.info("Database migrations applied.")

    start_time = time.perf_counter()
    asyncio.run(fetch_all_recent_content())
    elapsed = time.perf_counter() - start_time
    logger.info(f"fetch_all_recent_content completed in {elapsed:.2f}s")

    '''oauth.get_authenticated_youtube_service()

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
            exit(1)'''


def parse_args():
    parser = argparse.ArgumentParser(description="BSN - Social Media Upload Notifier")
    parser.add_argument(
        "command",
        nargs="?",
        default="run",
        choices=["healthcheck", "version", "help"],
        help="Optional command to run (e.g., healthcheck)",
    )
    return parser.parse_args()


def get_version():
    from util.version import get_version as _get_version
    return _get_version()


if __name__ == "__main__":
    try:
        load_dotenv()
        args = parse_args()
        if args.command == "healthcheck":
            healthcheck()
        elif args.command == "version":
            print(f"BSN Version {get_version()}")
        elif args.command == "help":
            print("Usage: python main.py [command]")
            print("Commands:")
            print("  healthcheck - Run a health check on the application")
            print("  version     - Display the current version of BSN")
            print("  help        - Show this help message")
        else:
            main()
    except KeyboardInterrupt:
        logger.info("Shutting down BSN...")
        exit(0)
