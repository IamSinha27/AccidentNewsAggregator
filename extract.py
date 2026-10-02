"""
extract.py
Hybrid extraction of structured fields (fatality, vehicle_type, state) from
traffic-accident news article text (title + snippet).

Tier 1: fast regex/keyword rules (free, instant).
Tier 2: optional LLM fallback for articles the rules can't confidently parse
        (only runs if ANTHROPIC_API_KEY is set in the environment).
"""

import os
import re
import json

# ---------------------------------------------------------------------------
# Reference data
# ---------------------------------------------------------------------------

INDIAN_STATES_UTS = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal", "Delhi", "Jammu and Kashmir", "Ladakh", "Puducherry",
    "Chandigarh",
]

# Major cities/districts -> state. Not exhaustive, expand as needed.
CITY_TO_STATE = {
    "mumbai": "Maharashtra", "pune": "Maharashtra", "nagpur": "Maharashtra",
    "bhiwandi": "Maharashtra", "nashik": "Maharashtra",
    "bengaluru": "Karnataka", "bangalore": "Karnataka", "hassan": "Karnataka",
    "bijapur": "Karnataka",
    "hyderabad": "Telangana", "chityal": "Telangana",
    "visakhapatnam": "Andhra Pradesh", "tirupati": "Andhra Pradesh",
    "chennai": "Tamil Nadu", "kolkata": "West Bengal", "sahapur": "West Bengal",
    "lucknow": "Uttar Pradesh", "kanpur": "Uttar Pradesh", "badaun": "Uttar Pradesh",
    "jalandhar": "Punjab", "harchandpur": "Uttar Pradesh", "etawah": "Uttar Pradesh",
    "jaipur": "Rajasthan", "dausa": "Rajasthan", "kotambi": "Gujarat",
    "jarod": "Gujarat", "surat": "Gujarat", "banswara": "Rajasthan",
    "dehradun": "Uttarakhand", "chakrata": "Uttarakhand", "vikasnagar": "Uttarakhand",
    "haridwar": "Uttarakhand", "indore": "Madhya Pradesh",
    "dhubri": "Assam", "gauhati": "Assam", "guwahati": "Assam",
    "bareilly": "Uttar Pradesh", "mathura": "Uttar Pradesh",
    "new delhi": "Delhi",
}

FATAL_WORDS = [
    r"\bkill(?:ed|s|ing)?\b", r"\bdead\b", r"\bdeath[s]?\b", r"\bdi(?:e|ed|es)\b",
    r"\bfatalit(?:y|ies)\b", r"\bperish(?:ed)?\b", r"\bsuccumb(?:ed|s)?\b",
    r"\bmangled\b.*\bkill",  # rare, still let generic kill match
]
INJURY_ONLY_WORDS = [
    r"\binjur(?:ed|y|ies)\b", r"\bhurt\b", r"\bwounded\b", r"\bhospitali[sz]ed\b",
    r"\bcritical condition\b",
]

VEHICLE_KEYWORDS = {
    "Bus": [r"\bbus(?:es)?\b"],
    "Truck": [r"\btruck[s]?\b", r"\blorry\b", r"\blorries\b"],
    "Car": [r"\bcar[s]?\b", r"\bsuv\b", r"\bsedan\b", r"\bertiga\b"],
    "Two-wheeler": [r"\bbike\b", r"\bmotorcycle\b", r"\bscooter\b", r"\btwo-wheeler\b"],
    "Auto-rickshaw / E-rickshaw": [r"\bauto-?rickshaw\b", r"\be-rickshaw\b"],
    "Van": [r"\bvan\b", r"\bminivan\b"],
    "Tractor": [r"\btractor[s]?\b"],
    "Jeep": [r"\bjeep[s]?\b"],
    "Train": [r"\btrain\b", r"\brailway\b"],
    "Pedestrian (no vehicle specified)": [r"\bpedestrian[s]?\b"],
}


def _count_deaths(text: str):
    """Try to pull a numeric death toll, e.g. 'killed 13', 'At least 8 killed'."""
    m = re.search(r"(\d+)\s+(?:people\s+)?(?:were\s+)?killed", text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"kill(?:ed|s|ing)\s+(?:at least\s+)?(\d+)", text, re.I)
    if m:
        return int(m.group(1))
    return None


def extract_rule_based(title: str, snippet: str = ""):
    """Tier 1 extraction. Returns dict with confidence flag."""
    text = f"{title} {snippet}"

    # --- Fatality ---
    fatality = "Unknown"
    death_count = _count_deaths(text)
    if death_count is not None:
        fatality = f"Yes ({death_count} dead)"
    elif any(re.search(p, text, re.I) for p in FATAL_WORDS):
        fatality = "Yes"
    elif any(re.search(p, text, re.I) for p in INJURY_ONLY_WORDS):
        fatality = "No (injuries only)"

    # --- Vehicle type ---
    vehicles_found = []
    for label, patterns in VEHICLE_KEYWORDS.items():
        if any(re.search(p, text, re.I) for p in patterns):
            vehicles_found.append(label)
    vehicle_type = " / ".join(vehicles_found) if vehicles_found else "Unknown"

    # --- State ---
    state = "Unknown"
    for s in INDIAN_STATES_UTS:
        if re.search(rf"\b{re.escape(s)}\b", text, re.I):
            state = s
            break
    if state == "Unknown":
        for city, st in CITY_TO_STATE.items():
            if re.search(rf"\b{re.escape(city)}\b", text, re.I):
                state = st
                break

    confident = fatality != "Unknown" and vehicle_type != "Unknown" and state != "Unknown"
    return {
        "fatality": fatality,
        "vehicle_type": vehicle_type,
        "state": state,
        "confident": confident,
    }


def extract_llm_fallback(title: str, snippet: str = ""):
    """Tier 2: LLM extraction for articles rule-based pass couldn't confidently parse.
    Requires ANTHROPIC_API_KEY in the environment. Returns None if unavailable."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    import anthropic
    client = anthropic.Anthropic(api_key=api_key)

    prompt = f"""Extract structured data from this Indian traffic accident news snippet.
Title: {title}
Snippet: {snippet}

Return ONLY valid JSON, no other text, with exactly these keys:
- "fatality": one of "Yes (N dead)" (fill in actual number if stated), "Yes", "No (injuries only)", or "Unknown"
- "vehicle_type": the vehicle(s) involved (e.g. "Bus", "Truck / Car", "Two-wheeler"), or "Unknown"
- "state": the Indian state the accident occurred in (infer from city/district if named), or "Unknown"
"""
    resp = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = resp.content[0].text.strip()
    raw = re.sub(r"^```json|```$", "", raw, flags=re.MULTILINE).strip()
    try:
        data = json.loads(raw)
        data["confident"] = True
        return data
    except json.JSONDecodeError:
        return None


def extract_fields(title: str, snippet: str = "", use_llm_fallback: bool = True):
    """Hybrid entry point: rule-based first, LLM fallback only if unconfident."""
    result = extract_rule_based(title, snippet)
    if not result["confident"] and use_llm_fallback:
        llm_result = extract_llm_fallback(title, snippet)
        if llm_result:
            return llm_result
    return result
