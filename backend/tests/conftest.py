import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import db  # noqa: E402

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "postgresql://localhost/accident_news_test")


@pytest.fixture
def conn():
    """Connection to the test database with empty tables."""
    connection = db.connect(TEST_DATABASE_URL)
    db.init_schema(connection)
    connection.execute("TRUNCATE articles, seen_links RESTART IDENTITY")
    connection.commit()
    yield connection
    connection.close()
