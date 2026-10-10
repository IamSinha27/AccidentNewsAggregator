"""
api.py
HTTP API over the articles table, for the Next.js frontend. Read-only apart
from /cron/fetch, which runs the pipeline for hosts that trigger it by URL.

    uvicorn api:app

GET /stats/daily    totals for every day that has data, oldest first
GET /stats/states   totals per state for a day (?date=), a month (?month=) or all time
GET /stats/vehicles totals per vehicle type for a day, a month or all time, optionally one ?state=
GET /articles       article list + totals for a day, a month and/or a state
                    (default: latest day with data); ?vehicle= ?severity= ?limit= ?offset=
GET /dates          days that have data, newest first (superseded by /stats/daily)
GET /health
GET /cron/fetch     run one fetch; needs "Authorization: Bearer $CRON_SECRET"
"""

import datetime
import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from typing import Literal, Optional

import psycopg
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import db
from extract import INDIAN_STATES_UTS, VEHICLE_TYPES

STATES = set(INDIAN_STATES_UTS) | {"Unknown"}

# The five numbers every view shows, as SELECT columns and as response keys.
TOTALS_SQL = """count(*),
    count(*) FILTER (WHERE severity = 'fatal'),
    count(*) FILTER (WHERE severity = 'non-fatal'),
    coalesce(sum(deaths), 0),
    coalesce(sum(injured), 0)"""
TOTALS_KEYS = ("accidents", "fatal", "non_fatal", "deaths", "injured")

ARTICLE_KEYS = ("id", "date", "title", "severity", "deaths", "injured", "vehicles", "state", "link", "source")

# How long /cron/fetch keeps starting new articles. Vercel ends a request at
# 300 seconds; stopping at 240 leaves room for the articles already in flight.
FETCH_BUDGET_SECONDS = 240

DATE_PARAM = Query(None, alias="date", description="YYYY-MM-DD")
MONTH_PARAM = Query(None, pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM; not together with date")


def parse_origins(value: Optional[str]) -> list:
    """Split the comma-separated CORS_ORIGINS value. A trailing slash is
    dropped because browsers send the Origin header without one."""
    return [o.strip().rstrip("/") for o in (value or "").split(",") if o.strip()]


ALLOWED_ORIGINS = parse_origins(os.environ.get("CORS_ORIGINS"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # A fresh database (before the first cron run) should answer with an
    # empty list, not a missing-table error.
    conn = db.connect()
    try:
        db.init_schema(conn)
    finally:
        conn.close()
    yield


app = FastAPI(title="Indian Traffic Accident News", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_methods=["GET"])


def get_conn():
    """One connection per request."""
    conn = db.connect()
    try:
        yield conn
    finally:
        conn.close()


def _latest_date(conn: psycopg.Connection) -> Optional[datetime.date]:
    return conn.execute("SELECT max(date) FROM articles").fetchone()[0]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/dates")
def dates(conn: psycopg.Connection = Depends(get_conn)):
    rows = conn.execute("SELECT DISTINCT date FROM articles ORDER BY date DESC").fetchall()
    return {"dates": [row[0] for row in rows]}


def _scope(day: Optional[datetime.date], month: Optional[str], state: Optional[str] = None, vehicle: Optional[str] = None):
    """WHERE clause and its parameters for a day or a month, optionally
    narrowed to one state and/or one vehicle type. With nothing given it is
    empty: all time."""
    if day and month:
        raise HTTPException(422, "give either date or month, not both")
    if state is not None and state not in STATES:
        raise HTTPException(422, f"unknown state: {state}")
    if vehicle is not None and vehicle not in VEHICLE_TYPES:
        raise HTTPException(422, f"unknown vehicle: {vehicle}")
    clauses, params = [], []
    if day:
        clauses.append("date = %s")
        params.append(day)
    if month:
        # A range rather than to_char(date) = ..., so the date index is used.
        first = datetime.date(int(month[:4]), int(month[5:]), 1)
        next_first = (first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        clauses.append("date >= %s AND date < %s")
        params += [first, next_first]
    if state is not None:
        clauses.append("state = %s")
        params.append(state)
    if vehicle is not None:
        clauses.append("%s = ANY(vehicles)")
        params.append(vehicle)
    return ("WHERE " + " AND ".join(clauses) if clauses else ""), params


def _totals(row) -> dict:
    return dict(zip(TOTALS_KEYS, row))


@app.get("/stats/daily")
def stats_daily(conn: psycopg.Connection = Depends(get_conn)):
    rows = conn.execute(f"SELECT date, {TOTALS_SQL} FROM articles GROUP BY date ORDER BY date").fetchall()
    days = [{"date": row[0], **_totals(row[1:])} for row in rows]
    return {
        "first_date": days[0]["date"] if days else None,
        "latest_date": days[-1]["date"] if days else None,
        "days": days,
    }


@app.get("/stats/states")
def stats_states(
    day: Optional[datetime.date] = DATE_PARAM,
    month: Optional[str] = MONTH_PARAM,
    conn: psycopg.Connection = Depends(get_conn),
):
    where, params = _scope(day, month)
    rows = conn.execute(
        f"""
        SELECT coalesce(state, 'Unknown') AS name, {TOTALS_SQL}
        FROM articles {where}
        GROUP BY name
        ORDER BY count(*) DESC, name
        """,
        params,
    ).fetchall()
    # Unlocated accidents can't go on the map; they're reported on their own.
    states = [{"state": row[0], **_totals(row[1:])} for row in rows if row[0] != "Unknown"]
    unknown = next((_totals(row[1:]) for row in rows if row[0] == "Unknown"), _totals((0,) * len(TOTALS_KEYS)))
    return {"date": day, "month": month, "states": states, "unknown": unknown}


@app.get("/stats/vehicles")
def stats_vehicles(
    day: Optional[datetime.date] = DATE_PARAM,
    month: Optional[str] = MONTH_PARAM,
    state: Optional[str] = Query(None, description="a state/UT name, or Unknown"),
    conn: psycopg.Connection = Depends(get_conn),
):
    """Totals per vehicle type for a day, a month or all time, optionally for
    one state. An accident that involves several vehicles counts under each of
    them, so the rows add up to more than the accident total. Accidents with
    no vehicle named are reported on their own."""
    where, params = _scope(day, month, state)
    rows = conn.execute(
        f"""
        SELECT vehicle, {TOTALS_SQL}
        FROM articles, unnest(vehicles) AS vehicle {where}
        GROUP BY vehicle
        ORDER BY count(*) DESC, vehicle
        """,
        params,
    ).fetchall()
    no_vehicle = where + (" AND " if where else "WHERE ") + "cardinality(vehicles) = 0"
    unknown = conn.execute(f"SELECT {TOTALS_SQL} FROM articles {no_vehicle}", params).fetchone()
    return {
        "date": day,
        "month": month,
        "state": state,
        "vehicles": [{"vehicle": row[0], **_totals(row[1:])} for row in rows],
        "unknown": _totals(unknown),
    }


@app.get("/articles")
def articles(
    day: Optional[datetime.date] = Query(None, alias="date", description="YYYY-MM-DD; with no date, month or state: the latest day with data"),
    month: Optional[str] = MONTH_PARAM,
    state: Optional[str] = Query(None, description="a state/UT name, or Unknown; alone it means all time for that state"),
    vehicle: Optional[str] = Query(None, description="a vehicle type; an accident with several vehicles is listed under each"),
    severity: Optional[Literal["fatal", "non-fatal"]] = Query(None, description="narrows the list, not the totals"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: psycopg.Connection = Depends(get_conn),
):
    latest = _latest_date(conn)
    if day is None and month is None and state is None and vehicle is None:
        day = latest
    where, params = _scope(day, month, state, vehicle)

    totals = _totals(conn.execute(f"SELECT {TOTALS_SQL} FROM articles {where}", params).fetchone())
    if severity:
        where += (" AND " if where else "WHERE ") + "severity = %s"
        params = params + [severity]
    rows = conn.execute(
        f"""
        SELECT {", ".join(ARTICLE_KEYS)} FROM articles {where}
        ORDER BY date DESC, (severity = 'fatal') DESC, id DESC
        LIMIT %s OFFSET %s
        """,
        params + [limit, offset],
    ).fetchall()
    return {
        "date": day,
        "latest_date": latest,
        "totals": totals,
        "articles": [dict(zip(ARTICLE_KEYS, row)) for row in rows],
    }


@app.get("/cron/fetch")
def cron_fetch(authorization: Optional[str] = Header(None), conn: psycopg.Connection = Depends(get_conn)):
    """Run the pipeline once, inside this request. Meant for a scheduler that
    calls a URL (Vercel Cron sends the CRON_SECRET as a bearer token). Safe to
    call again: stored and turned-down links are skipped, and whatever a run
    doesn't reach in time is left for the next one."""
    secret = os.environ.get("CRON_SECRET")
    if not secret or not hmac.compare_digest(authorization or "", f"Bearer {secret}"):
        raise HTTPException(401, "missing or wrong cron secret")
    deadline = time.monotonic() + FETCH_BUDGET_SECONDS

    # Imported here so that ordinary API requests don't pay for loading the
    # scraping and LLM libraries on a cold start.
    import run_pipeline
    from fetch import fetch_articles

    # Vercel keeps about 250 log lines per request. A line per HTTP request
    # or per article would push the summary below out of the log.
    logging.getLogger("httpx").setLevel(logging.WARNING)

    articles = fetch_articles()
    if not articles:
        raise HTTPException(502, "RSS fetch returned no articles")
    counts = run_pipeline.run(conn, articles, deadline=deadline, quiet=True)
    summary = {name: counts[name] for name in run_pipeline.OUTCOMES}
    print(f"cron_fetch: {summary}", flush=True)
    return summary
