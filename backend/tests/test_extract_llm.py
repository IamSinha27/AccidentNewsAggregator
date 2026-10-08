"""
Live checks that the extraction prompt gets the model to sort real-world
wording into our fixed fields. These call the OpenAI API, so they are not part
of a plain `pytest` run:

    pytest -m llm

The model isn't deterministic: a single odd failure can be noise, the same
case failing repeatedly means the prompt needs another hint.
"""

import os

import pytest

from extract import extract_fields

pytestmark = [
    pytest.mark.llm,
    pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="OPENAI_API_KEY not set"),
]


def extract(sentence: str) -> dict:
    """Run one made-up report through the real prompt. The same sentence is
    used as headline and body; 'this morning' keeps it a recent accident."""
    fields = extract_fields(sentence, body_text=sentence + " The accident happened this morning, police said.")
    assert fields is not None, "extraction failed"
    return fields


# --- vehicles: wording -> category ------------------------------------------

@pytest.mark.parametrize("sentence,expected", [
    # one row per mapping hint in the prompt
    ("Two killed as motorcycle skids off road in Nashik, Maharashtra", ["Two-wheeler"]),
    ("Woman on scooter injured after hitting divider in Jaipur, Rajasthan", ["Two-wheeler"]),
    ("Three hurt as SUV overturns on highway near Lucknow, Uttar Pradesh", ["Car"]),
    ("Jeep falls into gorge in Shimla, Himachal Pradesh, four dead", ["Car"]),
    ("Lorry overturns on highway near Salem, Tamil Nadu, driver hurt", ["Truck"]),
    ("Driver killed as dumper overturns in Dhanbad, Jharkhand", ["Truck"]),
    ("Tanker overturns on NH-48 near Vadodara, Gujarat, driver injured", ["Truck"]),
    ("Pickup van overturns in Kolhapur, Maharashtra, six labourers hurt", ["Van"]),
    ("Tempo falls into canal in Karnal, Haryana, two dead", ["Van"]),
    ("Ambulance overturns near Mysuru, Karnataka, patient injured", ["Van"]),
    ("E-rickshaw overturns in Patna, Bihar, three passengers hurt", ["Auto-rickshaw"]),
    ("Tractor-trolley overturns in Ludhiana, Punjab, five farm workers injured", ["Tractor"]),
    ("School bus falls into ditch in Dehradun, Uttarakhand, 12 children hurt", ["Bus"]),
    ("Mini-bus overturns near Guwahati, Assam, eight injured", ["Bus"]),
    # several vehicles: every type listed once, in alphabetical order
    ("Three killed as car rams truck on NH-44 near Agra, Uttar Pradesh", ["Car", "Truck"]),
    ("Biker dies after bike collides with bus in Kochi, Kerala", ["Bus", "Two-wheeler"]),
    ("Two motorcycles collide head-on in Indore, Madhya Pradesh, both riders hurt", ["Two-wheeler"]),
    ("Bus, lorry and auto-rickshaw collide near Vijayawada, Andhra Pradesh, five hurt", ["Auto-rickshaw", "Bus", "Truck"]),
    # things that are not one of our categories are left out
    ("Car hits pedestrian crossing the road in Bhopal, Madhya Pradesh, man injured", ["Car"]),
    ("Train hits truck at level crossing in Cuttack, Odisha, driver killed", ["Truck"]),
    ("Pedestrian killed in hit-and-run in Hyderabad, Telangana; vehicle not identified", []),
    ("Two injured in road accident near Raipur, Chhattisgarh", []),
])
def test_vehicles_are_mapped_to_our_categories(sentence, expected):
    assert extract(sentence)["vehicles"] == expected


# --- severity, deaths, injured ------------------------------------------------

@pytest.mark.parametrize("sentence,expected", [
    ("Three killed, five injured as bus overturns near Nagpur, Maharashtra", ("fatal", 3, 5)),
    ("Driver dies as truck overturns near Kota, Rajasthan", ("fatal", 1, 0)),
    ("Several killed as bus falls into gorge in Chamba, Himachal Pradesh", ("fatal", 0, 0)),
    ("12 injured as bus overturns near Madurai, Tamil Nadu; no deaths reported", ("non-fatal", 0, 12)),
    ("Many hurt as bus overturns near Warangal, Telangana", ("non-fatal", 0, 0)),
    ("Truck overturns on highway near Rourkela, Odisha; driver escapes unhurt", ("non-fatal", 0, 0)),
    ("Car and truck collide on highway near Ambala, Haryana; traffic hit for hours", ("non-fatal", 0, 0)),
])
def test_severity_and_counts(sentence, expected):
    fields = extract(sentence)
    assert (fields["severity"], fields["deaths"], fields["injured"]) == expected
