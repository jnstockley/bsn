import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

load_dotenv()

data_url = os.getenv("DATA_DIR", "./data")

if data_url == ":memory:":
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    data_dir = Path(data_url)
    if not data_dir.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
    engine = create_engine(f"sqlite:///{data_url}/bsn.db")
