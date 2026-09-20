"""Pure, versioned decision support. Asking prices are not transaction valuations."""
from datetime import datetime, timezone
import math
import statistics
import unicodedata

SCORE_VERSION = "1.1.0"


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def _text(value):
    return " ".join(unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower().split())


def _date(value):
    try:
        result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None


def monthly_cost(property):
    """Condo + tax only; never split or double count a legacy combined amount."""
    combined = _number(property.get("combined_monthly_cost"))
    if combined is not None and combined >= 0:
        if property.get("combined_cost_period") == "unknown":
            return None
        return combined
    condo, tax = _number(property.get("condo_fee")), _number(property.get("property_tax"))
    period = property.get("tax_period")
    if condo is None or condo < 0 or tax is None or tax < 0 or period not in ("monthly", "annual"):
        return None
    return condo + tax / (12 if period == "annual" else 1)


def evaluate_property(property, peers, profile, now=None):
    now = _date(now) if now is not None else datetime.now(timezone.utc)
    if now is None:
        raise ValueError("Data de avaliação inválida")
    reasons, pending, missing, quality_factors, fit_factors = [], [], [], [], []
    eligible = property.get("status") != "unavailable"
    if not eligible:
        reasons.append("Anúncio indisponível")
    checks = [
        ("price", "budget_min", "Preço mínimo", "min"),
        ("price", "budget_max", "Preço dentro do orçamento", "max"),
        ("area", "area_min", "Área mínima", "min"),
        ("area", "area_max", "Área máxima", "max"),
        ("bedrooms", "bedrooms_min", "Dormitórios mínimos", "min"),
        ("bathrooms", "bathrooms_min", "Banheiros mínimos", "min"),
        ("floor", "floor_min", "Andar mínimo", "min"),
        ("parking", "parking_min", "Vagas mínimas", "min"),
        ("metro_minutes", "metro_max", "Distância ao metrô", "max"),
        ("monthly_cost", "monthly_max", "Despesas mensais máximas", "max"),
    ]
    outcomes = {}
    applicable_requirements = known_requirements = 0
    for field, preference, label, direction in checks:
        limit = _number(profile.get(preference))
        if limit is None or (direction == "min" and limit <= 0 and field != "floor"):
            continue
        applicable_requirements += 1
        value = monthly_cost(property) if field == "monthly_cost" else _number(property.get(field))
        if field == "floor" and value is None:
            lower = _number(property.get("floor_min_reported"))
            upper = _number(property.get("floor_max_reported"))
            if upper is not None and upper < limit:
                value = upper
            elif lower is not None and lower >= limit:
                value = lower
            # A range straddling the requirement cannot establish the actual floor.
        if value is None:
            pending.append(label)
            missing.append(field)
            outcomes.setdefault(field, []).append(0)
            continue
        known_requirements += 1
        passed = value <= limit if direction == "max" else value >= limit
        outcomes.setdefault(field, []).append(100 if passed else 0)
        if not passed:
            eligible = False
            reasons.append(f"Não atende: {label} ({value:g}; limite {limit:g})")
    for field, pref, label in (("city", "cities", "Cidade desejada"), ("neighborhood", "neighborhoods", "Bairro desejado")):
        choices = profile.get(pref) or []
        if choices:
            applicable_requirements += 1
            if not _text(property.get(field)):
                pending.append(label)
                missing.append(field)
                outcomes[field] = [0]
            else:
                known_requirements += 1
                passed = _text(property[field]) in {_text(v) for v in choices}
                outcomes[field] = [100 if passed else 0]
                if not passed:
                    eligible = False
                    reasons.append(f"Não atende: {label}")
    if profile.get("require_elevator"):
        applicable_requirements += 1
        outcomes["elevator"] = [100 if property.get("elevator") is True else 0]
        if not isinstance(property.get("elevator"), bool):
            pending.append("Elevador obrigatório")
            missing.append("elevator")
        else:
            known_requirements += 1
            if not property["elevator"]:
                eligible = False
                reasons.append("Não atende: elevador obrigatório")
    if pending and profile.get("exclude_unknown_required"):
        eligible = False
    if profile.get("exclude_occupied"):
        applicable_requirements += 1
        occupied = property.get("occupied")
        outcomes["occupied"] = [100 if occupied is False else 0]
        if not isinstance(occupied, bool):
            pending.append("Imóvel desocupado")
            missing.append("occupied")
        else:
            known_requirements += 1
            if occupied:
                eligible = False
                reasons.append("Não atende: imóvel desocupado")
    stations = profile.get("metro_stations") or []
    if stations:
        applicable_requirements += 1
        available = property.get("metro_stations") or property.get("metro_station")
        available = [available] if isinstance(available, str) else available
        available = [_text(v) for v in available if _text(v)] if isinstance(available, list) else []
        if not available:
            pending.append("Estação de metrô desejada")
            missing.append("metro_station")
            outcomes["metro_station"] = [0]
        else:
            known_requirements += 1
            passed = bool(set(available) & {_text(v) for v in stations})
            outcomes["metro_station"] = [100 if passed else 0]
            if not passed:
                eligible = False
                reasons.append("Não atende: estação de metrô desejada")
    if pending and profile.get("exclude_unknown_required"):
        eligible = False
    quality_rules = [
        ("condition", "Estado de conservação", 35, {"good": 100, "needs_work": 20}),
        ("sunlight", "Iluminação", 25, {"good": 100, "poor": 20}),
        ("ventilation", "Ventilação", 25, {"good": 100, "poor": 20}),
        ("documentation", "Documentação", 15, {"verified": 100, "pending": 30}),
    ]
    for field, label, weight, scores in quality_rules:
        score = scores.get(property.get(field))
        quality_factors.append({"label": label, "value": score, "weight": weight})
        if score is None:
            missing.append(field)
    known = [f for f in quality_factors if f["value"] is not None]
    coverage = sum(f["weight"] for f in known)
    quality = sum(f["value"] * f["weight"] for f in known) / coverage if coverage >= 70 else None
    conservative_quality = sum(f["value"] * f["weight"] for f in known) / 100
    reasons.append(f"Qualidade observada em {coverage}% dos critérios; nota exige cobertura mínima de 70%; dados ausentes não são aprovação")
    weights = profile.get("weights") or {"price": 40, "location": 35, "quality": 25}
    for category, label, fields in (("price", "Orçamento", ["price", "monthly_cost"]), ("location", "Localização", ["city", "neighborhood", "metro_minutes", "metro_station"]), ("quality", "Características e qualidade", ["area", "bedrooms", "bathrooms", "floor", "parking", "elevator", "occupied"])):
        scores = [statistics.mean(outcomes[f]) for f in fields if f in outcomes]
        if category == "quality":
            scores.append(conservative_quality)
        weight = max(0, _number(weights.get(category)) or 0)
        fit_factors.append({"label": label, "score": round(statistics.mean(scores), 2) if scores else None, "weight": weight})
    known_fit = [f for f in fit_factors if f["score"] is not None and f["weight"] > 0]
    fit = sum(f["score"] * f["weight"] for f in known_fit) / sum(f["weight"] for f in known_fit) if known_fit else None
    fit_coverage = round(100 * known_requirements / applicable_requirements, 2) if applicable_requirements else None
    reasons.append("Aderência conservadora: critérios aplicáveis desconhecidos não recebem pontos; são pendências, não defeitos. Cobertura da aderência mede requisitos pessoais conhecidos; qualidade tem cobertura própria.")

    candidates, seen = [], set()
    area, price = _number(property.get("area")), _number(property.get("price"))
    geography = ("city", "neighborhood", "property_type")
    dated = [(p, _date(p.get("observed_at"))) for p in peers]
    dated.sort(key=lambda item: item[1] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for peer, observed in dated:
        if peer is property or (property.get("id") is not None and peer.get("id") == property["id"]):
            continue
        canonical = peer.get("canonical_key")
        source_key = (peer.get("source"), peer.get("external_id"))
        if (canonical and canonical == property.get("canonical_key")) or (all(source_key) and source_key == (property.get("source"), property.get("external_id"))):
            continue
        if observed is None or not 0 <= (now - observed).total_seconds() < 90 * 86400 or peer.get("status") != "active":
            continue
        if any(not _text(property.get(f)) or _text(peer.get(f)) != _text(property[f]) for f in geography):
            continue
        pa, pp = _number(peer.get("area")), _number(peer.get("price"))
        if not area or area <= 0 or not pa or pa <= 0 or not pp or pp <= 0 or not .75 * area <= pa <= 1.25 * area:
            continue
        if any(_number(property.get(f)) is not None and _number(peer.get(f)) is not None and _number(property[f]) != _number(peer[f]) for f in ("bedrooms", "parking")):
            continue
        identities = []
        if canonical:
            identities.append(("canonical", canonical))
        if all(source_key):
            identities.append(("source", *source_key))
        if peer.get("id") is not None:
            identities.append(("id", peer["id"]))
        if peer.get("url"):
            identities.append(("url", peer["url"]))
        if not identities or any(k in seen for k in identities):
            continue
        seen.update(identities)
        candidates.append({"id": peer.get("id"), "price": pp, "area": pa, "price_m2": pp / pa,
                           "_age": (now - observed).total_seconds() / 86400,
                           "_complete": all(_number(peer.get(f)) is not None for f in ("bedrooms", "parking"))})
    if len(candidates) >= 3:
        median = statistics.median(p["price_m2"] for p in candidates)
        mad = statistics.median(abs(p["price_m2"] - median) for p in candidates)
        tolerance = max(3 * 1.4826 * mad, .25 * median)
        candidates = [p for p in candidates if abs(p["price_m2"] - median) <= tolerance]
    count = len(candidates)
    benchmark = statistics.median(p["price_m2"] for p in candidates) if count >= 3 else None
    target_observed = _date(property.get("observed_at"))
    target_current = target_observed is not None and 0 <= (now - target_observed).total_seconds() < 90 * 86400 and property.get("status") == "active"
    opportunity = (1 - (price / area) / benchmark) * 100 if target_current and benchmark and price and price > 0 and area and area > 0 else None
    confidence = "insufficient"
    if benchmark and target_current:
        dispersion = (max(p["price_m2"] for p in candidates) - min(p["price_m2"] for p in candidates)) / benchmark
        median_age = statistics.median(p["_age"] for p in candidates)
        complete_fraction = sum(p["_complete"] for p in candidates) / count
        confidence = "medium" if count >= 6 and dispersion <= .4 and median_age <= 60 and complete_fraction >= .75 else "low"
        # Unknown matching characteristics cannot support the strongest confidence.
        if count >= 12 and dispersion <= .25 and median_age <= 30 and complete_fraction == 1 and all(_number(property.get(f)) is not None for f in ("bedrooms", "parking")):
            confidence = "high"
        reasons.append("Comparação com preços pedidos de anúncios ativos do mesmo bairro e tipo, observados há menos de 90 dias; não é valor de transação")
    elif not benchmark:
        reasons.append("Amostra insuficiente: necessários pelo menos 3 imóveis comparáveis únicos e recentes")
    if not target_current:
        reasons.append("Oportunidade não calculada: o próprio anúncio precisa estar ativo e ter observação conhecida com menos de 90 dias")
    public_comparables = [{k: v for k, v in p.items() if not k.startswith("_")} for p in candidates]
    return {"fit_score": round(fit, 2) if fit is not None else None, "fit_coverage": fit_coverage, "quality_score": round(quality, 2) if quality is not None else None, "quality_coverage": coverage, "opportunity_percent": round(opportunity, 2) if opportunity is not None else None, "confidence": confidence, "comparables_count": count, "benchmark_m2": round(benchmark, 2) if benchmark else None, "comparables": public_comparables, "eligible": eligible, "pending_requirements": pending, "reasons": reasons, "missing": sorted(set(missing)), "quality_factors": quality_factors, "fit_factors": fit_factors, "score_version": SCORE_VERSION}


def simulate_budget(payload):
    values = {}
    for field in ("price", "down_payment", "annual_rate", "months", "monthly_costs", "acquisition_costs", "reserve"):
        value = _number(payload.get(field))
        if value is None or value < 0:
            raise ValueError(f"{field}: informe um número finito não negativo")
        values[field] = value
    price, down, rate, months = (values[f] for f in ("price", "down_payment", "annual_rate", "months"))
    if price <= 0 or down > price or months != int(months) or not 1 <= months <= 600 or rate > 100:
        raise ValueError("Preço, entrada, taxa ou prazo inválido (prazo: 1 a 600 meses; taxa anual: 0 a 100%)")
    model = payload.get("model")
    if model not in ("price", "sac"):
        raise ValueError("Modelo deve ser price ou sac")
    months = int(months)
    principal = price - down
    monthly_rate = math.expm1(math.log1p(rate / 100) / 12)
    payment = principal / months if monthly_rate == 0 else principal * monthly_rate / (-math.expm1(-months * math.log1p(monthly_rate)))
    balance, schedule, interest_total = principal, [], 0.0
    for month in range(1, months + 1):
        interest = balance * monthly_rate
        amortization = principal / months if model == "sac" else payment - interest
        amortization = balance if month == months else min(balance, amortization)
        balance = max(0, balance - amortization)
        interest_total += interest
        schedule.append({"month": month, "payment": round(amortization + interest, 2), "interest": round(interest, 2), "amortization": round(amortization, 2), "balance": round(balance, 2)})
    return {"principal": round(principal, 2), "monthly_rate": monthly_rate, "first_payment": schedule[0]["payment"], "last_payment": schedule[-1]["payment"], "total_interest": round(interest_total, 2), "total_paid": round(principal + interest_total, 2), "initial_cash": round(down + values["acquisition_costs"] + values["reserve"], 2), "first_month_total": round(schedule[0]["payment"] + values["monthly_costs"], 2), "schedule": schedule}
