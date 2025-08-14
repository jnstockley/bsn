import os.path
import time

import pandas as pd
from pandas import DataFrame

from models import database
from models.models import YouTubeChannel
from src import logger
from youtube.youtube import (
    import_subscriptions,
    check_for_new_videos,
    calculate_interval_between_cycles,
)


def read_csv_file(
    file_path: str,
) -> DataFrame:
    """
    Reads a CSV file and returns a DataFrame or raises an error if the file is not found or is empty.
    :param file_path: str
        The path to the CSV file to be read.
    :return: DataFrame
        A pandas DataFrame containing the data from the CSV file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File {file_path} not found")
    df = pd.read_csv(file_path)

    if df.empty:
        raise ValueError(f"File {file_path} is empty")

    return df


def create_tables():
    with database:
        logger.info("Creating tables...")
        database.create_tables([YouTubeChannel])


def update_tables(yt_df: pd.DataFrame):
    logger.info(
        "Ensuring YouTube Channels table is up to date with subscriptions file..."
    )
    with database:
        import_subscriptions(yt_df)


def initialize(
    yt_subscriptions_file: str = "./data/subscriptions.csv",
    sqlite_db: str = "./data/bsn.db",
):
    yt_df = read_csv_file(yt_subscriptions_file)
    database.database = sqlite_db
    if not database.table_exists("youtubechannel"):
        logger.info("YouTube Channels table does not exist. Creating tables...")
        create_tables()

    update_tables(yt_df)


def main():
    logger.info("Staring BSN...")
    initialize()
    interval_between_checks: int = calculate_interval_between_cycles()

    while True:
        check_for_new_videos()
        logger.info(f"Sleeping for {interval_between_checks} seconds...")
        time.sleep(interval_between_checks)


if __name__ == "__main__":
    main()
