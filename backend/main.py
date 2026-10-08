"""Entry point for Vercel, which looks for the FastAPI app in a file with one
of a few fixed names (main.py among them). The app itself lives in api.py."""

from api import app  # noqa: F401
