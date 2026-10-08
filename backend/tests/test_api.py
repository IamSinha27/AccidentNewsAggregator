from datetime import date

import pytest
from fastapi.testclient import TestClient

import api
from store import save_article


@pytest.fixture
def client(conn):
    api.app.dependency_overrides[api.get_conn] = lambda: conn
    yield TestClient(api.app)
    api.app.dependency_overrides.clear()


def add(conn, day, link, **overrides):
    article = {
        "date": day,
        "title": "3 killed as car hits truck in Agra",
        "link": link,
        "source": "Outlet A",
        "severity": "fatal",
        "deaths": 3,
        "injured": 2,
        "vehicles": ["Car", "Truck"],
        "state": "Uttar Pradesh",
    }
    article.update(overrides)
    assert save_article(conn, article) == "inserted"


@pytest.fixture
def two_days(conn):
    add(conn, date(2026, 10, 1), "https://example.com/old", state="Bihar")
    add(conn, date(2026, 10, 2), "https://example.com/a")
    add(conn, date(2026, 10, 2), "https://example.com/b", state="Goa", title="Bus overturns in Goa")
    conn.commit()


ZERO = {"accidents": 0, "fatal": 0, "non_fatal": 0, "deaths": 0, "injured": 0}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_articles_defaults_to_latest_date_with_data(client, two_days):
    body = client.get("/articles").json()
    assert body["date"] == "2026-10-02"
    assert body["latest_date"] == "2026-10-02"
    assert [a["link"] for a in body["articles"]] == ["https://example.com/b", "https://example.com/a"]


def test_article_has_exactly_the_documented_fields(client, two_days):
    article = client.get("/articles").json()["articles"][1]
    assert article == {
        "id": article["id"],
        "date": "2026-10-02",
        "title": "3 killed as car hits truck in Agra",
        "severity": "fatal",
        "deaths": 3,
        "injured": 2,
        "vehicles": ["Car", "Truck"],
        "state": "Uttar Pradesh",
        "link": "https://example.com/a",
        "source": "Outlet A",
    }
    assert isinstance(article["id"], int)


def test_articles_for_an_explicit_date(client, two_days):
    body = client.get("/articles", params={"date": "2026-10-01"}).json()
    assert body["date"] == "2026-10-01"
    assert body["latest_date"] == "2026-10-02"
    assert [a["state"] for a in body["articles"]] == ["Bihar"]


def test_date_with_no_data_returns_empty_list(client, two_days):
    response = client.get("/articles", params={"date": "2026-09-15"})
    assert response.status_code == 200
    assert response.json() == {"date": "2026-09-15", "latest_date": "2026-10-02", "totals": ZERO, "articles": []}


def test_empty_database(client):
    assert client.get("/articles").json() == {"date": None, "latest_date": None, "totals": ZERO, "articles": []}
    assert client.get("/dates").json() == {"dates": []}
    assert client.get("/stats/daily").json() == {"first_date": None, "latest_date": None, "days": []}
    assert client.get("/stats/states").json() == {"date": None, "month": None, "states": [], "unknown": ZERO}


@pytest.mark.parametrize("bad", ["yesterday", "2026-13-40", "02-10-2026", ""])
def test_malformed_date_is_rejected(client, bad):
    assert client.get("/articles", params={"date": bad}).status_code == 422


# --- a spread of accidents for the totals and filters ----------------------

SEP_30, OCT_1, OCT_2 = date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)


@pytest.fixture
def spread(conn):
    """Six accidents over two months, three states and one unlocated.
    Vehicles differ so that none of them counts as the same event."""
    def put(n, day, state, severity="non-fatal", deaths=0, injured=0, vehicles=("Car",)):
        add(conn, day, f"https://example.com/{n}", state=state, severity=severity, deaths=deaths,
            injured=injured, vehicles=list(vehicles), title=f"Accident {n}")

    put(1, SEP_30, "Bihar", "fatal", 2, 1)
    put(2, OCT_1, "Bihar", injured=4)
    put(3, OCT_1, "Goa", "fatal", 0, 3)                       # fatal, toll not stated
    put(4, OCT_2, "Bihar", "fatal", 5, 0, vehicles=("Bus",))
    put(5, OCT_2, "Bihar", injured=2, vehicles=("Truck",))
    put(6, OCT_2, "Unknown", "fatal", 1, 0)
    conn.commit()


def titles(body):
    return [a["title"] for a in body["articles"]]


def totals(accidents, fatal, non_fatal, deaths, injured):
    return {"accidents": accidents, "fatal": fatal, "non_fatal": non_fatal, "deaths": deaths, "injured": injured}


# --- /stats/daily ---------------------------------------------------------

def test_daily_stats_has_one_row_per_day_oldest_first(client, spread):
    assert client.get("/stats/daily").json() == {
        "first_date": "2026-09-30",
        "latest_date": "2026-10-02",
        "days": [
            {"date": "2026-09-30", **totals(1, 1, 0, 2, 1)},
            {"date": "2026-10-01", **totals(2, 1, 1, 0, 7)},
            {"date": "2026-10-02", **totals(3, 2, 1, 6, 2)},
        ],
    }


# --- /stats/states --------------------------------------------------------

def test_state_stats_for_all_time_rank_states_and_set_unknown_aside(client, spread):
    assert client.get("/stats/states").json() == {
        "date": None,
        "month": None,
        "states": [
            {"state": "Bihar", **totals(4, 2, 2, 7, 7)},
            {"state": "Goa", **totals(1, 1, 0, 0, 3)},
        ],
        "unknown": totals(1, 1, 0, 1, 0),
    }


def test_state_stats_for_a_month(client, spread):
    body = client.get("/stats/states", params={"month": "2026-10"}).json()
    assert body["month"] == "2026-10"
    assert body["states"] == [{"state": "Bihar", **totals(3, 1, 2, 5, 6)}, {"state": "Goa", **totals(1, 1, 0, 0, 3)}]
    september = client.get("/stats/states", params={"month": "2026-09"}).json()
    assert september["states"] == [{"state": "Bihar", **totals(1, 1, 0, 2, 1)}]
    assert september["unknown"] == ZERO


def test_state_stats_for_a_day(client, spread):
    body = client.get("/stats/states", params={"date": "2026-10-01"}).json()
    assert body["date"] == "2026-10-01"
    # equal counts fall back to alphabetical order
    assert [s["state"] for s in body["states"]] == ["Bihar", "Goa"]
    assert body["unknown"] == ZERO


def test_state_stats_december_does_not_spill_into_january(client, conn):
    add(conn, date(2026, 12, 31), "https://example.com/dec")
    add(conn, date(2027, 1, 1), "https://example.com/jan")
    conn.commit()
    body = client.get("/stats/states", params={"month": "2026-12"}).json()
    assert body["states"][0]["accidents"] == 1


@pytest.mark.parametrize("path", ["/stats/states", "/articles"])
@pytest.mark.parametrize("params", [
    {"date": "2026-10-01", "month": "2026-10"},
    {"month": "2026-13"},
    {"month": "2026-1"},
    {"month": "October"},
])
def test_bad_scope_is_rejected(client, path, params):
    assert client.get(path, params=params).status_code == 422


# --- /articles filters ----------------------------------------------------

def test_articles_are_newest_day_first_then_fatal_first(client, spread):
    body = client.get("/articles", params={"month": "2026-10"}).json()
    assert titles(body) == ["Accident 6", "Accident 4", "Accident 5", "Accident 3", "Accident 2"]
    assert body["date"] is None
    assert body["totals"] == totals(5, 3, 2, 6, 9)
    assert [a["date"] for a in body["articles"]][-1] == "2026-10-01"


def test_articles_for_a_state_over_all_time(client, spread):
    body = client.get("/articles", params={"state": "Bihar"}).json()
    assert titles(body) == ["Accident 4", "Accident 5", "Accident 2", "Accident 1"]
    assert body["totals"] == totals(4, 2, 2, 7, 7)
    assert body["latest_date"] == "2026-10-02"


def test_articles_for_a_state_in_a_month_or_on_a_day(client, spread):
    month = client.get("/articles", params={"state": "Bihar", "month": "2026-10"}).json()
    assert titles(month) == ["Accident 4", "Accident 5", "Accident 2"]
    day = client.get("/articles", params={"state": "Bihar", "date": "2026-10-01"}).json()
    assert titles(day) == ["Accident 2"]
    assert day["totals"] == totals(1, 0, 1, 0, 4)


def test_articles_with_unknown_state_can_be_listed(client, spread):
    assert titles(client.get("/articles", params={"state": "Unknown"}).json()) == ["Accident 6"]


def test_severity_narrows_the_list_but_not_the_totals(client, spread):
    fatal = client.get("/articles", params={"state": "Bihar", "severity": "fatal"}).json()
    assert titles(fatal) == ["Accident 4", "Accident 1"]
    non_fatal = client.get("/articles", params={"state": "Bihar", "severity": "non-fatal"}).json()
    assert titles(non_fatal) == ["Accident 5", "Accident 2"]
    assert fatal["totals"] == non_fatal["totals"] == totals(4, 2, 2, 7, 7)


def test_limit_and_offset_page_through_the_list(client, spread):
    first = client.get("/articles", params={"state": "Bihar", "limit": 3}).json()
    rest = client.get("/articles", params={"state": "Bihar", "limit": 3, "offset": 3}).json()
    assert titles(first) == ["Accident 4", "Accident 5", "Accident 2"]
    assert titles(rest) == ["Accident 1"]
    assert first["totals"] == rest["totals"] == totals(4, 2, 2, 7, 7)


@pytest.mark.parametrize("params", [
    {"state": "Atlantis"},
    {"state": "bihar"},
    {"severity": "unknown"},
    {"limit": 0},
    {"limit": 501},
    {"offset": -1},
])
def test_bad_article_filters_are_rejected(client, params):
    assert client.get("/articles", params=params).status_code == 422


def test_dates_lists_days_with_data_newest_first(client, two_days):
    assert client.get("/dates").json() == {"dates": ["2026-10-02", "2026-10-01"]}


def test_cors_origins_are_read_from_a_comma_separated_env_value():
    assert api.parse_origins("https://a.example, https://b.example/ ,") == ["https://a.example", "https://b.example"]
    assert api.parse_origins("") == []
    assert api.parse_origins(None) == []


def test_allowed_origin_gets_cors_header(client, monkeypatch):
    origin = api.ALLOWED_ORIGINS[0] if api.ALLOWED_ORIGINS else None
    if origin is None:
        pytest.skip("CORS_ORIGINS not set in this environment")
    response = client.get("/health", headers={"Origin": origin})
    assert response.headers["access-control-allow-origin"] == origin
    other = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in other.headers


# --- /cron/fetch ----------------------------------------------------------

@pytest.fixture
def fetch_job(monkeypatch):
    """Stub the pipeline so the endpoint can be called without the network."""
    import fetch
    import run_pipeline

    calls = {}

    def run(conn, articles, deadline=None, **kwargs):
        calls["articles"] = articles
        calls["deadline"] = deadline
        return run_pipeline.Counter(fetched=len(articles), inserted=1, deferred=1)

    monkeypatch.setenv("CRON_SECRET", "s3cret-for-tests")
    monkeypatch.setattr(fetch, "fetch_articles", lambda: [{"title": "a"}, {"title": "b"}])
    monkeypatch.setattr(run_pipeline, "run", run)
    return calls


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "s3cret-for-tests"}])
def test_fetch_job_refuses_callers_without_the_secret(client, fetch_job, headers):
    assert client.get("/cron/fetch", headers=headers).status_code == 401
    assert fetch_job == {}


def test_fetch_job_is_closed_when_no_secret_is_configured(client, fetch_job, monkeypatch):
    monkeypatch.delenv("CRON_SECRET")
    assert client.get("/cron/fetch", headers={"Authorization": "Bearer "}).status_code == 401
    assert fetch_job == {}


def test_fetch_job_runs_the_pipeline_with_a_deadline_and_reports_counts(client, fetch_job):
    response = client.get("/cron/fetch", headers={"Authorization": "Bearer s3cret-for-tests"})
    assert response.status_code == 200
    body = response.json()
    assert (body["fetched"], body["inserted"], body["deferred"], body["error"]) == (2, 1, 1, 0)
    assert len(fetch_job["articles"]) == 2
    assert fetch_job["deadline"] is not None


def test_fetch_job_reports_an_empty_feed_as_a_failure(client, fetch_job, monkeypatch):
    import fetch
    monkeypatch.setattr(fetch, "fetch_articles", lambda: [])
    assert client.get("/cron/fetch", headers={"Authorization": "Bearer s3cret-for-tests"}).status_code == 502
