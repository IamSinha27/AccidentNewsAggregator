import pytest

from extract import VEHICLE_TYPES, normalise_casualties, normalise_vehicles


@pytest.mark.parametrize("sent,expected", [
    ({"severity": "fatal", "deaths": 3, "injured": 5}, ("fatal", 3, 5)),
    ({"severity": "fatal", "deaths": 0, "injured": 0}, ("fatal", 0, 0)),
    ({"severity": "non-fatal", "deaths": 0, "injured": 12}, ("non-fatal", 0, 12)),
    # a stated toll always means fatal, whatever the model called it
    ({"severity": "non-fatal", "deaths": 2, "injured": 0}, ("fatal", 2, 0)),
    # anything that isn't a plain number is "not stated"
    ({"severity": "Fatal", "deaths": "several", "injured": None}, ("fatal", 0, 0)),
    ({"severity": "fatal", "deaths": "4", "injured": "7"}, ("fatal", 4, 7)),
    ({"severity": "unknown", "deaths": None, "injured": -1}, ("non-fatal", 0, 0)),
    ({"severity": "non-fatal", "deaths": False, "injured": True}, ("non-fatal", 0, 0)),
])
def test_normalise_casualties(sent, expected):
    out = normalise_casualties(dict(sent))
    assert (out["severity"], out["deaths"], out["injured"]) == expected


@pytest.mark.parametrize("sent,expected", [
    (["Truck", "Car"], ["Car", "Truck"]),
    (["car", " TRUCK ", "Car"], ["Car", "Truck"]),
    (["Bus", "Train", "Pedestrian"], ["Bus"]),
    (["Two-wheeler"], ["Two-wheeler"]),
    ("Truck / Car, Bus", ["Bus", "Car", "Truck"]),
    ([], []),
    (["Unknown"], []),
    (None, []),
    ("Unknown", []),
    (7, []),
])
def test_normalise_vehicles(sent, expected):
    assert normalise_vehicles(sent) == expected


def test_vehicle_types_are_kept_sorted():
    assert VEHICLE_TYPES == sorted(VEHICLE_TYPES)
