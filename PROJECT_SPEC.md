# Indian Traffic Accident News Aggregator — Build Spec

## 1. Goal

A daily-refreshing dashboard that aggregates Indian traffic/road-accident news.

Every day, aggregate news articles covering traffic accidents in India. For each day, show a table of all qualifying articles with these columns:

| Title | Fatality | Vehicle type | State | Article link |
|---|---|---|---|---|

The user can change the date via a date picker and view the table for that date. On first visit (no date selected), the dashboard shows the **most recent date that has data** — not strictly "today" — so it's never an empty table if the daily cron hasn't run yet that day.

**Table is exactly these 5 columns, Title first.** No injury count. `source` is stored in the DB but not displayed as its own column.

## 2. Architecture

```
Daily cron (Render) 
  → fetch Google News RSS (last 24h, India-scoped keyword search)
  → for each article:
      resolve Google's redirect link → real publisher URL
      scrape publisher URL → clean article body text
      send to LLM (OpenAI gpt-4o-mini) → structured fields + relevance/recency flags
      filter out anything not a real, recent India traffic accident
      dedup against existing DB rows (exact link match, and same-event-different-outlet match)
      insert (or merge into existing row)
  → Postgres (Render)
  ↕
FastAPI backend (Render) — serves /articles?date=YYYY-MM-DD and "most recent date with data"
  ↕
Next.js frontend (Vercel) — date picker + table
```

Deployment target: **Vercel** (frontend), **Render** (Postgres + backend API + the daily cron job).

## 3. Data source: Google News RSS

Endpoint: `https://news.google.com/rss/search`

Query params:
- `q` — search terms. Supports basic boolean (`AND`/`OR`), `site:`, and `when:` (recency filter, e.g. `when:1d`).
- `hl` — interface language, e.g. `en-IN`.
- `gl` — country bias, e.g. `IN`.
- `ceid` — combined edition id, `country:language`, e.g. `IN:en`.

**Important, confirmed-by-testing caveats:**
- `gl`/`ceid`/`hl` are a **bias**, not a geo filter. Live testing repeatedly returned non-India stories (Iran, Nepal, Kyrgyzstan, Afghanistan, US local news) in a feed scoped to `gl=IN&ceid=IN:en`. **Do not rely on these params for geo-filtering** — that's what the LLM's `is_india_traffic_accident` field is for (see §5).
- The RSS `link` field is **not** the real article URL — it's an opaque Google redirect (`news.google.com/rss/articles/CBMi...`) that must be resolved separately (see §4, step 2).
- The RSS `summary`/snippet field is usually just an HTML-wrapped duplicate of the title, not real excerpt text. Don't rely on it for extraction when body text is available — only use it as a last-resort fallback if scraping fails.

Recency filter: `when:1d` is applied on every fetch, matched to a daily cron cadence. This filters by **Google's indexed/published time**, not necessarily the time the accident happened — that distinction is handled separately by the LLM's `is_recent_accident` field.

## 4. Pipeline steps (already built and tested — see §9 for full code)

### Step 1 — Fetch (`fetch.py`)
Builds the RSS URL and parses it with `feedparser`. Returns raw candidate articles (title, Google redirect link, published date, source, snippet). **Does no filtering** — every article is passed downstream for the LLM to judge. Tested live: works correctly, reproduces the known `gl=IN` bias issue described above.

### Step 2 — Resolve redirect (`fetch_body.py::resolve_url`)
Uses the `googlenewsdecoder` PyPI package to turn the Google redirect link into the real publisher URL. This requires a live round-trip to Google's servers (the old base64-offline-decode trick no longer works — Google changed the token format). Returns `None` on failure rather than raising.

### Step 3 — Scrape body (`fetch_body.py::get_article_text`)
Uses `trafilatura` to fetch the resolved URL and extract clean body text (strips nav/ads/boilerplate). Returns `None` on failure (paywall, bot-block, dead link) rather than raising. Capped at 3000 chars by default.

Both steps 2 and 3 require real outbound network access — they will not work in a network-sandboxed CI environment. (This was validated on a real unrestricted network — see §10.)

### Step 4 — Extract (`extract.py::extract_fields`)
One LLM call per article (OpenAI `gpt-4o-mini`) that both judges relevance/recency **and** extracts the structured fields in a single pass — see §5 for the exact schema and reasoning.

## 5. LLM extraction: schema, prompt, and reasoning

**Why a single LLM call instead of regex/keyword rules:** regex is brittle, requires constant hardcoded maintenance (keyword lists, city→state mappings), and — critically — gives no reliable confidence signal: a rule can match the wrong word and report "confident" anyway, silently producing wrong data with no way to detect the error. An LLM call per article is simpler, more accurate, and cheap enough at this volume.

**Required output schema** (JSON, exactly these 5 keys):

```json
{
  "is_india_traffic_accident": true,
  "is_recent_accident": true,
  "fatality": "Yes (3 dead)",
  "vehicle_type": "Car",
  "state": "Uttar Pradesh"
}
```

- `is_india_traffic_accident` (bool) — false if this is not an Indian road/traffic accident at all (wrong country, or not a traffic accident — e.g. a stock market "crash", an app "crash").
- `is_recent_accident` (bool) — **true only if the accident itself occurred roughly within the last 24–48 hours** and is the actual news. **false** if the accident happened much earlier (weeks/months/years ago) and the article is really about something else that happened *around* it more recently — a court verdict, a compensation award, an arrest, an appeal, an anniversary retrospective, a policy response, etc. Rule of thumb for the model: look at what the headline is actually announcing — a court awarding money over a "2018 crash" is news about the court, not about a crash that just happened. **This was validated live**: correctly returned `false` for a tribunal-compensation article about a 2018 crash, and `true` for a same-day crash report.
- `fatality` — one of `"Yes (N dead)"` (fill in the number if stated), `"Yes"` (fatal, no count given), `"No (injuries only)"`, or `"Unknown"`.
- `vehicle_type` — the vehicle(s) involved, e.g. `"Bus"`, `"Truck / Car"`, `"Two-wheeler"`, `"Auto-rickshaw"`, `"Pedestrian (no vehicle specified)"`, or `"Unknown"`.
- `state` — the Indian state the accident occurred in (infer from a named city/district if the state isn't stated directly). **Must exactly match** one of the full names in the reference list below — never abbreviate, never invent a spelling variant. `"Unknown"` if it truly can't be determined.

Reference list of Indian states/UTs (passed into every prompt, for the model to disambiguate a city/district into its state):

```
Andhra Pradesh, Arunachal Pradesh, Assam, Bihar, Chhattisgarh, Goa, Gujarat,
Haryana, Himachal Pradesh, Jharkhand, Karnataka, Kerala, Madhya Pradesh,
Maharashtra, Manipur, Meghalaya, Mizoram, Nagaland, Odisha, Punjab, Rajasthan,
Sikkim, Tamil Nadu, Telangana, Tripura, Uttar Pradesh, Uttarakhand, West Bengal,
Delhi, Jammu and Kashmir, Ladakh, Puducherry, Chandigarh
```

**Filtering rule:** only pass an article through to the database if **both** `is_india_traffic_accident` AND `is_recent_accident` are `true`. Anything real-but-historical (old accident resurfacing via court/legal/anniversary coverage) is discarded at extraction time and never reaches the DB.

**Known edge case, accepted as-is (not fixed):** an article can occasionally report on **more than one accident** (observed once in live testing — an ANI piece bundled an Agra crash with an unrelated Delhi hit-and-run in the same story). The current design extracts one accident's worth of fields per article and does not split compound articles into multiple rows. Revisit only if this turns out to be common in practice, not a one-off.

**Model behavior notes from live testing:**
- The model sometimes wraps its JSON response in markdown fences (```json ... ```) despite being told not to — code must strip these (see `extract.py`'s regex cleanup).
- `max_tokens` should be generous enough (400, not 200) that a stray preamble before the JSON doesn't get truncated mid-object and break parsing.
- Every failure path (`None` return) should log *why* to stderr — API error, JSON parse failure (with the raw text), or missing keys — rather than silently returning `None` with no diagnostic. A batch run with silent `None`s is undebuggable after the fact. This is already implemented.

## 6. Date semantics

The `date` stored for each article is the article's **published** date, not the accident's occurrence date. This is a deliberate choice: using occurrence date risks a late-reported accident silently populating an already-viewed/past date in the dashboard. Published date is always "today" (or very close to it, given the `when:1d` + `is_recent_accident` filters), which is what the daily-aggregation UX actually wants.

## 7. Deduplication

Two distinct dedup problems, both necessary for "daily aggregation" to actually work over time:

1. **Exact duplicate** — the same article being processed twice (e.g. a cron rerun, or the same URL appearing in two query variants). Handled by a `UNIQUE` constraint on the resolved article link in Postgres, with `INSERT ... ON CONFLICT (link) DO NOTHING`.
2. **Same real-world event, different outlet** — multiple outlets covering the same accident. Handled by checking existing rows for the same `date + state + vehicle_type`, with `fatality` compared loosely (e.g. within ±1 of the stated death count, since outlets sometimes disagree slightly early in coverage) rather than requiring an exact string match. If a match is found, **append** the new outlet/link into that row's `sources` JSONB column instead of inserting a new row. If no match, insert a new row.

This heuristic is accepted as imperfect (could over-merge two unrelated accidents in the same state/vehicle-type on a busy day, or under-merge if district naming differs) but is good enough for this use case.

## 8. Database schema (Postgres)

```sql
CREATE TABLE articles (
    id SERIAL PRIMARY KEY,
    date DATE NOT NULL,                  -- article's published date, not occurrence date
    title TEXT NOT NULL,
    link TEXT UNIQUE NOT NULL,            -- the RESOLVED publisher URL, not the Google redirect
    source TEXT,                          -- primary outlet name
    sources JSONB DEFAULT '[]'::jsonb,    -- additional outlets covering the same event: [{"source": "...", "link": "..."}]
    fatality TEXT,
    vehicle_type TEXT,
    state TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_articles_date ON articles (date);
CREATE INDEX idx_articles_date_state_vehicle ON articles (date, state, vehicle_type);  -- for the dedup lookup in §7
```

Notes:
- `id` is a surrogate key deliberately, not `link` — because the dedup/merge design needs to append additional source links to an existing row, and `link` alone can't serve as a stable identity for a merged multi-outlet event.
- `link` stores the **resolved** publisher URL (post step-2), not the raw Google redirect — the redirect is useless to an end user clicking through from the dashboard.
- `title` **is shown** in the dashboard table (first column — see §1). `source` is stored for debugging/context but is not shown as its own column.

## 9. Existing code (already written and live-tested — build on this, don't rewrite from scratch)

All of the following has been tested against live Google News RSS data, real publisher sites, and the real OpenAI API (not mocked). Dependencies: `feedparser`, `googlenewsdecoder`, `trafilatura`, `openai`, `python-dotenv`.

**Known environment gotchas hit during testing** (worth being aware of when deploying):
- `googlenewsdecoder` and `trafilatura` need real, unrestricted outbound network access — they will fail (connection errors) behind a restrictive egress allowlist/proxy. Fine on Render; just something to know if testing inside a sandboxed CI step.
- Python 3.9 doesn't support the `str | None` union-type syntax (needs 3.10+) — use `typing.Optional[str]` instead if targeting 3.9.
- When testing with environment variables, remember `python-dotenv`'s `load_dotenv()` does **not** override an already-exported shell variable by default — a stale exported key will silently win over a freshly-edited `.env` file.

### `fetch.py`

```python
"""
fetch.py
Pulls candidate articles from Google News RSS (India-scoped keyword search).
Relevance/geo-filtering is NOT done here -- that's handled entirely by the
LLM call in extract.py (is_india_traffic_accident / is_recent_accident), so
every fetched article gets passed on as a raw candidate for the LLM to judge.
"""

import feedparser
from urllib.parse import quote

RSS_BASE = "https://news.google.com/rss/search"

# Keywords that indicate a genuine traffic/road accident story
ACCIDENT_QUERY = '(accident OR crash OR collision OR "hit and run") AND (road OR highway OR bus OR truck OR car OR bike OR vehicle)'


def build_rss_url(query: str = ACCIDENT_QUERY, country: str = "IN", lang: str = "en", when: str = "1d") -> str:
    """when: Google's own recency filter, e.g. '1h', '1d', '7d'. Appended
    directly into the query string. Set to None/"" to disable."""
    full_query = f"{query} when:{when}" if when else query
    q = quote(full_query)
    return f"{RSS_BASE}?q={q}&hl={lang}-{country}&gl={country}&ceid={country}:{lang}"


def fetch_articles(query: str = ACCIDENT_QUERY, country: str = "IN", lang: str = "en", when: str = "1d"):
    """Fetch and parse the RSS feed. Returns list of dicts, unfiltered --
    pass each one to extract.extract_fields() to judge relevance/recency and
    pull structured fields.

    when: Google's recency filter (default '1d' for a daily cron run).
    Filters by when Google indexed/published the article, not necessarily
    when the accident occurred -- that distinction is handled by the LLM's
    is_recent_accident field, not here."""
    url = build_rss_url(query, country, lang, when)
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
```

### `fetch_body.py`

```python
"""
fetch_body.py
Two-step enrichment for each article, before it goes to extract.py:

1. resolve_url()      -- decode Google's redirect link into the real publisher URL
2. get_article_text() -- fetch that real URL and pull clean body text (no
   ads/nav/boilerplate) for the LLM to actually read, instead of just the
   thin headline-only snippet Google's RSS gives us.

Both steps hit the network per article and can fail for reasons outside
our control (paywalls, bot-blocking, slow/dead redirect tokens, publisher
sites that don't want scraping). Every function here degrades gracefully
-- returns None on failure rather than raising -- so the pipeline can fall
back to headline-only extraction rather than dropping the article entirely.
"""

from typing import Optional
from googlenewsdecoder import gnewsdecoder
import trafilatura

REQUEST_TIMEOUT = 10  # seconds, per network call


def resolve_url(google_link: str) -> Optional[str]:
    """Decode a news.google.com/rss/articles/... redirect link into the
    real publisher URL. Returns None if decoding fails."""
    try:
        result = gnewsdecoder(google_link, interval=1)
        if result.get("status"):
            return result["decoded_url"]
        return None
    except Exception:
        return None


def get_article_text(url: str, max_chars: int = 3000) -> Optional[str]:
    """Fetch a URL and extract clean article body text. Returns None if
    the fetch or extraction fails (paywall, block, dead link, etc)."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if not downloaded:
            return None
        text = trafilatura.extract(downloaded)
        if not text:
            return None
        return text[:max_chars]
    except Exception:
        return None


def enrich_article(article: dict) -> dict:
    """Takes a raw article dict from fetch.py (has 'link' = Google redirect
    URL) and adds 'resolved_link' and 'body_text' keys. Both may be None
    if resolution/scraping failed -- caller should fall back to
    title+snippet extraction in that case, not skip the article."""
    resolved = resolve_url(article["link"])
    body_text = get_article_text(resolved) if resolved else None
    return {
        **article,
        "resolved_link": resolved,
        "body_text": body_text,
    }
```

### `extract.py`

**Note:** the `is_recent_accident` wording below has been tightened to the 24–48 hour framing per the latest design decision. The "last few days" wording was what was actually live-tested (and worked correctly on both test cases in §10) — the 24–48h tightening is a wording-only change in the same spirit and has not been separately re-tested, but should behave the same or better given it's a narrower, more explicit version of the same instruction. Worth a quick sanity check after deploying.

```python
"""
extract.py
LLM-based extraction of structured fields (fatality, vehicle_type, state)
from traffic-accident news article text (title + snippet/body).

Regex/keyword rules were deliberately dropped: they're brittle, need
constant hardcoded maintenance (keyword lists, city->state mappings), and
worst of all give no reliable confidence signal -- a rule can match the
wrong word and report "confident" anyway, silently producing wrong data
with no way to know it happened. An LLM call per article is simpler,
more accurate, and cheap enough at this volume (a few cents/day at most).
"""

import os
import re
import sys
import json
from typing import Optional

# Reference list passed into the prompt to help the model disambiguate
# a city/district name into its state -- data for the model to use,
# not a matching mechanism we rely on ourselves.
INDIAN_STATES_UTS = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh", "Puducherry",
    "Chandigarh",
]

EXTRACTION_PROMPT = """You are extracting structured data from an Indian traffic accident news article for a tracking database.

Title: {title}
Article text: {body}

Reference list of Indian states/UTs (use this to infer a state from a city or district name if the state itself isn't mentioned): {states}

Return ONLY valid JSON, no other text, no markdown fences, with exactly these keys:
- "is_india_traffic_accident": true or false -- false if this is not an Indian road/traffic accident (e.g. it's about a different country, or not a traffic accident at all -- stock market "crash", app "crash", etc.)
- "is_recent_accident": true or false -- true only if the accident itself occurred roughly within the last 24-48 hours and is the actual news. false if the accident happened much earlier (weeks, months, years ago) and the article is actually about something else that happened *around* it more recently -- a court verdict, compensation award, an arrest, an appeal, an anniversary retrospective, a policy response, etc. When in doubt, look at what the headline is actually announcing: a court awarding money over a "2018 crash" is news about the court, not about a crash that just happened.
- "fatality": one of "Yes (N dead)" (fill in the actual number if stated), "Yes" (fatal but no count given), "No (injuries only)", or "Unknown"
- "vehicle_type": the vehicle(s) involved, e.g. "Bus", "Truck / Car", "Two-wheeler", "Auto-rickshaw", "Pedestrian (no vehicle specified)", or "Unknown"
- "state": the Indian state the accident occurred in, inferring from a named city/district if needed. You MUST return the state's full name EXACTLY as it appears in the reference list above (e.g. "Uttar Pradesh", not "UP" or "Uttar pradesh") -- or "Unknown" if it truly can't be determined. Never abbreviate, never invent a spelling variant.
"""


def extract_fields(title: str, snippet: str = "", body_text: Optional[str] = None):
    """Single LLM call per article. Returns a dict with the five keys above.

    body_text: full article text from fetch_body.get_article_text(), if
    available -- gives the model much more to work with than the headline
    alone (Google's RSS snippet is usually just a duplicate of the title,
    not real excerpt text). Falls back to title+snippet when body_text is
    None (scrape failed, paywalled, etc) so the pipeline still produces a
    best-effort result rather than skipping the article.

    Returns None if OPENAI_API_KEY isn't set, the API call itself fails
    (network, rate limit, auth), or the response can't be parsed into the
    expected shape. Every None path prints a one-line diagnostic to stderr
    first -- including the raw model output when parsing is what failed --
    so a None in a batch run is debuggable after the fact instead of being
    indistinguishable from every other None. Caller should treat None as
    'needs manual review', not silently skip it."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print(f"extract_fields: OPENAI_API_KEY not set, skipping '{title[:60]}'", file=sys.stderr)
        return None

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    body = body_text if body_text else (snippet or "(no article text available -- title only)")

    prompt = EXTRACTION_PROMPT.format(
        title=title,
        body=body,
        states=", ".join(INDIAN_STATES_UTS),
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as e:
        # Broad on purpose: network errors, rate limits, auth failures, etc.
        # all land here -- a bad article shouldn't crash a whole batch run,
        # but we still want the reason on record, not just a silent None.
        print(f"extract_fields: API call failed for '{title[:60]}': {e}", file=sys.stderr)
        return None

    raw = resp.choices[0].message.content.strip()
    cleaned = re.sub(r"^```json|```$", "", raw, flags=re.MULTILINE).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        print(f"extract_fields: JSON parse failed for '{title[:60]}': {e}", file=sys.stderr)
        print(f"  raw model output was: {raw!r}", file=sys.stderr)
        return None

    required_keys = {"is_india_traffic_accident", "is_recent_accident", "fatality", "vehicle_type", "state"}
    if not required_keys.issubset(data.keys()):
        print(f"extract_fields: missing keys for '{title[:60]}': got {list(data.keys())}", file=sys.stderr)
        return None

    return data
```

## 10. What's been validated live (and what hasn't)

**Validated against real data, real network, real API — not mocked:**
- `fetch_articles()` against the live Google News RSS endpoint.
- `resolve_url()` via `googlenewsdecoder` against real Google redirect links.
- `get_article_text()` via `trafilatura` against real publisher pages.
- `extract_fields()` against the real OpenAI API, including on two deliberately-chosen edge cases:
  - A same-day fresh accident (Agra, UP car crash) → correctly returned `is_india_traffic_accident: true, is_recent_accident: true, fatality: "Yes (3 dead)", vehicle_type: "Car", state: "Uttar Pradesh"`.
  - A 2018 accident resurfacing via a tribunal compensation ruling → correctly returned `is_india_traffic_accident: true, is_recent_accident: false, fatality: "Yes (1 dead)", vehicle_type: "Two-wheeler", state: "Maharashtra"`.
- Confirmed live that `gl=IN`/`ceid=IN:en` do **not** reliably filter to India-only content (see §3).

**Not yet built — this is the actual remaining work:**
- The dedup/insert function described in §7 (currently only designed, not coded).
- The Postgres schema in §8 (designed, not yet created on an actual Render Postgres instance).
- The FastAPI backend: needs at minimum
  - `GET /articles?date=YYYY-MM-DD` → returns rows for that date.
  - An endpoint (or a parameter default) to get the **most recent date with data**, e.g. `SELECT DISTINCT date FROM articles ORDER BY date DESC LIMIT 1`, so the frontend can default to it on first load.
- The Next.js dashboard frontend: date picker + table with the 5 columns from §1, defaulting to the most-recent-date-with-data view on load.
- The daily cron job on Render that strings together fetch → enrich → extract → filter → dedup/insert, end to end, on a schedule.
- Deployment config/secrets: `OPENAI_API_KEY` on Render, Postgres connection string, Vercel env var pointing the frontend at the Render API URL.

## 11. Known edge cases / design decisions log (for context, not action items)

- **Published date vs. occurrence date**: deliberately using published date for the `date` column, to avoid a late-reported accident silently populating an already-viewed past date.
- **Dashboard default view**: most recent date *with data*, not strictly "today" — avoids an empty table before the daily cron has run.
- **Table columns**: exactly Title / Fatality / Vehicle type / State / Article link, Title first. An `injury_count` field was considered and explicitly rejected — fatality only.
- **Multi-accident-per-article**: known gap, accepted as-is for now (see §5).
- **India-accident criteria**: based on where the accident **occurred**, not the nationality of people involved.
