from pathlib import Path
import os
from peewee import SqliteDatabase

# Allow overriding path via env var; default to data/bsn.db
_db_path = Path(os.getenv("DATA_DIR", "../data")) / "bsn.db"
_db_path.parent.mkdir(parents=True, exist_ok=True)

database = SqliteDatabase(str(_db_path))
