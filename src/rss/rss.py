import asyncio
import feedparser
from feedparser import FeedParserDict

from main import get_version
from util.logging import logger


async def get_youtube_feed(playlist_id: str):
    if await __valid_id(playlist_id):
        try:
            return await __get_rss_feed(playlist_id)
        except RuntimeError as e:
            logger.error(f"Failed to fetch rss feed. Error: {e}")
            return None
    raise ValueError("Invalid playlist ID")

async def __valid_id(playlist_id: str) -> bool:
    valid_prefixes = {"UULF": "videos", "UULV": "livestreams", "UUSH": "shorts"}
    for prefix in valid_prefixes:
        if playlist_id.startswith(prefix):
            return len(playlist_id) == 26
    return False


async def __get_rss_feed(playlist_id: str):
    url = f"https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"
    version = get_version()
    user_agent = f"bsn/{version}"
    logger.debug(f"Fetching rss feed: {url}")
    feed: FeedParserDict = await asyncio.to_thread(feedparser.parse, url, agent=user_agent)

    status_code = feed.status
    if status_code == 200:
        logger.debug("Successfully fetched rss feed")
        return feed
    else:
        raise RuntimeError(f"Failed to fetch rss feed. Status code: {status_code}")
