"""Regression matrix for shared Radar and saved-alert eligibility."""
import pytest
from app.domain import evaluate_property


def result(home, profile):
    return evaluate_property({"status": "active", **home}, [], profile)


@pytest.mark.parametrize("field,pref,direction", [
    ("price", "budget_min", "min"), ("price", "budget_max", "max"),
    ("area", "area_min", "min"), ("area", "area_max", "max"),
    ("bedrooms", "bedrooms_min", "min"), ("bathrooms", "bathrooms_min", "min"),
    ("floor", "floor_min", "min"), ("parking", "parking_min", "min"),
    ("metro_minutes", "metro_max", "max"),
])
def test_numeric_limits_inclusive_and_missing_policy(field, pref, direction):
    assert result({field: 10}, {pref: 10})["eligible"]
    failing = 9 if direction == "min" else 11
    passing = 11 if direction == "min" else 9
    assert not result({field: failing}, {pref: 10})["eligible"]
    assert result({field: passing}, {pref: 10})["eligible"]
    assert result({}, {pref: 10})["pending_requirements"]
    assert not result({}, {pref: 10, "exclude_unknown_required": True})["eligible"]
    assert result({field: failing}, {pref: None})["eligible"]


@pytest.mark.parametrize("status", ["sold", "inactive", "unavailable"])
def test_unavailable_status_cannot_match(status):
    assert not result({"status": status}, {})["eligible"]


BOUNDS = [{"north": -23.5, "south": -23.6, "west": -46.7, "east": -46.6},
          {"north": -23.7, "south": -23.8, "west": -46.9, "east": -46.8}]


@pytest.mark.parametrize("lat,lon,eligible", [
    (-23.55, -46.65, True), (-23.75, -46.85, True),
    (-23.5, -46.6, True), (-23.6, -46.7, True),
    (-23.65, -46.75, False), (-23.55, -46.85, False),
])
def test_bounds_union_not_enclosing_rectangle(lat, lon, eligible):
    evaluated = result({"latitude": lat, "longitude": lon}, {"search_bounds": BOUNDS})
    assert evaluated["eligible"] is eligible
    assert evaluated["fit_coverage"] == 100


@pytest.mark.parametrize("coordinates", [{}, {"latitude": -23.55}, {"latitude": 100, "longitude": -46.65}])
def test_bounds_missing_coordinates_are_pending(coordinates):
    profile = {"search_bounds": BOUNDS}
    evaluated = result(coordinates, profile)
    assert evaluated["eligible"]
    assert evaluated["pending_requirements"] == ["Região delimitada no mapa"]
    assert evaluated["fit_coverage"] == 0
    assert not result(coordinates, {**profile, "exclude_unknown_required": True})["eligible"]


@pytest.mark.parametrize("field,pref,passing,failing", [
    ("elevator", "require_elevator", True, False),
    ("occupied", "exclude_occupied", False, True),
])
def test_boolean_filters_and_unknown_policy(field, pref, passing, failing):
    assert result({field: passing}, {pref: True})["eligible"]
    assert not result({field: failing}, {pref: True})["eligible"]
    assert result({field: failing}, {pref: False})["eligible"]
    assert not result({}, {pref: True, "exclude_unknown_required": True})["eligible"]


@pytest.mark.parametrize("field,pref", [("city", "cities"), ("neighborhood", "neighborhoods"), ("metro_station", "metro_stations")])
def test_text_filters_normalize_accents_whitespace_case(field, pref):
    assert result({field: "  São   Paulo "}, {pref: ["sao paulo"]})["eligible"]
    assert not result({field: "Campinas"}, {pref: ["sao paulo"]})["eligible"]
    assert not result({}, {pref: ["sao paulo"], "exclude_unknown_required": True})["eligible"]


@pytest.mark.parametrize('city', ['São Paulo - SP', 'sao  paulo,sp', ' SÃO  PAULO  -  sp ', 'São Paulo'])
def test_city_aliases_are_canonical_in_profile_and_legacy_filter(city):
    from app.schemas import Profile
    profile = Profile(cities=[city, 'São Paulo'], neighborhoods=[' Vila  Mariana '], metro_stations=[' Ana  Rosa '])
    assert profile.cities == ['São Paulo']
    assert profile.neighborhoods == ['Vila Mariana']
    assert profile.metro_stations == ['Ana Rosa']
    assert result({'city': 'São Paulo'}, {'cities': [city]})['eligible']
    assert result({'city': city}, {'cities': ['São Paulo']})['eligible']
    assert not result({'city': 'Campinas'}, {'cities': [city]})['eligible']


def test_city_aliases_do_not_strip_other_city_or_state_names():
    from app.schemas import Profile
    assert Profile(cities=[' São  Luís ', 'São Paulo - RS']).cities == ['São Luís', 'São Paulo - RS']
    assert not result({'city': 'São Paulo'}, {'cities': ['São Paulo - RS']})['eligible']
