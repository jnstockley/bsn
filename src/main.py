from models import database
from models.models import YouTubeChannel
from youtube.youtube import import_subscriptions


def create_tables():
    with database:
        database.create_tables([YouTubeChannel])

def populate_tables():
    with database:
        import_subscriptions('../data/subscriptions.csv')


def initialize():
    if not database.table_exists('youtubechannel'):
        create_tables()
        populate_tables()

if __name__ == '__main__':
    initialize()

