import time

from models import database
from models.models import YouTubeChannel
from src import logger
from youtube.youtube import import_subscriptions, get_channels_with_new_videos, check_for_new_videos


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
    #time.sleep(60)

    logger.info("Staring BSN...")
    initialize()

    while True:
        check_for_new_videos()
        logger.info("Sleeping for 60 seconds...")
        time.sleep(60)