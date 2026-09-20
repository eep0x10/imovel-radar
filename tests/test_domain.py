from datetime import datetime, timezone
import math

import pytest

from app.domain import evaluate_property, monthly_cost, simulate_budget


NOW = datetime(2026, 9, 19, tzinfo=timezone.utc)


def home(**changes):
    return dict({"id": 1, "canonical_key": "home", "source": "feed", "external_id": "1", "price": 300000, "area": 50, "city": "São Paulo", "neighborhood": "Mooca", "property_type": "apartment", "bedrooms": 2, "parking": 1, "status": "active", "observed_at": "2026-09-18T00:00:00Z"}, **changes)


def peers(n=3):
    return [home(id=i + 2, external_id=str(i + 2), canonical_key=f"peer{i}", price=350000 + i * 1000) for i in range(n)]


def test_unknown_quality_is_not_zero_or_perfect_and_unknown_requirement_is_pending():
    result = evaluate_property(home(), [], {"require_elevator": True, "monthly_max": 600}, NOW)
    assert result["quality_score"] is None
    assert result["fit_score"] == 0
    assert result["fit_coverage"] == 0
    assert result["eligible"]
    assert set(result["pending_requirements"]) == {"Elevador obrigatório", "Despesas mensais máximas"}
    assert not evaluate_property(home(), [], {"require_elevator": True, "exclude_unknown_required": True}, NOW)["eligible"]


def test_requirements_fail_and_zero_parking_is_known():
    result = evaluate_property(home(parking=0, elevator=False), [], {"parking_min": 1, "require_elevator": True, "budget_max": 250000}, NOW)
    assert not result["eligible"]
    assert result["pending_requirements"] == []
    assert len(result["reasons"]) >= 3
    assert not evaluate_property(home(), [], {"cities": ["Campinas"]}, NOW)["eligible"]
    assert evaluate_property(home(), [], {"cities": ["sao paulo"]}, NOW)["eligible"]


def test_quality_is_price_and_preference_independent():
    first = home(condition="good", sunlight="poor", ventilation="good")
    a = evaluate_property(first, [], {"weights": {"quality": 100}}, NOW)
    b = evaluate_property({**first, "price": 1000000}, [], {"weights": {"price": 100}}, NOW)
    assert a["quality_score"] == b["quality_score"]
    assert 20 < a["quality_score"] < 100
    assert b["fit_score"] is None


def test_personal_weights_change_fit_only():
    p = home(condition="good")
    a = evaluate_property(p, [], {"budget_max": 200000, "weights": {"price": 90, "quality": 10}}, NOW)
    b = evaluate_property(p, [], {"budget_max": 200000, "weights": {"price": 10, "quality": 90}}, NOW)
    assert a["fit_score"] < b["fit_score"]
    assert a["quality_score"] == b["quality_score"]
    assert not a["eligible"] and not b["eligible"]


def test_sparse_quality_has_no_grade_and_keeps_evidence_coverage():
    result = evaluate_property(home(condition="good"), [], {}, NOW)
    assert result["quality_score"] is None
    assert result["quality_coverage"] == 35
    assert result["fit_score"] == 35
    assert result["fit_coverage"] is None  # No configured personal requirements.
    assert result["score_version"] == "1.1.0"


def test_missing_requirements_never_improve_fit_and_elevator_contributes():
    profile = {"budget_max": 330000, "monthly_max": 600, "require_elevator": True, "metro_max": 15}
    unknown = home(condition="good")
    scores = []
    coverages = []
    for updates in ({}, {"combined_monthly_cost": 500}, {"elevator": True}, {"metro_minutes": 10}, {"sunlight": "good"}, {"ventilation": "good"}, {"documentation": "verified"}):
        unknown.update(updates)
        result = evaluate_property(unknown, [], profile, NOW)
        scores.append(result["fit_score"])
        coverages.append(result["fit_coverage"])
    assert scores == sorted(scores)
    assert coverages == sorted(coverages)
    assert scores[0] < scores[-1] == 100
    assert coverages[0] == 25 and coverages[-1] == 100
    good = evaluate_property(home(elevator=True), [], {"require_elevator": True}, NOW)
    missing = evaluate_property(home(), [], {"require_elevator": True}, NOW)
    assert good["fit_score"] > missing["fit_score"]


@pytest.mark.parametrize("changes", [{"observed_at": None}, {"observed_at": "2025-01-01"}, {"observed_at": "2027-01-01"}, {"status": "unknown"}, {"status": "unavailable"}])
def test_opportunity_requires_current_observation_of_target(changes):
    result = evaluate_property(home(**changes), peers(12), {}, NOW)
    assert result["opportunity_percent"] is None
    assert result["confidence"] == "insufficient"
    assert result["benchmark_m2"] is not None
    assert result["comparables_count"] == 12


def test_legacy_combined_cost_does_not_double_count_and_tax_period_matters():
    assert monthly_cost({"combined_monthly_cost": 500, "condo_fee": 400, "property_tax": 1200, "tax_period": "annual"}) == 500
    assert monthly_cost({"condo_fee": 400, "property_tax": 1200, "tax_period": "annual"}) == 500
    assert monthly_cost({"condo_fee": 400, "property_tax": 1200, "tax_period": "unknown"}) is None
    assert monthly_cost({"condo_fee": 0, "property_tax": 0, "tax_period": "monthly"}) == 0
    assert not evaluate_property(home(combined_monthly_cost=700), [], {"monthly_max": 600}, NOW)["eligible"]


def test_combined_cost_unknown_period_is_pending_not_monthly_approval():
    property = home(combined_monthly_cost=500, combined_cost_period="unknown", condo_fee=400, property_tax=1200, tax_period="annual")
    assert monthly_cost(property) is None
    result = evaluate_property(property, [], {"monthly_max": 600}, NOW)
    assert "Despesas mensais máximas" in result["pending_requirements"]
    assert "monthly_cost" in result["missing"]
    assert result["fit_coverage"] == 0
    assert next(f for f in result["fit_factors"] if f["label"] == "Orçamento")["score"] == 0
    assert not evaluate_property(property, [], {"monthly_max": 600, "exclude_unknown_required": True}, NOW)["eligible"]
    assert monthly_cost({"combined_monthly_cost": 500}) == 500
    assert monthly_cost({"combined_monthly_cost": 500, "combined_cost_period": "monthly"}) == 500


@pytest.mark.parametrize('costs,eligible,pending', [
    ({'condo_fee': 630, 'property_tax': 1200, 'tax_period': 'unknown'}, False, False),
    ({'condo_fee': 400, 'property_tax': 1200, 'tax_period': 'unknown'}, True, True),
    ({'condo_fee': None, 'property_tax': 7200, 'tax_period': 'annual'}, False, False),
    ({'condo_fee': None, 'property_tax': 600, 'tax_period': 'monthly'}, False, False),
    ({'condo_fee': 580, 'property_tax': None}, True, True),
])
def test_known_cost_lower_bound_can_disprove_budget_without_inventing_total(costs, eligible, pending):
    property = home(**costs)
    assert monthly_cost(property) is None
    result = evaluate_property(property, [], {'monthly_max': 580}, NOW)
    assert result['eligible'] is eligible
    assert ('Despesas mensais máximas' in result['pending_requirements']) is pending
    assert result['fit_coverage'] == (0 if pending else 100)
    if not eligible:
        assert any('pelo menos' in reason for reason in result['reasons'])
        assert any('Não atende: Despesas mensais máximas' in reason for reason in result['reasons'])
    assert monthly_cost(property) is None


@pytest.mark.parametrize("profile,changes,label", [
    ({"budget_min": 250000}, {"price": 200000}, "Preço mínimo"),
    ({"bathrooms_min": 2}, {"bathrooms": 1}, "Banheiros mínimos"),
    ({"floor_min": 3}, {"floor": 2}, "Andar mínimo"),
    ({"floor_min": 0}, {"floor": -1}, "Andar mínimo"),
    ({"exclude_occupied": True}, {"occupied": True}, "imóvel desocupado"),
    ({"metro_stations": ["Belém"]}, {"metro_station": "Tatuapé"}, "estação de metrô"),
])
def test_extended_profile_requirements_reject_known_failure(profile, changes, label):
    result = evaluate_property(home(**changes), [], profile, NOW)
    assert not result["eligible"]
    assert any(label.lower() in reason.lower() for reason in result["reasons"])


def test_extended_profile_unknowns_pending_and_recovery_monotonic():
    profile = {"bathrooms_min": 2, "floor_min": 3, "exclude_occupied": True, "metro_stations": ["Belém"], "exclude_unknown_required": True}
    pending = evaluate_property(home(), [], profile, NOW)
    assert not pending["eligible"]
    assert len(pending["pending_requirements"]) == 4
    assert pending["fit_coverage"] == 0
    matched = evaluate_property(home(bathrooms=2, floor=3, occupied=False, metro_station="Belem"), [], profile, NOW)
    assert matched["eligible"]
    assert not matched["pending_requirements"]
    assert matched["fit_coverage"] == 100
    assert matched["fit_score"] > pending["fit_score"]
    many = evaluate_property(home(metro_stations=["Tatuapé", "Belém"]), [], {"metro_stations": ["Belém"]}, NOW)
    assert many["eligible"] and not many["pending_requirements"]


@pytest.mark.parametrize('changes,eligible,pending', [
    ({'floor_min_reported': 0, 'floor_max_reported': 3}, True, True),
    ({'floor_min_reported': 0, 'floor_max_reported': 1}, False, False),
    ({'floor_min_reported': 3, 'floor_max_reported': 6}, True, False),
    ({'floor_min_reported': 0}, True, True),
    ({'floor_max_reported': 6}, True, True),
    ({'floor': 1, 'floor_min_reported': 0, 'floor_max_reported': 3}, False, False),
    ({'floor': 3, 'floor_min_reported': 0, 'floor_max_reported': 3}, True, False),
])
def test_floor_interval_only_decides_when_requirement_is_proven(changes, eligible, pending):
    property = home(**changes)
    result = evaluate_property(property, [], {'floor_min': 2}, NOW)
    assert result['eligible'] is eligible
    assert ('Andar mínimo' in result['pending_requirements']) is pending
    assert result['fit_coverage'] == (0 if pending else 100)
    assert property.get('floor') == changes.get('floor')
    if pending:
        assert not evaluate_property(property, [], {'floor_min': 2, 'exclude_unknown_required': True}, NOW)['eligible']


def test_small_sample_and_duplicates_never_manufacture_discount():
    candidates = peers(2)
    result = evaluate_property(home(), candidates * 4 + [home()], {}, NOW)
    assert result["comparables_count"] == 2
    assert result["opportunity_percent"] is None
    assert result["confidence"] == "insufficient"


def test_comparable_filters_unknown_stale_future_inactive_geography_and_outliers():
    valid = peers()
    invalid = [home(id=99, canonical_key="bad", external_id="99", **changes) for changes in [
        {"observed_at": None}, {"observed_at": "2025-01-01"}, {"observed_at": "2027-01-01"},
        {"status": "unknown"}, {"status": "unavailable"}, {"city": "Campinas"},
        {"neighborhood": "Ipiranga"}, {"property_type": "house"}, {"area": 100},
        {"parking": 0}, {"bedrooms": 3}, {"price": 99999999},
    ]]
    result = evaluate_property(home(), valid + invalid, {}, NOW)
    assert result["comparables_count"] == 3
    assert result["benchmark_m2"] == 7020
    assert result["opportunity_percent"] == round((1 - 6000 / 7020) * 100, 2)
    assert result["confidence"] == "low"


def test_duplicate_sources_and_unknown_geography():
    candidates = peers()
    # Same source listing with a different canonical label is still one observation.
    candidates.append({**candidates[0], "id": 80, "canonical_key": "other"})
    assert evaluate_property(home(), candidates, {}, NOW)["comparables_count"] == 3
    assert evaluate_property(home(neighborhood=None), candidates, {}, NOW)["benchmark_m2"] is None


def test_confidence_accounts_for_freshness_and_completeness():
    candidates = peers(12)
    assert evaluate_property(home(), candidates, {}, NOW)["confidence"] == "high"
    stale = [{**p, "observed_at": "2026-07-01"} for p in candidates]
    assert evaluate_property(home(), stale, {}, NOW)["confidence"] == "low"
    unknown = [{**p, "parking": None} for p in candidates]
    assert evaluate_property(home(), unknown, {}, NOW)["confidence"] == "low"


def budget(**changes):
    return dict({"price": 300000, "down_payment": 60000, "annual_rate": 12, "months": 240, "monthly_costs": 500, "acquisition_costs": 10000, "reserve": 20000, "model": "price"}, **changes)


@pytest.mark.parametrize("model", ["price", "sac"])
def test_interest_free_and_cash_accounting(model):
    result = simulate_budget(budget(annual_rate=0, model=model))
    assert result["principal"] == 240000
    assert result["first_payment"] == result["last_payment"] == 1000
    assert result["total_interest"] == 0
    assert result["total_paid"] == 240000
    assert result["initial_cash"] == 90000
    assert result["first_month_total"] == 1500
    assert result["schedule"][-1]["balance"] == 0


def test_sac_matches_analytical_interest_sum_and_price_annuity():
    sac = simulate_budget(budget(model="sac"))
    price = simulate_budget(budget())
    rate = 1.12 ** (1 / 12) - 1
    assert sac["monthly_rate"] == pytest.approx(rate)
    assert sac["first_payment"] == round(1000 + 240000 * rate, 2)
    assert sac["total_interest"] == round(rate * 240000 * 241 / 2, 2)
    assert sac["first_payment"] > sac["last_payment"]
    expected = 240000 * rate / (1 - (1 + rate) ** -240)
    assert price["first_payment"] == round(expected, 2)
    assert abs(price["first_payment"] - price["last_payment"]) <= .01
    assert price["total_interest"] > sac["total_interest"]
    assert price["schedule"][-1]["balance"] == 0
    assert math.isclose(sum(row["amortization"] for row in price["schedule"]), 240000, abs_tol=1.2)


@pytest.mark.parametrize("changes", [{"price": None}, {"price": float("nan")}, {"months": 0}, {"months": 1.5}, {"months": 601}, {"down_payment": 400000}, {"annual_rate": -1}, {"annual_rate": float("inf")}, {"monthly_costs": -1}, {"model": "unknown"}, {"months": True}])
def test_invalid_budget_rejected(changes):
    with pytest.raises(ValueError):
        simulate_budget(budget(**changes))


def test_full_cash_purchase_has_no_interest():
    result = simulate_budget(budget(down_payment=300000))
    assert result["principal"] == result["total_paid"] == 0
    assert result["first_month_total"] == 500
