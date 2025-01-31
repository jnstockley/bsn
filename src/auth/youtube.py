from dotenv import load_dotenv
import os
from googleapiclient.discovery import build

from src import logger

load_dotenv()

# Set up the API key and service
API_KEYS = os.environ["YOUTUBE_API_KEYS"].split(",")
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"
api_key_index = 0


def get_youtube_service():
    global api_key_index
    api_key = API_KEYS[api_key_index]
    api_key_index = (api_key_index + 1) % len(API_KEYS)
    logger.info(f"Connecting to YouTube API with key index {api_key_index}")
    return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=api_key)
