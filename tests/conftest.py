"""
Pytest configuration file for test setup and fixtures.
"""

import os
import sys
from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool


# Set required environment variables before importing any modules
os.environ["APPRISE_URLS"] = "test://localhost"
# Use in-memory SQLite for tests – the actual DATA_DIR value is overridden
# by the in_memory_db fixture below before any real DB connection is made.
os.environ["DATA_DIR"] = ":memory:"

# Ensure the src directory is in the Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


@pytest.fixture(autouse=True, scope="session")
def in_memory_db():
    """
    Create a shared in-memory SQLite engine for the entire test session and
    patch ``db.engine`` (plus the engine reference cached in every module
    that has already imported it) so no test ever touches a real database file.
    """
    from unittest.mock import patch

    import db as db_module
    from models import Base

    # StaticPool keeps the same connection alive so that tables created here
    # are visible to every Session opened against this engine.
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)

    # Replace the engine on the db module so future imports of `engine` from
    # db also get the in-memory engine.
    db_module.engine = test_engine

    # Patch the cached `engine` reference in every module that imported it.
    modules_to_patch = ["auth.oauth", "youtube.youtube", "youtube.quota"]
    patchers = []
    for mod_name in modules_to_patch:
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "engine"):
            p = patch.object(mod, "engine", test_engine)
            p.start()
            patchers.append(p)

    yield test_engine

    for p in patchers:
        p.stop()
