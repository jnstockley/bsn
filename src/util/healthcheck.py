from auth import oauth
from models import database
from models.models import OAuthCredentials
from util.logging import logger


def healthcheck() -> bool:
    example_channel_id = "UC_x5XG1OV2P6uZZ5FSM9Ttw"
    try:
        if not database.table_exists("youtubechannel"):
            raise Exception("YouTubeChannel table does not exist.")
        if not database.table_exists("oauth_credentials"):
            raise Exception("OAuthCredentials table does not exist.")
        if len(OAuthCredentials.select()) < 1:
            raise Exception("No OAuth credentials found in database.")
        youtube = oauth.get_authenticated_youtube_service(force_auth=True)
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
