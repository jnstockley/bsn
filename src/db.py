import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from models import Base

load_dotenv()

data_url = os.getenv("DATA_DIR", "./data")

if data_url == ":memory:":
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(f"sqlite:///{data_url}/bsn.db")

Base.metadata.create_all(engine)
