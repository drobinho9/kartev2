"""Pravna pravila preprodaje po državama."""

from __future__ import annotations

from karte import knowledge
from karte.models import LegalResult

PROFIT_PROHIBITED_RULES = {"face", "organizer_permission"}

RULE_LABELS = {
    "none": "bez zakonskog limita cijene",
    "face": "zabranjeno iznad nominalne cijene",
    "percent": "limit postotka iznad originalne cijene",
    "percent_or_abs": "limit postotka / apsolutnog iznosa iznad originalne cijene",
    "organizer_permission": "samo uz dopuštenje organizatora",
}


def country_info(country: str | None, region: str | None = None) -> dict:
    """Pravila za državu; ako postoji pravilo za saveznu državu/pokrajinu (npr. US-VT), ono nadjačava državno."""
    data = knowledge.laws()
    code = (country or "").upper()
    base = dict(data[code]) if code in data else dict(data["default"])
    if region:
        sub = data.get(f"{code}-{region.upper()}")
        if sub:
            if "planned_cap" not in sub:
                for k in [k for k in base if k.startswith("planned_")]:
                    base.pop(k)
            country_summary = base.get("summary", "")
            base.update(sub)
            base["summary"] = f"{sub.get('summary', '')} ({base.get('name', code)} – općenito: {country_summary})".strip()
            base["_code"] = f"{code}-{region.upper()}"
    return base


def cap_price(rule: str, info: dict, face_ref: float | None, buy_cost: float | None, prefix: str = "") -> float | None:
    """Najviša zakonski dopuštena cijena preprodaje po ulaznici (EUR) ili None ako limita nema."""
    if face_ref is None or rule == "none":
        return None
    basis = info.get("cap_basis", "face")
    base = buy_cost if (basis == "paid" and buy_cost is not None) else face_ref
    if rule in ("face", "organizer_permission"):
        return base
    if rule == "percent":
        return base * (1 + float(info.get(f"{prefix}cap_pct", 0.0)))
    if rule == "percent_or_abs":
        pct = float(info.get(f"{prefix}cap_pct", 0.0))
        absolute = float(info.get(f"{prefix}cap_abs", 0.0))
        return base + min(base * pct, absolute)
    return None


def evaluate(
    country: str | None, face_ref: float | None, buy_cost: float | None, strict: bool = False, region: str | None = None
) -> LegalResult:
    info = country_info(country, region)
    rule = info.get("cap", "none")
    planned = info.get("planned_cap")
    planned_applied = False
    prefix = ""
    if strict and planned:
        rule = planned
        planned_applied = True
        prefix = "planned_"
    price = cap_price(rule, info, face_ref, buy_cost, prefix)
    return LegalResult(
        country=info.get("_code", (country or "").upper()),
        country_name=info.get("name", country or "?"),
        rule=rule,
        summary=info.get("summary", ""),
        cap_price=price,
        planned_applied=planned_applied,
        planned_rule=planned,
        risk=float(info.get("risk", 0.35)),
        profit_prohibited=rule in PROFIT_PROHIBITED_RULES,
        sources=list(info.get("sources", [])),
    )


def all_countries() -> list[tuple[str, dict]]:
    return [(code, info) for code, info in knowledge.laws().items() if code != "default"]
