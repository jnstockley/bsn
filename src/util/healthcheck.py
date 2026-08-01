import sys

from auth import oauth
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
            raise Exception("No valid YouTube service available.")  # noqa: TRY002
        request = youtube.channels().list(part="id", id=example_channel_id)
        response = request.execute()
        __increment_quota_usage(1)
        if (
            "items" not in response
            or len(response["items"]) == 0
            or response["pageInfo"]["totalResults"] < 1
        ):
            raise Exception("Healthcheck channel not found.")  # noqa: TRY002
        logger.info("Healthcheck passed.")
        sys.exit(0)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Healthcheck failed: {e}", e)
        sys.exit(1)
