import asyncio
import os
import tomllib
import argparse
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from dotenv import load_dotenv

from auth import oauth as oauth
from notifications.notifications import send_notifications
from util.healthcheck import healthcheck

from util.logging import logger
from youtube.quota import initialize_policy, initialize_usage
from youtube.youtube import (
    get_recent_videos,
    sync_subscriptions,
)


async def main():
    logger.info("Staring BSN...")

    interval: int = int(os.getenv("INTERVAL", default=30))

    oauth.get_authenticated_youtube_service()

    initialize_policy()
    initialize_usage()
    youtube = oauth.get_authenticated_youtube_service()

    sync_subscriptions(youtube)

    scheduler = BackgroundScheduler(timezone="America/Chicago")
    scheduler.add_job(sync_subscriptions, CronTrigger(minute=0), args=[youtube])
    scheduler.start()

    while True:
        try:
            logger.info("Fetching recent videos...")
            await get_recent_videos()
            logger.info("Fetched recent videos")
            send_notifications()
        except Exception as exc:
            logger.exception(f"Background cycle failed: {exc}")

        logger.info(f"Sleeping for {interval} seconds...")
        await asyncio.sleep(interval)


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
    except FileNotFoundError, KeyError:
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
            asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down BSN...")
        exit(0)
