"""
fetch.py
Pulls candidate articles from Google News RSS (India-scoped keyword search).
Relevance/geo-filtering is NOT done here -- that's handled entirely by the
LLM call in extract.py (is_india_traffic_accident / is_recent_accident), so
every fetched article gets passed on as a raw candidate for the LLM to judge.

The search is scoped to India by running the accident query once per state
(plus once for "India") and merging the results. The gl=IN/ceid=IN edition
parameters alone don't do it: an unscoped query comes back mostly US and UK
local crash stories. The states can't be OR-ed into one query either --
Google ignores terms past a length limit, which silently drops the `when:`
filter at the end and returns months-old articles.
"""

import feedparser
from typing import Optional
from urllib.parse import quote

from extract import INDIAN_STATES_UTS

RSS_BASE = "https://news.google.com/rss/search"

# Keywords that indicate a genuine traffic/road accident story
ACCIDENT_QUERY = '(accident OR crash OR collision OR "hit and run") AND (road OR highway OR bus OR truck OR car OR bike OR vehicle)'

# One request per entry. "India" picks up national stories that name no state.
REGIONS = INDIAN_STATES_UTS + ["India"]


def build_rss_url(query: str = ACCIDENT_QUERY, country: str = "IN", lang: str = "en", when: str = "1d") -> str:
    """when: Google's own recency filter, e.g. '1h', '1d', '7d'. Appended
    directly into the query string. Set to None/"" to disable."""
    full_query = f"{query} when:{when}" if when else query
    q = quote(full_query)
    return f"{RSS_BASE}?q={q}&hl={lang}-{country}&gl={country}&ceid={country}:{lang}"


def fetch_articles(query: str = ACCIDENT_QUERY, country: str = "IN", lang: str = "en", when: str = "1d",
                   regions: Optional[list] = REGIONS):
    """Fetch and parse the RSS feed. Returns list of dicts, unfiltered --
    pass each one to extract.extract_fields() to judge relevance/recency and
    pull structured fields.

    when: Google's recency filter (default '1d' for a daily cron run).
    Filters by when Google indexed/published the article, not necessarily
    when the accident occurred -- that distinction is handled by the LLM's
    is_recent_accident field, not here.

    regions: the query is run once per region with the region name added as
    a required phrase, and the results merged. An article that comes back
    for more than one region (or twice from the same outlet under different
    Google links) is kept once. Pass None to run the bare query once."""
    queries = [f'{query} "{region}"' for region in regions] if regions else [query]
    articles = []
    seen = set()
    for q in queries:
        feed = feedparser.parse(build_rss_url(q, country, lang, when))
        for entry in feed.entries:
            article = {
                "title": entry.get("title", ""),
                "link": entry.get("link", ""),
                "published": entry.get("published", ""),
                "source": entry.get("source", {}).get("title", "") if entry.get("source") else "",
                "snippet": entry.get("summary", ""),
            }
            keys = {article["link"], (article["title"], article["source"])}
            if keys & seen:
                continue
            seen |= keys
            articles.append(article)
    return articles
