"""
run_pipeline.py
Cron entrypoint: fetch -> resolve -> scrape -> extract -> dedup/insert.

    python run_pipeline.py [--dry-run] [--limit N] [--workers N]

One bad article never aborts the run -- it's counted and the loop moves on.
The exit code is non-zero only when the run as a whole couldn't happen: the
database is unreachable or the RSS fetch came back empty.
"""

import argparse
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from typing import Optional
from zoneinfo import ZoneInfo

import psycopg

import db
from extract import extract_fields
from fetch import fetch_articles
from fetch_body import get_article_text, resolve_url
from store import forget_old_links, link_known, remember_link, save_article

IST = ZoneInfo("Asia/Kolkata")

# Final verdicts on a link: remembered so the next run doesn't scrape it and
# ask the LLM again. extraction-failed and error are left out on purpose --
# those are worth another attempt.
REMEMBERED = {"rejected-not-india", "rejected-not-recent", "same-event"}

# Threads for the per-article network steps. Kept modest: every article's
# redirect decode goes to Google, which rate-limits bursts.
DEFAULT_WORKERS = 8

# Order the summary is printed in.
OUTCOMES = [
    "fetched", "duplicate", "rejected-not-india", "rejected-not-recent",
    "extraction-failed", "error", "same-event", "inserted", "deferred",
]


def published_date_ist(published: Optional[str], today: Optional[date] = None) -> date:
    """Calendar date of an RSS `published` timestamp in Indian time. The feed
    gives GMT, so an article published at 01:00 IST would otherwise land on
    the previous day. Falls back to today (IST) if the timestamp is missing
    or unparseable -- the feed is already limited to the last day."""
    try:
        return parsedate_to_datetime(published).astimezone(IST).date()
    except (TypeError, ValueError):
        return today or datetime.now(IST).date()


def _scrape_and_extract(job):
    """Worker-thread half of an article: network only, no database. Returns
    (fields, error) so one article's failure stays its own."""
    article, resolved, _link = job
    try:
        body_text = get_article_text(resolved) if resolved else None
        return extract_fields(article["title"], article.get("snippet", ""), body_text), None
    except Exception as e:
        return None, e


def _store(conn: psycopg.Connection, article: dict, link: str, fields: Optional[dict]) -> str:
    """Turn one article's extraction result into its outcome, saving it if
    it passes both relevance flags. A link that gets turned down is
    remembered so later runs skip it. Doesn't commit -- the caller does."""
    outcome = _decide(conn, article, link, fields)
    if outcome in REMEMBERED:
        remember_link(conn, link, outcome)
    return outcome


def _decide(conn: psycopg.Connection, article: dict, link: str, fields: Optional[dict]) -> str:
    if fields is None:
        return "extraction-failed"
    if not fields["is_india_traffic_accident"]:
        return "rejected-not-india"
    if not fields["is_recent_accident"]:
        return "rejected-not-recent"
    return save_article(conn, {
        "date": published_date_ist(article.get("published")),
        "title": article["title"],
        "link": link,
        "source": article.get("source", ""),
        "severity": fields["severity"],
        "deaths": fields["deaths"],
        "injured": fields["injured"],
        "vehicles": fields["vehicles"],
        "state": fields["state"],
    })


def run(conn: psycopg.Connection, articles: list, dry_run: bool = False, limit: Optional[int] = None,
        workers: int = DEFAULT_WORKERS, deadline: Optional[float] = None, quiet: bool = False) -> Counter:
    """Process the articles and return a count per outcome.

    The slow part of each article is network I/O (decode the redirect, scrape
    the page, call the LLM), so that runs on `workers` threads. Everything
    that touches the database stays on the calling thread, in feed order:
    the same-event check depends on which article was stored first, and a
    psycopg connection can't be used from several threads at once.

    dry_run: nothing is committed. The whole batch runs in one transaction
    that is rolled back at the end, so the reported decisions (including
    same-event discards between articles in the same batch) match what a
    real run would do.

    deadline: a time.monotonic() value after which no further article is
    started. For hosts that cut a run off after a fixed time: what has been
    stored stays stored, and the rest is counted as 'deferred' -- nothing is
    remembered about those links, so the next run picks them up.

    quiet: don't print a line per article (failures are still reported). For
    hosts that keep only a limited number of log lines per run."""
    if limit is not None:
        articles = articles[:limit]
    counts = Counter(fetched=len(articles))

    def record(article, outcome):
        counts[outcome] += 1
        if not quiet:
            print(f"[{outcome}] {article.get('title', '')}", flush=True)

    def fail(article, e):
        conn.rollback()
        print(f"run_pipeline: failed on '{article.get('title', '')[:60]}': {e}", file=sys.stderr)
        record(article, "error")

    forget_old_links(conn)
    if not dry_run:
        conn.commit()

    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        # A redirect that won't decode isn't a reason to drop the article:
        # fall back to the Google link and to title-only extraction.
        resolved_links = list(pool.map(resolve_url, [a["link"] for a in articles]))
        unresolved = resolved_links.count(None)
        if unresolved:
            print(f"run_pipeline: {unresolved} of {len(articles)} redirects could not be decoded", file=sys.stderr)

        # Known links are dropped before the scrape and the LLM call, so
        # reruns cost nothing. `seen` does the same for two feed entries in
        # this batch that turn out to be the same page.
        pending = []
        seen = set()
        for article, resolved in zip(articles, resolved_links):
            link = resolved or article["link"]
            try:
                if link in seen or link_known(conn, link):
                    record(article, "duplicate")
                    continue
            except Exception as e:
                fail(article, e)
                continue
            seen.add(link)
            pending.append((article, resolved, link))

        handled = 0
        for (article, _resolved, link), (fields, error) in zip(pending, pool.map(_scrape_and_extract, pending)):
            if deadline is not None and time.monotonic() >= deadline:
                break
            handled += 1
            if error is not None:
                fail(article, error)
                continue
            try:
                outcome = _store(conn, article, link, fields)
                if not dry_run:
                    conn.commit()
            except Exception as e:
                fail(article, e)
                continue
            record(article, outcome)
        if handled < len(pending):
            counts["deferred"] = len(pending) - handled
    finally:
        # Past the deadline, articles still queued are dropped, not waited for.
        pool.shutdown(wait=True, cancel_futures=True)

    if dry_run:
        conn.rollback()
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch, extract and store today's accident articles.")
    parser.add_argument("--dry-run", action="store_true", help="go through every step but write no rows")
    parser.add_argument("--limit", type=int, help="only process the first N fetched articles")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help=f"threads for the per-article network steps (default {DEFAULT_WORKERS})")
    args = parser.parse_args()

    try:
        conn = db.connect()
        db.init_schema(conn)
    except Exception as e:
        print(f"run_pipeline: database unavailable: {e}", file=sys.stderr)
        return 1

    articles = fetch_articles()
    if not articles:
        # feedparser doesn't raise on a network error, it returns no entries;
        # an empty India-wide accident feed for a whole day isn't believable.
        print("run_pipeline: RSS fetch returned no articles", file=sys.stderr)
        conn.close()
        return 1

    counts = run(conn, articles, dry_run=args.dry_run, limit=args.limit, workers=args.workers)
    conn.close()

    print("\nSummary" + (" (dry run, nothing written)" if args.dry_run else ""))
    for name in OUTCOMES:
        print(f"  {name:<20} {counts[name]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
