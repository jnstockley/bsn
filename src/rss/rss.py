import asyncio
import feedparser
import aiohttp
from feedparser import FeedParserDict

from util.logging import logger


async def get_youtube_feed(playlist_id: str, session: aiohttp.ClientSession):
    if await __valid_id(playlist_id):
        try:
            return await __get_rss_feed(playlist_id, session)
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


async def __get_rss_feed(playlist_id: str, session: aiohttp.ClientSession):
    url = f"https://www.youtube.com/feeds/videos.xml?playlist_id={playlist_id}"
    logger.debug(f"Fetching rss feed: {url}")

    async with session.get(url) as response:
        if response.status != 200:
            raise RuntimeError(f"Failed to fetch rss feed. Status code: {response.status}")
        content = await response.text()

    feed: FeedParserDict = await asyncio.to_thread(feedparser.parse, content)
    logger.debug("Successfully fetched rss feed")
    return feed
