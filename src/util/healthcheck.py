from auth import oauth as oauth
from util.logging import logger


def healthcheck() -> bool:
    example_channel_id = "UC_x5XG1OV2P6uZZ5FSM9Ttw"
    try:
        youtube = oauth.get_authenticated_youtube_service()
        if not youtube:
            raise Exception("No valid YouTube service available.")
        request = youtube.channels().list(part="id", id=example_channel_id)
        response = request.execute()
        if (
            "items" not in response
            or len(response["items"]) == 0
            or response["pageInfo"]["totalResults"] < 1
        ):
            raise Exception("Healthcheck channel not found.")
        logger.info("Healthcheck passed.")
        exit(0)
    except Exception as e:
        logger.error(f"Healthcheck failed: {e}", e)
        exit(1)
