from datetime import date

import psycopg
import pytest

from extract import VEHICLE_TYPES
from store import casualties_match, forget_old_links, link_known, remember_link, save_article

DAY = date(2026, 10, 2)


def make(**overrides):
    article = {
        "date": DAY,
        "title": "3 killed as car hits truck in Agra",
        "link": "https://example.com/a",
        "source": "Outlet A",
        "severity": "fatal",
        "deaths": 3,
        "injured": 0,
        "vehicles": ["Car", "Truck"],
        "state": "Uttar Pradesh",
    }
    article.update(overrides)
    return article


def rows(conn):
    return conn.execute("SELECT link, source FROM articles ORDER BY id").fetchall()


# --- pure helpers ---------------------------------------------------------

FATAL, NON_FATAL = "fatal", "non-fatal"


@pytest.mark.parametrize("a,b,expected", [
    ((FATAL, 3), (FATAL, 3), True),
    ((FATAL, 3), (FATAL, 4), True),
    ((FATAL, 3), (FATAL, 2), True),
    ((FATAL, 3), (FATAL, 5), False),
    ((FATAL, 0), (FATAL, 7), True),
    ((FATAL, 0), (FATAL, 0), True),
    ((NON_FATAL, 0), (NON_FATAL, 0), True),
    ((FATAL, 1), (NON_FATAL, 0), False),
    ((FATAL, 0), (NON_FATAL, 0), False),
])
def test_casualties_match(a, b, expected):
    assert casualties_match(*a, *b) is expected
    assert casualties_match(*b, *a) is expected


# --- save_article ---------------------------------------------------------

def test_inserts_new_article(conn):
    assert save_article(conn, make()) == "inserted"
    assert rows(conn) == [("https://example.com/a", "Outlet A")]


def test_exact_duplicate_link_is_skipped(conn):
    save_article(conn, make())
    assert save_article(conn, make(title="Different headline, same URL")) == "duplicate"
    assert len(rows(conn)) == 1


def test_same_event_from_another_outlet_is_discarded(conn):
    save_article(conn, make())
    result = save_article(conn, make(link="https://example.com/b", source="Outlet B", deaths=4))
    assert result == "same-event"
    assert rows(conn) == [("https://example.com/a", "Outlet A")]


def test_vehicle_order_does_not_hide_a_same_event(conn):
    save_article(conn, make())
    assert save_article(conn, make(link="https://example.com/b", vehicles=["Truck", "Car"])) == "same-event"


def test_death_count_too_far_apart_is_a_new_row(conn):
    save_article(conn, make())
    assert save_article(conn, make(link="https://example.com/b", deaths=6)) == "inserted"
    assert len(rows(conn)) == 2


def test_fatal_and_non_fatal_are_different_events(conn):
    save_article(conn, make())
    assert save_article(conn, make(link="https://example.com/b", severity="non-fatal", deaths=0)) == "inserted"


def test_severity_deaths_and_injured_are_stored(conn):
    save_article(conn, make(injured=5))
    assert conn.execute("SELECT severity, deaths, injured FROM articles").fetchall() == [("fatal", 3, 5)]


def test_every_vehicle_type_can_be_stored_and_nothing_else(conn):
    save_article(conn, make(vehicles=VEHICLE_TYPES))
    assert conn.execute("SELECT vehicles FROM articles").fetchone()[0] == VEHICLE_TYPES
    with pytest.raises(psycopg.errors.CheckViolation):
        save_article(conn, make(link="https://example.com/b", vehicles=["Hovercraft"]))
    conn.rollback()


def test_deaths_on_a_non_fatal_row_are_refused(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        save_article(conn, make(severity="non-fatal", deaths=2))
    conn.rollback()


@pytest.mark.parametrize("field,value", [
    ("state", "Bihar"),
    ("vehicles", ["Bus"]),
    ("vehicles", ["Bus", "Car", "Truck"]),
    ("vehicles", []),
    ("date", date(2026, 10, 1)),
])
def test_different_state_vehicle_or_date_is_a_new_row(conn, field, value):
    save_article(conn, make())
    assert save_article(conn, make(link="https://example.com/b", **{field: value})) == "inserted"


def test_unknown_state_is_never_treated_as_same_event(conn):
    save_article(conn, make(state="Unknown"))
    assert save_article(conn, make(link="https://example.com/b", state="Unknown")) == "inserted"
    assert len(rows(conn)) == 2


def test_articles_table_has_no_sources_column(conn):
    columns = [c.name for c in conn.execute("SELECT * FROM articles LIMIT 0").description]
    assert "sources" not in columns


def test_link_known_checks_stored_links(conn):
    save_article(conn, make())
    assert link_known(conn, "https://example.com/a")
    assert not link_known(conn, "https://example.com/zzz")


# --- seen links -----------------------------------------------------------

def seen(conn):
    return conn.execute("SELECT link, outcome FROM seen_links ORDER BY link").fetchall()


def test_remembered_link_is_known(conn):
    remember_link(conn, "https://example.com/rejected", "rejected-not-india")
    assert link_known(conn, "https://example.com/rejected")
    assert seen(conn) == [("https://example.com/rejected", "rejected-not-india")]


def test_remembering_the_same_link_twice_keeps_one_row(conn):
    remember_link(conn, "https://example.com/rejected", "rejected-not-india")
    remember_link(conn, "https://example.com/rejected", "same-event")
    assert seen(conn) == [("https://example.com/rejected", "rejected-not-india")]


def test_remembered_link_is_not_saved_as_an_article(conn):
    remember_link(conn, "https://example.com/a", "rejected-not-recent")
    assert save_article(conn, make()) == "duplicate"
    assert rows(conn) == []


def test_old_seen_links_are_forgotten_and_recent_ones_kept(conn):
    remember_link(conn, "https://example.com/old", "rejected-not-india")
    remember_link(conn, "https://example.com/new", "rejected-not-india")
    conn.execute("UPDATE seen_links SET seen_at = now() - interval '8 days' WHERE link = 'https://example.com/old'")
    assert forget_old_links(conn) == 1
    assert [link for link, _ in seen(conn)] == ["https://example.com/new"]


def test_forgetting_seen_links_leaves_articles_alone(conn):
    save_article(conn, make())
    conn.execute("UPDATE articles SET created_at = now() - interval '90 days'")
    forget_old_links(conn)
    assert len(rows(conn)) == 1
