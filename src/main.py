import tomllib
import argparse
from pathlib import Path

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
    try:
        pyproject_path = Path(__file__).parent.parent / "pyproject.toml"
        with open(pyproject_path, "rb") as f:
            data = tomllib.load(f)
        return data["project"]["version"]
    except (FileNotFoundError, KeyError):
        return "unknown"


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
