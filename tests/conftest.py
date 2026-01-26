"""
Pytest configuration file for test setup and fixtures.
"""
import os
import sys
from pathlib import Path

# Set required environment variables before importing any modules
os.environ["APPRISE_URLS"] = "test://localhost"
os.environ["DATA_DIR"] = str(Path(__file__).parent / "test_data")

# Ensure the src directory is in the Python path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))
