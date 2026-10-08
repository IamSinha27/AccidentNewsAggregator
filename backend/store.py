"""
store.py
Dedup + insert for extracted articles. Two separate dedup problems:

1. Exact duplicate -- the same article URL seen again (cron rerun, same URL
   via two query variants). Skipped.
2. Same real-world event, different outlet -- matched on date + state +
   vehicle(s), with the death toll compared loosely. One link per accident is
   enough, so the later article is discarded and the first one stored stays.

The event match is a heuristic and accepted as imperfect: it can discard an
unrelated accident with the same state/vehicle on a busy day, and let the
same accident through twice when outlets name different vehicle types.
"""

from typing import Optional

import psycopg

# Outlets often disagree by one on the death toll early in coverage.
DEATH_COUNT_TOLERANCE = 1

# How long a turned-down link is remembered. The feed only reaches back one
# day, so a week is a wide margin.
SEEN_LINK_DAYS = 7


def casualties_match(severity_a: str, deaths_a: int, severity_b: str, deaths_b: int) -> bool:
    """Loose comparison: could these two outcomes describe the same accident?
    Fatal never matches non-fatal; two stated death counts must be within
    the tolerance; a toll of 0 on a fatal accident means it wasn't stated,
    which is compatible with any count."""
    if severity_a != severity_b:
        return False
    if not deaths_a or not deaths_b:
        return True
    return abs(deaths_a - deaths_b) <= DEATH_COUNT_TOLERANCE


def link_known(conn: psycopg.Connection, link: str) -> bool:
    """True if this URL has been dealt with before: either stored as an
    article, or looked at and turned down (see remember_link)."""
    row = conn.execute(
        "SELECT 1 FROM articles WHERE link = %s UNION ALL SELECT 1 FROM seen_links WHERE link = %s LIMIT 1",
        (link, link),
    ).fetchone()
    return row is not None


def remember_link(conn: psycopg.Connection, link: str, outcome: str) -> None:
    """Record that this URL was looked at and turned down, so the next run
    skips it instead of scraping it and asking the LLM again."""
    conn.execute(
        "INSERT INTO seen_links (link, outcome) VALUES (%s, %s) ON CONFLICT (link) DO NOTHING",
        (link, outcome),
    )


def forget_old_links(conn: psycopg.Connection, days: int = SEEN_LINK_DAYS) -> int:
    """Drop remembered links older than `days`, which keeps seen_links from
    growing without bound. Returns how many were removed."""
    return conn.execute(
        "DELETE FROM seen_links WHERE seen_at < now() - make_interval(days => %s)", (days,)
    ).rowcount


def _find_same_event(conn: psycopg.Connection, article: dict) -> Optional[int]:
    """Id of an existing row that looks like the same accident, or None."""
    # An unlocated accident can't be matched on location, and two of them on
    # the same day are more likely different events than the same one.
    if not article["state"] or article["state"] == "Unknown":
        return None
    candidates = conn.execute(
        "SELECT id, vehicles, severity, deaths FROM articles WHERE date = %s AND state = %s ORDER BY id",
        (article["date"], article["state"]),
    ).fetchall()
    wanted = set(article["vehicles"])
    for row_id, vehicles, severity, deaths in candidates:
        if set(vehicles) == wanted and casualties_match(severity, deaths, article["severity"], article["deaths"]):
            return row_id
    return None


def save_article(conn: psycopg.Connection, article: dict) -> str:
    """Store one extracted article. `article` needs: date, title, link,
    source, severity, deaths, injured, vehicles (a list), state.

    Returns 'duplicate' (link already stored), 'same-event' (another outlet's
    article on this accident is already stored) or 'inserted' (new row).
    Only 'inserted' writes anything."""
    with conn.transaction():
        if link_known(conn, article["link"]):
            return "duplicate"

        if _find_same_event(conn, article) is not None:
            return "same-event"

        conn.execute(
            """
            INSERT INTO articles (date, title, link, source, severity, deaths, injured, vehicles, state)
            VALUES (%(date)s, %(title)s, %(link)s, %(source)s, %(severity)s, %(deaths)s, %(injured)s, %(vehicles)s, %(state)s)
            ON CONFLICT (link) DO NOTHING
            """,
            article,
        )
        return "inserted"
