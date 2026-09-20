"""Batch optimization must preserve every score and ordered comparable."""
from datetime import datetime, timedelta, timezone

import pytest

from app.domain import evaluate_many, evaluate_property


NOW = datetime(2026, 9, 20, tzinfo=timezone.utc)


def listings():
    rows = []
    for i in range(80):
        rows.append({
            "id": i, "canonical_key": f"property-{i}", "source": "feed",
            "external_id": str(i), "url": f"https://example.test/{i}",
            "city": "São Paulo" if i % 3 else " sao  PAULO ",
            "neighborhood": "Mooca" if i % 2 else "Brás",
            "property_type": "apartment", "status": "active",
            "price": 300000 + i * 1300, "area": 60 + i % 12,
            "bedrooms": 2, "parking": 1,
            "observed_at": (NOW - timedelta(days=i % 15)).isoformat(),
        })
    # Same canonical, same ID, same URL, same source identity; newer wins,
    # but an incompatible newer record must not suppress an eligible older one.
    rows.extend([
        {**rows[1], "id": 101, "price": 315000, "observed_at": NOW.isoformat()},
        {**rows[3], "canonical_key": "duplicate-id", "price": 320000},
        {**rows[5], "id": 105, "canonical_key": "duplicate-url", "external_id": "105"},
        {**rows[7], "id": 107, "canonical_key": "duplicate-source", "url": "https://example.test/new"},
        {**rows[9], "id": 109, "area": 400, "observed_at": NOW.isoformat()},
        {**rows[11], "id": 111, "neighborhood": "Other", "observed_at": NOW.isoformat()},
    ])
    for field in ("city", "neighborhood", "property_type"):
        rows.append({**rows[0], "id": len(rows) + 200, field: None})
    rows.extend([
        {**rows[13], "observed_at": "invalid"},
        {**rows[15], "observed_at": (NOW + timedelta(days=1)).isoformat()},
        {**rows[17], "observed_at": (NOW - timedelta(days=90)).isoformat()},
        {**rows[19], "status": "unavailable"},
        {**rows[21], "property_type": "house"},
        {**rows[23], "city": "Campinas"},
        {**rows[25], "bedrooms": None, "parking": None},
    ])
    return rows


@pytest.mark.parametrize("profile", [{}, {"area_min": 70, "budget_max": 400000},
    {"cities": ["São Paulo"], "neighborhoods": ["Brás"], "exclude_unknown_required": True}])
def test_batch_matches_unrestricted_evaluation_including_duplicate_order(profile):
    rows = listings()
    expected = [evaluate_property(row, rows, profile, NOW) for row in rows]
    assert evaluate_many(iter(rows), profile, NOW) == expected
    for row, result in zip(rows, expected):
        if any(row.get(field) is None for field in ("city", "neighborhood", "property_type")):
            assert result["comparables"] == []


def test_empty_batch_and_invalid_evaluation_date():
    assert evaluate_many([], {}, NOW) == []
    with pytest.raises(ValueError, match="inválida"):
        evaluate_many(listings(), {}, "invalid")
