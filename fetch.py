"""
fetch.py
Pulls candidate articles from Google News RSS (India, English) and filters
out non-traffic-accident noise (e.g. "stock market crash", "app crash").
"""

import feedparser
import re
from urllib.parse import quote

RSS_BASE = "https://news.google.com/rss/search"

# Keywords that indicate a genuine traffic/road accident story
ACCIDENT_QUERY = '(accident OR crash OR collision OR "hit and run") AND (road OR highway OR bus OR truck OR car OR bike OR vehicle)'

# Terms that, if present, usually mean it's NOT a traffic accident
FALSE_POSITIVE_PATTERNS = [
    r"\bstock market\b", r"\bshare[s]?\b.*\bcrash\b", r"\bsensex\b", r"\bnifty\b",
    r"\bapp\b.*\bcrash", r"\bserver\b.*\bcrash", r"\beconomy\b.*\bcrash",
    r"\bhousing market\b", r"\bcrypto\b", r"\bbitcoin\b",
    r"\bwedding crash(?:er)?\b", r"\bgatecrash",
]


def build_rss_url(query: str = ACCIDENT_QUERY, country: str = "IN", lang: str = "en") -> str:
    q = quote(query)
    return f"{RSS_BASE}?q={q}&hl={lang}-{country}&gl={country}&ceid={country}:{lang}"


def fetch_articles(query: str = ACCIDENT_QUERY, country: str = "IN", lang: str = "en"):
    """Fetch and parse the RSS feed. Returns list of dicts."""
    url = build_rss_url(query, country, lang)
    feed = feedparser.parse(url)
    articles = []
    for entry in feed.entries:
        articles.append({
            "title": entry.get("title", ""),
            "link": entry.get("link", ""),
            "published": entry.get("published", ""),
            "source": entry.get("source", {}).get("title", "") if entry.get("source") else "",
            "snippet": entry.get("summary", ""),
        })
    return articles


def is_relevant(article: dict) -> bool:
    text = f"{article['title']} {article.get('snippet', '')}"
    if any(re.search(p, text, re.I) for p in FALSE_POSITIVE_PATTERNS):
        return False
    return True


def fetch_and_filter(query: str = ACCIDENT_QUERY, country: str = "IN", lang: str = "en"):
    articles = fetch_articles(query, country, lang)
    return [a for a in articles if is_relevant(a)]
