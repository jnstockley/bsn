import asyncio

from auth import oauth as oauth
from rss.rss import get_youtube_feed
from util.logging import logger
from youtube.quota import initialize_policy, initialize_usage
from youtube.youtube import __increment_quota_usage


def healthcheck() -> bool:
    example_channel_id = "UC_x5XG1OV2P6uZZ5FSM9Ttw"
    initialize_policy()
    initialize_usage()
    try:
        youtube = oauth.get_authenticated_youtube_service()
        if not youtube:
            raise Exception("No valid YouTube service available.")
        request = youtube.channels().list(part="id", id=example_channel_id)
        response = request.execute()
        __increment_quota_usage(1)
        if (
            "items" not in response
            or len(response["items"]) == 0
            or response["pageInfo"]["totalResults"] < 1
        ):
            raise Exception("Healthcheck channel not found.")

        rss_response = asyncio.run(get_youtube_feed(f"UULF{example_channel_id[2:]}"))
        if not rss_response:
            raise Exception("Error getting RSS feed from YouTube.")

        logger.info("Healthcheck passed.")
        exit(0)
    except Exception as e:
        logger.error(f"Healthcheck failed: {e}", e)
        exit(1)
