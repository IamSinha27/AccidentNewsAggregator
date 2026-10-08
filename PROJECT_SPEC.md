# Indian Traffic Accident News Aggregator

Describes the system as built. Last updated 8 October 2026.

## 1. Goal

A daily-refreshing dashboard of Indian road-accident news. Once a day the pipeline collects that day's articles, an LLM pulls structured fields out of each one, and the result is stored in Postgres and shown on a web page.

## 2. Status

| Part | State |
|---|---|
| Pipeline (fetch → resolve → scrape → extract → dedup → store) | Built and tested |
| Database schema | Built; reworked on 8 Oct 2026 (see §8) |
| API | Built: totals per day and per state, and article lists by day, month and state (see §10) |
| Frontend | Built from the mockup in `mock_ui/index.html`: overview, day view and state view (see §10) |

**Deployed** on Vercel (dashboard and API) with a Neon database; see §12.

**Not yet done:** a check of the phone layout.

## 3. Architecture

```
Daily cron (Render, 18:00 UTC = 23:30 IST)
  → fetch Google News RSS, one query per state/UT plus "India" (last 24h)
  → resolve each Google redirect link → real publisher URL
  → skip links already stored or already turned down
  → scrape the publisher page → article body text
  → LLM (OpenAI gpt-4o-mini) → relevance flags + structured fields
  → drop anything that isn't a recent Indian road accident
  → drop a second report of an accident that is already stored
  → insert
  → Postgres (Render)
  ↕
FastAPI backend (Render), read-only
  ↕
Next.js frontend (Vercel)
```

## 4. Repository layout

```
backend/
  fetch.py              Google News RSS → raw candidate articles
  fetch_body.py         resolve Google redirect; scrape article body
  extract.py            LLM prompt, the fixed lists, cleanup of the LLM's answer
  store.py              dedup + insert; memory of turned-down links
  run_pipeline.py       cron entrypoint that strings the steps together
  api.py                FastAPI app
  main.py               entry point for Vercel (re-exports the app)
  vercel.json           Vercel: framework and the fetch schedule
  db.py                 connection + schema bootstrap
  schema.sql            tables, constraints, and upgrades of older tables
  backfill_injured.py   one-off: fill injured for rows that predate the column
  backfill_vehicles.py  one-off: convert old free-text vehicle_type, then drop it
  tests/                pytest suite (see §11)
frontend/               Next.js 16 app: the dashboard (see §10)
mock_ui/index.html      the design mockup the UI was built from (a bundled export; open in a browser)
docker-compose.yml      three containers: db, backend (API + fetch job) and frontend
render.yaml             Render blueprint: Postgres, API web service, cron job
backups/                local pg_dump files taken before schema changes (untracked)
```

## 5. Data source: Google News RSS

Endpoint: `https://news.google.com/rss/search`, with `q` (search terms, supports `AND`/`OR` and `when:1d`), `hl=en-IN`, `gl=IN`, `ceid=IN:en`.

Things learned by testing, all still true:

- **`gl`/`ceid`/`hl` are a bias, not a geo filter.** An unscoped query returns mostly non-India stories. The fetch therefore runs the accident query once per state/UT, with the name as a required phrase, plus once for "India": 37 requests per run. Results are merged and de-duplicated. The states can't be OR-ed into one query, because Google ignores terms past a length limit, which silently drops the `when:` filter.
- **Relevance is still judged by the LLM**, not by the fetch (§7).
- **The RSS `link` is a Google redirect**, not the article URL. It has to be resolved separately.
- **The RSS snippet is usually just the title again.** It is only a fallback when scraping fails.
- **`when:1d` filters by when Google indexed the article**, not when the accident happened. The LLM's `is_recent_accident` flag handles that difference.

## 6. Pipeline (`run_pipeline.py`)

```
python run_pipeline.py [--dry-run] [--limit N] [--workers N]
```

1. **Fetch** (`fetch.py`): returns raw candidates: title, Google link, published time, source, snippet. No filtering.
2. **Resolve** (`fetch_body.resolve_url`): the `googlenewsdecoder` package turns the redirect into the publisher URL. Needs a live round-trip to Google. On failure the article is kept, with the Google link and title-only extraction.
3. **Skip known links** (`store.link_known`): a link that is already stored, or was turned down in the last 7 days (`seen_links`), is counted as `duplicate` before any scrape or LLM call, so reruns cost nothing.
4. **Scrape** (`fetch_body.get_article_text`): `trafilatura` extracts clean body text, capped at 3000 characters. Returns nothing on a paywall, block or dead link.
5. **Extract** (`extract.extract_fields`): one LLM call per article (§7).
6. **Decide and store** (`store.save_article`): relevance check, dedup, insert (§9).

Steps 2, 4 and 5 are network-bound and run on a thread pool (8 workers by default). Everything that touches the database stays on one thread, in feed order, because the same-event check depends on which article was stored first.

Each article ends with exactly one outcome: `inserted`, `duplicate`, `same-event`, `rejected-not-india`, `rejected-not-recent`, `extraction-failed` or `error`. A run given a deadline (`run(..., deadline=)`, used by `/cron/fetch`) also counts `deferred`: articles it did not reach in time, about which nothing is remembered, so the next run takes them. One bad article never aborts the run. The exit code is non-zero only if the database is unreachable or the RSS fetch returns nothing.

`--dry-run` goes through every step inside one transaction and rolls it back.

## 7. LLM extraction (`extract.py`)

One call to `gpt-4o-mini` per article both judges relevance and extracts the fields.

**Why an LLM and not regex rules:** rules are brittle, need constant maintenance (keyword lists, city-to-state tables), and give no reliable confidence signal. A rule can match the wrong word and still report success.

**The model returns JSON with exactly these seven keys:**

```json
{
  "is_india_traffic_accident": true,
  "is_recent_accident": true,
  "severity": "fatal",
  "deaths": 3,
  "injured": 5,
  "vehicles": ["Car", "Truck"],
  "state": "Uttar Pradesh"
}
```

| Key | Meaning |
|---|---|
| `is_india_traffic_accident` | False for another country, or for something that isn't a road accident (a stock market "crash") |
| `is_recent_accident` | True only if the accident itself happened in roughly the last 24–48 hours. False for an old accident back in the news through a verdict, compensation award, arrest or anniversary |
| `severity` | `"fatal"` if the article says at least one person died. Otherwise `"non-fatal"`, which covers both "nobody died" and "the article doesn't say" |
| `deaths` | Number killed. 0 if nobody died or no number is given |
| `injured` | Number injured, not counting the dead. 0 if nobody was injured or no number is given |
| `vehicles` | List of the vehicle types involved, from the fixed list below. Empty if none is known |
| `state` | A name from the fixed list below, or `"Unknown"` |

An article is stored only if both flags are true.

**Fixed lists** (both defined in `extract.py` and inserted into the prompt):

- `VEHICLE_TYPES`, 7 names: Auto-rickshaw, Bus, Car, Tractor, Truck, Two-wheeler, Van.
- `INDIAN_STATES_UTS`, 36 names: the 28 states and 8 union territories.

**Who does what for vehicles:**

- The **LLM** translates real-world wording into the seven categories. The prompt gives hints: motorcycle/scooter/bike → Two-wheeler; SUV/MUV/jeep → Car; lorry/dumper/tanker/trailer/container → Truck; pickup/tempo/ambulance/school van → Van; e-rickshaw → Auto-rickshaw; tractor-trolley → Tractor; mini-bus/school bus → Bus. Anything that fits none (a train, a pedestrian) is left out.
- The **code** does not translate. `normalise_vehicles` only keeps names that are in the list (ignoring capitalisation), removes repeats and sorts alphabetically. An out-of-list name is dropped, not converted.

**Cleanup of the counts** (`normalise_casualties`): a stated death toll always makes the article fatal; any severity other than "fatal" becomes "non-fatal"; a count that isn't a plain number ("several", null) becomes 0.

**Model behaviour to know about:**

- It sometimes wraps the JSON in markdown fences despite being told not to; the code strips them.
- `max_tokens` is 400 so a stray preamble can't truncate the JSON.
- Every failure path logs its reason to stderr (API error, unparseable JSON with the raw text, missing keys) and returns nothing; the pipeline counts it as `extraction-failed` and will retry it on the next run.

## 8. Database (`schema.sql`)

```sql
CREATE TABLE articles (
    id          SERIAL PRIMARY KEY,
    date        DATE NOT NULL,           -- published date in IST, not the accident date
    title       TEXT NOT NULL,
    link        TEXT UNIQUE NOT NULL,    -- resolved publisher URL
    source      TEXT,                    -- outlet name
    severity    TEXT NOT NULL,           -- 'fatal' | 'non-fatal'
    deaths      INT NOT NULL DEFAULT 0,
    injured     INT NOT NULL DEFAULT 0,
    vehicles    TEXT[] NOT NULL DEFAULT '{}',
    state       TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE seen_links (                -- links looked at and turned down
    link     TEXT PRIMARY KEY,
    outcome  TEXT NOT NULL,
    seen_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Indexes: `articles (date)`, `articles (date, state)` for the dedup lookup, `articles (state, date)` for one state's article list, `seen_links (seen_at)` for pruning.

**Rules the database enforces:**

- `severity` is `'fatal'` or `'non-fatal'`.
- `deaths` and `injured` are not negative.
- `deaths` is 0 unless `severity` is `'fatal'`.
- `vehicles` contains only the seven names. This list is repeated from `extract.VEHICLE_TYPES`; adding a category means changing both, and altering the constraint on existing databases.

**How to read the values:**

| Value | Meaning | Suggested display |
|---|---|---|
| `fatal`, `deaths = 3` | Three stated dead | Fatal · 3 dead |
| `fatal`, `deaths = 0` | Fatal, toll not stated | Fatal · toll unknown |
| `non-fatal` | No one died, or unclear | Non-fatal |
| `injured = 0` | Nobody hurt, or no number stated; the two can't be told apart | Show no injury text |
| `vehicles = {}` | No known vehicle | Unknown |
| `state = 'Unknown'` | Could not be determined | Excluded from the map |

The words "Unknown" and the " / " between vehicles are added by the UI. The database stores neither for vehicles.

**Upgrading an older database.** `schema.sql` is run on every API start and pipeline run (`db.init_schema`) and upgrades older tables in place:

- A table with the old free-text `fatality` column gets `severity` and `deaths` derived from it by SQL, and `fatality` is dropped.
- A table with the old free-text `vehicle_type` column gets an empty `vehicles` column. The old column stays until `backfill_vehicles.py` is run.

Two one-off scripts then fill what SQL can't. Neither scrapes anything.

- `python backfill_vehicles.py`: splits each stored description into individual vehicle names, asks the LLM for the category of each distinct name, writes `vehicles`, drops `vehicle_type`.
- `python backfill_injured.py`: asks the LLM for an injured count from the stored headline only. Rows whose headline doesn't state one stay at 0.

Both have been run on the local database. A deployed database needs each run once.

## 9. Deduplication (`store.py`)

Two separate problems:

1. **The same article again** (a cron rerun, or one URL returned by two regional queries). Caught by the link check: the URL is already in `articles` or `seen_links`. Backed by the `UNIQUE` constraint on `link`.
2. **The same accident from another outlet.** An existing row counts as the same event if all of these hold:
   - same `date` and same `state` (never applied when the state is "Unknown");
   - the same set of `vehicles`;
   - the same `severity`;
   - a compatible death toll: within 1 of each other, or either one not stated.

   The later article is discarded and the first one stored stays. One link per accident is enough. Its URL goes into `seen_links` so later runs skip it.

`injured` is deliberately not compared: injury counts differ too much between outlets.

The same-event match is a heuristic and accepted as imperfect. It can discard an unrelated accident with the same state and vehicles on a busy day, including two unrelated accidents that both have no known vehicle. It can let the same accident through twice when outlets name different vehicle types.

`seen_links` is pruned after 7 days; the feed only reaches back one day, so older links never return.

## 10. API (`api.py`) and frontend

Read-only FastAPI app. CORS origins come from the `CORS_ORIGINS` environment variable.

| Endpoint | Returns |
|---|---|
| `GET /stats/daily` | Totals for every day that has data, oldest first |
| `GET /stats/states` | Totals per state for a day, a month or all time |
| `GET /articles` | An article list with its totals, for a day, a month and/or a state |
| `GET /dates` | Days that have data, newest first. Superseded by `/stats/daily`; no longer used by the frontend |
| `GET /health` | `{"status": "ok"}` |
| `GET /cron/fetch` | Runs one fetch inside the request and returns the outcome counts. Requires `Authorization: Bearer $CRON_SECRET` |

"Totals" always means the same five numbers: `accidents`, `fatal`, `non_fatal`, `deaths`, `injured`.

**`GET /stats/daily`** takes no parameters. About 365 rows a year, so the UI fetches it once and derives month totals, day-on-day changes, the month and day pickers and previous/next day from it.

```json
{
  "first_date": "2026-10-01",
  "latest_date": "2026-10-07",
  "days": [{"date": "2026-10-01", "accidents": 45, "fatal": 30, "non_fatal": 15, "deaths": 70, "injured": 90}]
}
```

**`GET /stats/states`** takes `?date=YYYY-MM-DD` or `?month=YYYY-MM` (not both); with neither it covers all time. `states` lists only states with at least one accident, most accidents first. Accidents with no known state can't go on the map and are reported separately in `unknown`.

```json
{
  "date": null,
  "month": "2026-10",
  "states": [{"state": "Maharashtra", "accidents": 60, "fatal": 37, "non_fatal": 23, "deaths": 125, "injured": 339}],
  "unknown": {"accidents": 10, "fatal": 6, "non_fatal": 4, "deaths": 9, "injured": 12}
}
```

**`GET /articles`** parameters, all optional:

| Parameter | Meaning |
|---|---|
| `date` | One day |
| `month` | `YYYY-MM`; not together with `date` |
| `state` | A name from `INDIAN_STATES_UTS`, or `Unknown`. On its own it means all time for that state |
| `severity` | `fatal` or `non-fatal`. Narrows the list only, not `totals` |
| `limit`, `offset` | Paging. Default limit 50, maximum 500 |

With no `date`, `month` or `state`, it returns the latest day that has data.

```json
{
  "date": "2026-10-07",
  "latest_date": "2026-10-07",
  "totals": {"accidents": 56, "fatal": 30, "non_fatal": 26, "deaths": 83, "injured": 86},
  "articles": [{"id": 495, "date": "2026-10-07", "title": "...", "severity": "fatal", "deaths": 1, "injured": 4,
                "vehicles": ["Car"], "state": "Andhra Pradesh", "link": "...", "source": "The Hindu"}]
}
```

- `totals` covers the whole date/month/state scope and ignores `severity` and paging. It supplies the stat tiles, the counts on the severity filter, and how many rows exist in total.
- `date` in the response is null when the request was for a month or a state.
- Order: newest day first, then fatal before non-fatal, then newest `id`.

A bad parameter (malformed month, both `date` and `month`, an unrecognised state, a limit out of range) returns 422.

### Frontend

`frontend/` is a Next.js 16 app (React 19, Tailwind 4) with one page and three views. The view and everything selected in it live in the URL, so any view can be linked to and the back button works.

| URL | View |
|---|---|
| `/` | Overview: latest day's totals, accidents over time, and the state map, for the latest month |
| `/?month=2026-09` | Overview for another month |
| `/?scope=day&day=2026-10-07` | Overview with the state map narrowed to one day |
| `/?scope=all` | Overview with the state map over all time |
| `/?date=2026-10-07` | Day view: that day's totals, a strip to jump to another day, and its articles |
| `/?state=Goa` plus the same `month` / `scope` / `day` | State view: that state's totals and articles for the chosen period |
| `&severity=fatal` or `non-fatal` | Narrows the article list in the day and state views |

How it is put together:

- **Data is fetched on the server** (`lib/api.ts`, using `API_URL`). The browser never calls the API. The first request is allowed 90 seconds, because Render's free tier sleeps when idle; `app/error.tsx` shows a retry message if it still fails.
- **`/stats/daily` is fetched on every view.** Month totals, day-on-day changes, the month and day pickers and previous/next day are all derived from it (`lib/dates.ts`).
- **Things that change the data are links** (month, period, day, state, severity). Things that only change how loaded data is shown are browser state: the Accidents/Deaths toggle, the selected state, "show all", and the hover note on the chart.
- **Files:** `app/page.tsx` picks the view; `overview.tsx`, `day-view.tsx` and `state-view.tsx` are the views; `time-chart.tsx`, `state-map.tsx` and `article-table.tsx` are the interactive parts; `ui.tsx` holds shared pieces; `lib/urls.ts` defines the URL scheme; `lib/india-map.ts` holds the map outlines taken from the mockup.

Differences from the mockup:

- **Two severities, not three.** Bars, legend and filter have fatal and non-fatal only.
- **The "Today" card is labelled "Latest"**, since it shows the latest day with data, which is not always today. It also has a direct link to that day's articles.
- **The fatality pill** reads "Fatal · 3 dead", "Fatal · toll unknown", "Non-fatal · 5 injured" or "Non-fatal".
- **A list longer than 500 articles** shows only the newest 500 and says so. Only a state's all-time list can get that long.
- **The footnote under the map** gives the real number of accidents left out for having no known state.

## 11. Tests

Run from `backend/`.

| Command | What runs |
|---|---|
| `pytest` | 124 tests, about 2 seconds, no LLM calls. Needs a local Postgres database named `accident_news_test` (or `TEST_DATABASE_URL`) |
| `pytest -m llm` | 29 live tests through the real prompt, about 50 seconds. Needs `OPENAI_API_KEY`; costs well under a cent |

The live tests (`tests/test_extract_llm.py`) check that the LLM maps wording to the fixed fields: one case per vehicle hint, multi-vehicle cases, things outside the list, and the severity and count combinations. They are excluded from a plain `pytest` by `pytest.ini`. The model isn't deterministic, so a one-off failure can be noise; a case that fails repeatedly means the prompt needs another hint.

## 12. Running and deploying

**Local.** Copy `backend/.env.example` to `backend/.env` and set `OPENAI_API_KEY`, `DATABASE_URL` and `CORS_ORIGINS`. Then, from `backend/`:

```
python run_pipeline.py --dry-run --limit 10   # try the pipeline without writing
python run_pipeline.py                        # a real run
uvicorn api:app                               # the API on :8000
```

From `frontend/`, set `API_URL` (see `.env.example`) and run `npm run dev`.

**In containers.** `docker compose up --build` starts three services: `db`, `backend` and `frontend`. The fetch job is part of the backend service: `docker compose exec backend python run_pipeline.py` runs it inside the running backend container, using `OPENAI_API_KEY` from `backend/.env`. `frontend/Dockerfile` builds the dashboard's standalone production server. The README has the details.

**Deployed (Vercel + Neon).** Live at https://accident-news-phi.vercel.app, API at https://accident-news-api.vercel.app.

- **Two Vercel projects** on the Hobby plan, both connected to the GitHub repository: `accident-news` with root directory `frontend/` and `accident-news-api` with root directory `backend/`. A push to `main` deploys both to production; other branches get preview deployments.
- **Each folder has a `vercel.json` naming its framework** (`nextjs`, `fastapi`). The projects were created empty, so Vercel did not detect it.
- **`backend/main.py`** re-exports the app from `api.py`; Vercel only looks for a FastAPI app in a few fixed file names. A `pyproject.toml` entry point was tried first and failed the build, because Vercel then expects a full `[project]` table.
- **`backend/.vercelignore`** keeps `.env`, `.venv` and the tests out of a deployment made with the CLI from that folder, where the repo's root `.gitignore` does not apply. Deployments from GitHub only ever contain committed files.
- **Database:** Neon Postgres (`accident-news-db`, US East), added through the Vercel Marketplace, which injects `DATABASE_URL` and related variables into the API project. Seeded on 9 Oct 2026 with the 536 local articles and the remembered links.
- **Secrets in the API project:** `OPENAI_API_KEY` and `CRON_SECRET`. The frontend project has `API_URL`.
- **Fetch job:** Vercel Cron calls `GET /cron/fetch` at 06:00, 12:00 and 18:00 UTC (each up to an hour late on Hobby). Hobby allows each cron entry once a day and ends a request at 300 seconds, so the endpoint stops starting articles after 240 seconds (`FETCH_BUDGET_SECONDS`) and the three runs cover for each other. `vercel crons run /cron/fetch` triggers one by hand.
- `render.yaml` is from an earlier Render plan and is unused.

**Environment gotchas:**

- `googlenewsdecoder` and `trafilatura` need unrestricted outbound network access.
- `googlenewsdecoder` 0.2.1 breaks with `selectolax` 1.0, which a fresh install picks by default; `requirements.txt` pins `selectolax` to 0.4.13.
- `load_dotenv()` does not override a variable already exported in the shell, so a stale exported key wins over `.env`.
- Render's free Postgres expires 30 days after creation.

## 13. Design decisions

- **Published date, not accident date.** `date` is the article's published date in Indian time. Using the accident date would let a late report change a day that has already been viewed. The dashboard's "today" therefore means "reported today".
- **Default view is the latest day with data**, not the calendar day, so the page is never empty before the cron has run.
- **Two severities, no "unknown".** An article that doesn't say whether anyone died is stored as non-fatal. Simpler everywhere, at the cost of a slight undercount of fatal accidents (about 5% of articles were unclear when this was decided).
- **0 means "not stated" for the counts.** No NULLs to handle. Death and injury totals are therefore lower bounds.
- **A fixed vehicle list instead of free text.** Free text produced 89 distinct descriptions in 466 rows, which made counting by vehicle impossible and weakened dedup. Pedestrians and anything outside the seven categories are not recorded.
- **`vehicles` is an array column**, not two columns or a link table. It handles any number of vehicles and keeps "accidents involving a bus" a one-line filter.
- **One row per accident, one link per row.** A second outlet's report is discarded, not merged in. (An earlier design kept extra outlets in a `sources` column; that was dropped.)
- **No publish time is stored.** Articles within a day are ordered by `id`.
- **"India accident" means where it happened**, not the nationality of the people involved.

## 14. Known gaps

- **Duplicates inflate the totals.** The same accident is sometimes stored more than once (in the 1–7 October data, one Ramban bus accident appears under several outlets). Death and injury totals count each copy. See §9 for why the same-event check misses these.

- **Several accidents in one article.** One article yields one row; a report that bundles two accidents is not split.
- **Injury counts for 1–7 October 2026** came from headlines only, so they are an undercount (147 of 466 articles have one).
- **Occurrence date is not extracted.** Charts by the day an accident happened would need a new LLM field.
