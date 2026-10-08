"""
db.py
Postgres connection + schema bootstrap. The connection string comes from
DATABASE_URL (Render injects it in production; locally it's read from .env).
"""

import os
from pathlib import Path
from typing import Optional

import psycopg
from dotenv import load_dotenv

load_dotenv()

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def connect(url: Optional[str] = None) -> psycopg.Connection:
    """Open a connection. Raises if no URL is given and DATABASE_URL isn't
    set -- there's no sensible default to fall back to."""
    url = url or os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return psycopg.connect(url)


def init_schema(conn: psycopg.Connection) -> None:
    """Create the articles table and indexes if they don't exist yet.
    Safe to call on every run."""
    conn.execute(SCHEMA_PATH.read_text())
    conn.commit()
