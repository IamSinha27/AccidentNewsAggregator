"""
extract.py
LLM-based extraction of structured fields (severity, deaths, injured,
vehicles, state) from traffic-accident news article text (title + snippet/body).

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
    "Chandigarh", "Andaman and Nicobar Islands",
    "Dadra and Nagar Haveli and Daman and Diu", "Lakshadweep",
]

# The only vehicle categories stored. Kept sorted: that is also the order a
# row's vehicles are stored and shown in. schema.sql repeats this list in a
# CHECK constraint.
VEHICLE_TYPES = ["Auto-rickshaw", "Bus", "Car", "Tractor", "Truck", "Two-wheeler", "Van"]

EXTRACTION_PROMPT = """You are extracting structured data from an Indian traffic accident news article for a tracking database.

Title: {title}
Article text: {body}

Reference list of Indian states/UTs (use this to infer a state from a city or district name if the state itself isn't mentioned): {states}

Return ONLY valid JSON, no other text, no markdown fences, with exactly these keys:
- "is_india_traffic_accident": true or false -- false if this is not an Indian road/traffic accident (e.g. it's about a different country, or not a traffic accident at all -- stock market "crash", app "crash", etc.)
- "is_recent_accident": true or false -- true only if the accident itself occurred roughly within the last 24-48 hours and is the actual news. false if the accident happened much earlier (weeks, months, years ago) and the article is actually about something else that happened *around* it more recently -- a court verdict, compensation award, an arrest, an appeal, an anniversary retrospective, a policy response, etc. When in doubt, look at what the headline is actually announcing: a court awarding money over a "2018 crash" is news about the court, not about a crash that just happened.
- "severity": "fatal" if the article says at least one person died, otherwise "non-fatal" -- including when nobody died and when the article doesn't say either way
- "deaths": the number of people killed, as an integer. Use 0 if nobody died OR the article gives no number ("several dead") -- never guess a number
- "injured": the number of people injured (not counting the dead), as an integer. Use 0 if nobody was injured OR the article gives no number ("many hurt") -- never guess a number
- "vehicles": a JSON array of the types of vehicle involved, using ONLY these exact names: {vehicle_types}. Map what the article says to the closest one: motorcycle/scooter/bike/moped -> "Two-wheeler"; SUV/MUV/jeep -> "Car"; lorry/dumper/tanker/trailer/container -> "Truck"; pickup/tempo/ambulance/school van -> "Van"; e-rickshaw -> "Auto-rickshaw"; tractor-trolley -> "Tractor"; mini-bus/school bus -> "Bus". List each type once, however many of them were involved. Leave out anything that fits none of the names (a train, a pedestrian, a cart), and return [] if no listed vehicle is mentioned -- never invent a name
- "state": the Indian state the accident occurred in, inferring from a named city/district if needed. You MUST return the state's full name EXACTLY as it appears in the reference list above (e.g. "Uttar Pradesh", not "UP" or "Uttar pradesh") -- or "Unknown" if it truly can't be determined. Never abbreviate, never invent a spelling variant.
"""


def _count(value) -> int:
    """A stated head count as a non-negative int. Anything that isn't a
    plain number (null, "several", a missing key) counts as not stated: 0."""
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return 0


def normalise_casualties(data: dict) -> dict:
    """Force severity/deaths/injured into the shape the database expects,
    whatever the model actually sent: severity is 'fatal' or 'non-fatal',
    the counts are ints, a stated death toll always means fatal, and a
    non-fatal accident has no deaths."""
    deaths = _count(data.get("deaths"))
    fatal = str(data.get("severity", "")).strip().lower() == "fatal" or deaths > 0
    data["severity"] = "fatal" if fatal else "non-fatal"
    data["deaths"] = deaths
    data["injured"] = _count(data.get("injured"))
    return data


def normalise_vehicles(value) -> list:
    """The model's vehicles answer as a sorted list of VEHICLE_TYPES, each at
    most once. Names outside the list are dropped rather than stored, so an
    unrecognised or missing answer comes out as [] (shown as unknown)."""
    if isinstance(value, str):
        value = re.split(r"[/,]", value)
    if not isinstance(value, list):
        return []
    known = {name.lower(): name for name in VEHICLE_TYPES}
    found = {known.get(str(item).strip().lower()) for item in value}
    return sorted(found - {None})


def extract_fields(title: str, snippet: str = "", body_text: Optional[str] = None):
    """Single LLM call per article. Returns a dict with the seven keys above.

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
        vehicle_types=", ".join(f'"{name}"' for name in VEHICLE_TYPES),
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

    required_keys = {"is_india_traffic_accident", "is_recent_accident", "severity", "deaths", "injured", "vehicles", "state"}
    if not required_keys.issubset(data.keys()):
        print(f"extract_fields: missing keys for '{title[:60]}': got {list(data.keys())}", file=sys.stderr)
        return None

    data["vehicles"] = normalise_vehicles(data["vehicles"])
    return normalise_casualties(data)
