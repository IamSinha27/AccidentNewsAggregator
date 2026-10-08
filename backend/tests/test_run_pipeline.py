import threading
import time
from datetime import date

import pytest

import run_pipeline
from run_pipeline import published_date_ist, run

GOOGLE_LINK = "https://news.google.com/rss/articles/abc"
REAL_LINK = "https://example.com/agra-crash"


def raw(**overrides):
    article = {
        "title": "3 killed as car hits truck in Agra",
        "link": GOOGLE_LINK,
        "published": "Fri, 02 Oct 2026 08:30:00 GMT",
        "source": "Outlet A",
        "snippet": "",
    }
    article.update(overrides)
    return article


def extracted(**overrides):
    fields = {
        "is_india_traffic_accident": True,
        "is_recent_accident": True,
        "severity": "fatal",
        "deaths": 3,
        "injured": 0,
        "vehicles": ["Car", "Truck"],
        "state": "Uttar Pradesh",
    }
    fields.update(overrides)
    return fields


@pytest.fixture
def pipeline(monkeypatch):
    """Stub out the three network steps. Returns a dict the test can edit to
    change what they return, plus a list of the calls that were made."""
    state = {"resolved": REAL_LINK, "body": "Body text.", "fields": extracted(), "calls": []}

    def resolve_url(link):
        state["calls"].append("resolve")
        return state["resolved"]

    def get_article_text(url):
        state["calls"].append("scrape")
        return state["body"]

    def extract_fields(title, snippet="", body_text=None):
        state["calls"].append("extract")
        state["body_seen"] = body_text
        return state["fields"]

    monkeypatch.setattr(run_pipeline, "resolve_url", resolve_url)
    monkeypatch.setattr(run_pipeline, "get_article_text", get_article_text)
    monkeypatch.setattr(run_pipeline, "extract_fields", extract_fields)
    return state


def outcome(conn, article):
    """Run a single article and return what happened to it."""
    counts = run(conn, [article])
    del counts["fetched"]
    (name, n), = counts.items()
    assert n == 1
    return name


def rows(conn):
    return conn.execute(
        "SELECT date, title, link, source, severity, deaths, injured, vehicles, state FROM articles ORDER BY id"
    ).fetchall()


# --- date -----------------------------------------------------------------

@pytest.mark.parametrize("published,expected", [
    ("Fri, 02 Oct 2026 08:30:00 GMT", date(2026, 10, 2)),
    # 19:30 GMT is 01:00 IST the next day
    ("Fri, 02 Oct 2026 19:30:00 GMT", date(2026, 10, 3)),
    ("Fri, 02 Oct 2026 18:29:59 GMT", date(2026, 10, 2)),
])
def test_published_date_is_taken_in_ist(published, expected):
    assert published_date_ist(published) == expected


@pytest.mark.parametrize("published", ["", "not a date", None])
def test_unparseable_published_falls_back_to_today_ist(published):
    assert published_date_ist(published, today=date(2026, 10, 2)) == date(2026, 10, 2)


# --- one article ----------------------------------------------------------

def test_inserts_relevant_article_with_resolved_link_and_ist_date(conn, pipeline):
    assert outcome(conn, raw(published="Fri, 02 Oct 2026 19:30:00 GMT")) == "inserted"
    assert rows(conn) == [(
        date(2026, 10, 3), "3 killed as car hits truck in Agra", REAL_LINK, "Outlet A",
        "fatal", 3, 0, ["Car", "Truck"], "Uttar Pradesh",
    )]


def test_known_link_is_skipped_before_scrape_and_llm(conn, pipeline):
    run(conn, [raw()])
    pipeline["calls"].clear()
    assert outcome(conn, raw()) == "duplicate"
    assert pipeline["calls"] == ["resolve"]
    assert len(rows(conn)) == 1


def test_not_india_is_rejected(conn, pipeline):
    pipeline["fields"] = extracted(is_india_traffic_accident=False)
    assert outcome(conn, raw()) == "rejected-not-india"
    assert rows(conn) == []


def test_not_recent_is_rejected(conn, pipeline):
    pipeline["fields"] = extracted(is_recent_accident=False)
    assert outcome(conn, raw()) == "rejected-not-recent"
    assert rows(conn) == []


def test_extraction_failure_is_not_inserted(conn, pipeline):
    pipeline["fields"] = None
    assert outcome(conn, raw()) == "extraction-failed"
    assert rows(conn) == []


def test_unresolvable_redirect_stores_google_link_and_skips_scrape(conn, pipeline):
    pipeline["resolved"] = None
    assert outcome(conn, raw()) == "inserted"
    assert rows(conn)[0][2] == GOOGLE_LINK
    assert "scrape" not in pipeline["calls"]
    assert pipeline["body_seen"] is None


def test_second_outlet_for_same_event_is_discarded(conn, pipeline):
    run(conn, [raw()])
    pipeline["resolved"] = "https://other.example/agra"
    pipeline["fields"] = extracted(deaths=4)
    assert outcome(conn, raw(source="Outlet B", link=GOOGLE_LINK + "2")) == "same-event"
    assert [r[2] for r in rows(conn)] == [REAL_LINK]


# --- run ------------------------------------------------------------------

def test_run_counts_outcomes_and_survives_a_bad_article(conn, pipeline, monkeypatch):
    def extract_fields(title, snippet="", body_text=None):
        if title == "boom":
            raise RuntimeError("unexpected")
        return extracted()

    monkeypatch.setattr(run_pipeline, "extract_fields", extract_fields)
    articles = [raw(), raw(title="boom", link=GOOGLE_LINK + "x"), raw()]
    monkeypatch.setattr(run_pipeline, "resolve_url", lambda link: "https://example.com/" + link[-1])

    counts = run_pipeline.run(conn, articles)

    assert counts == {"fetched": 3, "inserted": 1, "error": 1, "duplicate": 1}
    assert len(rows(conn)) == 1


def test_rows_are_committed(conn, pipeline):
    import db
    from conftest import TEST_DATABASE_URL

    run_pipeline.run(conn, [raw()])
    other = db.connect(TEST_DATABASE_URL)
    try:
        assert other.execute("SELECT count(*) FROM articles").fetchone()[0] == 1
    finally:
        other.close()


def test_dry_run_writes_nothing_but_reports_decisions(conn, pipeline):
    counts = run_pipeline.run(conn, [raw(), raw()], dry_run=True)
    assert counts == {"fetched": 2, "inserted": 1, "duplicate": 1}
    assert rows(conn) == []


def test_limit_caps_articles_processed(conn, pipeline, monkeypatch):
    links = iter(["https://example.com/1", "https://example.com/2"])
    pipeline["fields"] = extracted(state="Unknown")
    monkeypatch.setattr(run_pipeline, "resolve_url", lambda link: next(links))
    counts = run_pipeline.run(conn, [raw(), raw(), raw()], limit=2)
    assert counts["fetched"] == 2
    assert len(rows(conn)) == 2


# --- parallelism ----------------------------------------------------------

def distinct(n):
    return [raw(title=f"Crash {i}", link=f"{GOOGLE_LINK}{i}") for i in range(n)]


def test_network_steps_run_concurrently(conn, pipeline, monkeypatch):
    # Each call waits for a second one to be in flight at the same time; run
    # one after another they would time out and raise.
    resolving = threading.Barrier(2, timeout=5)
    extracting = threading.Barrier(2, timeout=5)

    def resolve_url(link):
        resolving.wait()
        return "https://example.com/" + link[-1]

    def extract_fields(title, snippet="", body_text=None):
        extracting.wait()
        return extracted(state="Unknown")

    monkeypatch.setattr(run_pipeline, "resolve_url", resolve_url)
    monkeypatch.setattr(run_pipeline, "extract_fields", extract_fields)

    assert run(conn, distinct(2), workers=2) == {"fetched": 2, "inserted": 2}


def test_rows_are_stored_in_feed_order_whatever_finishes_first(conn, pipeline, monkeypatch):
    def extract_fields(title, snippet="", body_text=None):
        time.sleep(0.2 if title == "Crash 0" else 0)
        return extracted(state="Unknown")

    monkeypatch.setattr(run_pipeline, "resolve_url", lambda link: "https://example.com/" + link[-1])
    monkeypatch.setattr(run_pipeline, "extract_fields", extract_fields)

    run(conn, distinct(4), workers=4)

    assert [r[1] for r in rows(conn)] == ["Crash 0", "Crash 1", "Crash 2", "Crash 3"]


def test_same_link_twice_in_one_batch_is_extracted_once(conn, pipeline):
    counts = run(conn, [raw(), raw(link=GOOGLE_LINK + "2")], workers=2)
    assert counts == {"fetched": 2, "inserted": 1, "duplicate": 1}
    assert pipeline["calls"].count("extract") == 1


def test_workers_one_still_works(conn, pipeline):
    assert run(conn, [raw()], workers=1) == {"fetched": 1, "inserted": 1}


# --- remembering turned-down links ----------------------------------------

def seen(conn):
    return conn.execute("SELECT link, outcome FROM seen_links ORDER BY link").fetchall()


@pytest.mark.parametrize("fields,expected", [
    (extracted(is_india_traffic_accident=False), "rejected-not-india"),
    (extracted(is_recent_accident=False), "rejected-not-recent"),
])
def test_rejected_article_is_not_sent_to_the_llm_again(conn, pipeline, fields, expected):
    pipeline["fields"] = fields
    assert outcome(conn, raw()) == expected
    assert seen(conn) == [(REAL_LINK, expected)]

    pipeline["calls"].clear()
    pipeline["fields"] = extracted()  # the model would say yes this time
    assert outcome(conn, raw()) == "duplicate"
    assert pipeline["calls"] == ["resolve"]
    assert rows(conn) == []


def test_same_event_article_is_not_sent_to_the_llm_again(conn, pipeline):
    run(conn, [raw()])
    pipeline["resolved"] = "https://other.example/agra"
    assert outcome(conn, raw(source="Outlet B", link=GOOGLE_LINK + "2")) == "same-event"

    pipeline["calls"].clear()
    assert outcome(conn, raw(source="Outlet B", link=GOOGLE_LINK + "2")) == "duplicate"
    assert pipeline["calls"] == ["resolve"]


def test_failed_extraction_is_retried_next_run(conn, pipeline):
    pipeline["fields"] = None
    assert outcome(conn, raw()) == "extraction-failed"
    assert seen(conn) == []

    pipeline["fields"] = extracted()
    assert outcome(conn, raw()) == "inserted"


def test_stored_articles_are_not_added_to_seen_links(conn, pipeline):
    run(conn, [raw()])
    assert seen(conn) == []


def test_run_forgets_old_seen_links(conn, pipeline):
    conn.execute("INSERT INTO seen_links (link, outcome, seen_at) VALUES ('https://example.com/old', 'rejected-not-india', now() - interval '8 days')")
    conn.commit()
    run(conn, [raw()])
    assert seen(conn) == []


def test_dry_run_remembers_nothing(conn, pipeline):
    pipeline["fields"] = extracted(is_india_traffic_accident=False)
    run(conn, [raw()], dry_run=True)
    assert seen(conn) == []
