from pathlib import Path
import os
from peewee import SqliteDatabase

# Allow overriding path via env var; default to data/bsn.db
_db_path = Path(os.getenv("BSN_SQLITE_DB", "../data/bsn.db"))
_db_path.parent.mkdir(parents=True, exist_ok=True)

database = SqliteDatabase(str(_db_path))
