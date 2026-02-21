import os

from dotenv import load_dotenv
from sqlalchemy import create_engine

from models import Base

load_dotenv()

data_url = os.getenv("DATA_DIR", "./data")

engine = create_engine(f"sqlite:///{data_url}/bsn.db")

Base.metadata.create_all(engine)
