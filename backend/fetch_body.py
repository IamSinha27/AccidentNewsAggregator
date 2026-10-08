"""
fetch_body.py
Two-step enrichment for each article, before it goes to extract.py:

1. resolve_url()      -- decode Google's redirect link into the real publisher URL
2. get_article_text() -- fetch that real URL and pull clean body text (no
   ads/nav/boilerplate) for the LLM to actually read, instead of just the
   thin headline-only snippet Google's RSS gives us.

Both steps hit the network per article and can fail for reasons outside
our control (paywalls, bot-blocking, slow/dead redirect tokens, publisher
sites that don't want scraping). Every function here degrades gracefully
-- returns None on failure rather than raising -- so the pipeline can fall
back to headline-only extraction rather than dropping the article entirely.
"""

from typing import Optional
from googlenewsdecoder import gnewsdecoder
import trafilatura

REQUEST_TIMEOUT = 10  # seconds, per network call


def resolve_url(google_link: str) -> Optional[str]:
    """Decode a news.google.com/rss/articles/... redirect link into the
    real publisher URL. Returns None if decoding fails."""
    try:
        result = gnewsdecoder(google_link, interval=1)
        # The success flag was renamed across googlenewsdecoder releases
        # ("status" in older ones, "success" in 0.2.x) -- accept either.
        if result.get("status") or result.get("success"):
            return result.get("decoded_url")
        return None
    except Exception:
        return None


def get_article_text(url: str, max_chars: int = 3000) -> Optional[str]:
    """Fetch a URL and extract clean article body text. Returns None if
    the fetch or extraction fails (paywall, block, dead link, etc)."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(downloaded)
        if not text:
            return None
        return text[:max_chars]
    except Exception:
        return None


def enrich_article(article: dict) -> dict:
    """Takes a raw article dict from fetch.py (has 'link' = Google redirect
    URL) and adds 'resolved_link' and 'body_text' keys. Both may be None
    if resolution/scraping failed -- caller should fall back to
    title+snippet extraction in that case, not skip the article."""
    resolved = resolve_url(article["link"])
    body_text = get_article_text(resolved) if resolved else None
    return {
        **article,
        "resolved_link": resolved,
        "body_text": body_text,
    }
