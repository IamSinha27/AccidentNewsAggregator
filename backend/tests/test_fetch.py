from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import fetch
from extract import INDIAN_STATES_UTS
from fetch import ACCIDENT_QUERY, REGIONS, fetch_articles


def entry(title, link, source="Outlet A"):
    return {"title": title, "link": link, "published": "Fri, 02 Oct 2026 08:30:00 GMT",
            "source": {"title": source}, "summary": ""}


def fake_feed(monkeypatch, entries_for):
    """Replace the network call. entries_for(query) -> list of entries.
    Returns the list of query strings that were requested."""
    queries = []

    def parse(url):
        query = parse_qs(urlparse(url).query)["q"][0]
        queries.append(query)
        return SimpleNamespace(entries=entries_for(query))

    monkeypatch.setattr(fetch.feedparser, "parse", parse)
    return queries


def test_regions_cover_every_state_plus_india():
    assert REGIONS == INDIAN_STATES_UTS + ["India"]


def test_one_short_query_per_region_each_with_recency_filter(monkeypatch):
    queries = fake_feed(monkeypatch, lambda q: [])
    fetch_articles(regions=["Uttar Pradesh", "Goa"])
    assert queries == [
        f'{ACCIDENT_QUERY} "Uttar Pradesh" when:1d',
        f'{ACCIDENT_QUERY} "Goa" when:1d',
    ]


def test_default_fetch_queries_every_region(monkeypatch):
    queries = fake_feed(monkeypatch, lambda q: [])
    fetch_articles()
    assert len(queries) == len(REGIONS)
    assert all(q.endswith(" when:1d") for q in queries)


def test_results_are_merged_across_regions(monkeypatch):
    fake_feed(monkeypatch, lambda q: [entry("Crash in Agra", "g/1")] if "Uttar" in q else [entry("Crash in Panaji", "g/2")])
    articles = fetch_articles(regions=["Uttar Pradesh", "Goa"])
    assert [a["title"] for a in articles] == ["Crash in Agra", "Crash in Panaji"]
    assert articles[0] == {
        "title": "Crash in Agra", "link": "g/1", "published": "Fri, 02 Oct 2026 08:30:00 GMT",
        "source": "Outlet A", "snippet": "",
    }


def test_article_returned_by_two_regions_is_kept_once(monkeypatch):
    fake_feed(monkeypatch, lambda q: [entry("Bus from Bengal overturns in Ramban", "g/1")])
    assert len(fetch_articles(regions=["West Bengal", "Jammu and Kashmir"])) == 1


def test_same_title_and_outlet_under_a_different_link_is_kept_once(monkeypatch):
    links = iter(["g/1", "g/2"])
    fake_feed(monkeypatch, lambda q: [entry("Crash in Agra", next(links))])
    assert len(fetch_articles(regions=["Uttar Pradesh", "India"])) == 1


def test_same_title_from_different_outlets_is_kept_twice(monkeypatch):
    fake_feed(monkeypatch, lambda q: [entry("Crash in Agra", "g/1", "Outlet A"), entry("Crash in Agra", "g/2", "Outlet B")])
    assert len(fetch_articles(regions=["Uttar Pradesh"])) == 2


def test_no_regions_runs_the_bare_query_once(monkeypatch):
    queries = fake_feed(monkeypatch, lambda q: [entry("Crash", "g/1")])
    assert len(fetch_articles(regions=None)) == 1
    assert queries == [f"{ACCIDENT_QUERY} when:1d"]
