import time

from models import database
from models.models import YouTubeChannel
from src import logger
from youtube.youtube import import_subscriptions, get_channels_with_new_videos, check_for_new_videos, calculate_interval_between_cycles


def create_tables():
    with database:
        logger.info("Creating tables...")
        database.create_tables([YouTubeChannel])

def populate_tables():
    with database:
        file = '../data/subscriptions.csv'
        logger.info(f"Importing YouTube Subscriptions from {file}")
        import_subscriptions(file)


def initialize():
    if not database.table_exists('youtubechannel'):
        logger.info("YouTube Channels table does not exist. Creating tables and populating data...")
        create_tables()
        populate_tables()

if __name__ == '__main__':
    logger.info("Staring BSN...")
    initialize()
    interval_between_checks: int = calculate_interval_between_cycles()

    while True:
        check_for_new_videos()
        logger.info(f"Sleeping for {interval_between_checks} seconds...")
        time.sleep(interval_between_checks)