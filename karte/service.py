"""Zajednički sloj za CLI i grafičko sučelje: izrada događaja iz obrasca, kalkulator, kategorije, tržišta."""

from __future__ import annotations

import dataclasses
import json
from datetime import datetime, timedelta

from karte import legal
from karte.advisor import build_advice
from karte.categories import CategoryInput, analyze
from karte.knowledge import ModelConfig, estimate_capacity, market_info, markets, venue_capacity
from karte.models import Event, Opportunity, Presale, SecondaryMarket
from karte.scoring import Evaluator
from karte.util import parse_bool, parse_datetime, parse_float, parse_int, utcnow


def build_event(f: dict, now: datetime | None = None) -> Event:
    """Događaj iz obrasca (rječnik s ključevima kao u GUI-ju / CLI kalkulatoru)."""
    now = now or utcnow()
    date = parse_datetime(f"{f.get('date')} {f.get('time') or '20:00'}") if f.get("date") else None
    if date is None:
        date = now + timedelta(days=parse_int(f.get("days")) or 45)
    face = parse_float(f.get("face"))
    face_min = parse_float(f.get("face_min")) or face
    face_max = parse_float(f.get("face_max")) or face or face_min
    currency = (f.get("currency") or "EUR").upper()
    lowest, median = parse_float(f.get("resale_lowest")), parse_float(f.get("resale_median"))
    secondary = None
    if lowest or median:
        secondary = SecondaryMarket(
            source=f.get("resale_source") or "ručni unos",
            lowest=lowest,
            median=median,
            currency=currency,
            listing_count=parse_int(f.get("listing_count")),
        )
    tags = f.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.replace("|", ",").split(",") if t.strip()]
    presales = []
    if f.get("presale_start"):
        presales.append(Presale(name=f.get("presale_name") or "Presale", start=parse_datetime(f.get("presale_start"))))
    venue = f.get("venue") or ""
    capacity = parse_int(f.get("capacity"))
    estimated = False
    if not capacity and venue:
        capacity = venue_capacity(venue) or estimate_capacity(venue)
        estimated = capacity is not None
    pers = f.get("personalized")
    return Event(
        id=f.get("id") or "form",
        name=f.get("name") or f.get("artist") or "Događaj",
        artist=f.get("artist") or f.get("name") or "Izvođač",
        venue=venue,
        city=f.get("city") or "",
        country=(f.get("country") or "HR").upper(),
        region=(f.get("region") or "").upper() or None,
        date=date,
        source="obrazac",
        face_min=face_min,
        face_max=face_max,
        currency=currency,
        status=f.get("status") or "onsale",
        public_onsale=parse_datetime(f.get("onsale")),
        presales=presales,
        capacity=capacity,
        capacity_estimated=estimated,
        ticket_limit=parse_int(f.get("ticket_limit")),
        personalized=parse_bool(pers) if pers not in (None, "", "nepoznato") else None,
        tags=[t.lower() for t in tags],
        secondary=secondary,
        artist_listeners=parse_int(f.get("listeners")),
        artist_upcoming_events=parse_int(f.get("upcoming")),
        primary_vendor=(f.get("vendor") or "").lower() or None,
        url=f.get("url") or None,
    )


def make_evaluator(f: dict, settings, model_path: str | None = None, now: datetime | None = None) -> Evaluator:
    config = ModelConfig.load(model_path)
    if f.get("primary_fee") not in (None, ""):
        config.data.setdefault("primary_fees", {})["default_pct"] = parse_float(f.get("primary_fee")) or 0.0
        config.data["primary_fees"]["default_fixed"] = 0.0
    budget = parse_float(f.get("budget"))
    return Evaluator(
        config,
        budget=budget if budget is not None else settings.budget,
        category=f.get("category") or "cheap",
        strict=bool(f.get("strict")),
        now=now,
        seller_country=(f.get("seller_country") or settings.seller_country or "HR").upper(),
    )


def calculate(f: dict, settings, model_path: str | None = None, now: datetime | None = None) -> Opportunity:
    evaluator = make_evaluator(f, settings, model_path, now)
    event = build_event(f, evaluator.now)
    if f.get("primary_fee") not in (None, ""):
        event.primary_vendor = None
    op = evaluator.evaluate(event)
    op.advice = build_advice(op, evaluator.cfg)
    return op


def categories(f: dict, cats: list[dict], settings, model_path: str | None = None, now: datetime | None = None) -> dict:
    evaluator = make_evaluator(f, settings, model_path, now)
    base = build_event({**f, "face": f.get("face") or (cats[0].get("face") if cats else None)}, evaluator.now)
    inputs = [
        CategoryInput(
            name=(c.get("name") or f"Kategorija {i + 1}").strip(),
            face=parse_float(c.get("face")) or 0.0,
            kind=c.get("kind") or "standard",
            secondary_lowest=parse_float(c.get("resale_lowest")),
            listing_count=parse_int(c.get("listing_count")),
        )
        for i, c in enumerate(cats)
    ]
    return analyze(base, inputs, evaluator)


def market_score(code: str) -> tuple[float, dict, dict]:
    """Privlačnost tržišta za prodavača iz HR: veličina × (1 − pravni rizik) × (1 − pristup); limiti jako smanjuju."""
    info = market_info(code)
    law = legal.country_info(code)
    size = float(info.get("size", 0.05))
    score = size ** 0.5 * (1 - float(law.get("risk", 0.35))) * (1 - float(info.get("access_risk", 0.35)))
    rule = law.get("cap", "none")
    if rule in legal.PROFIT_PROHIBITED_RULES:
        score *= 0.1
    elif rule != "none":
        score *= 0.4
    if law.get("planned_cap"):
        score *= 0.7
    return score, info, law


def market_rows(codes: list[str] | None = None) -> list[dict]:
    codes = [c for c in (codes or sorted(markets())) if c != "ALL"] or sorted(markets())
    rows = []
    for code in codes:
        score, info, law = market_score(code)
        rule = law.get("cap", "none")
        rows.append({
            "code": code,
            "name": info.get("name") or law.get("name") or code,
            "score": round(score, 4),
            "size": float(info.get("size", 0.0)),
            "access": round(1 - float(info.get("access_risk", 0.35)), 3),
            "tm": info.get("tm", "?"),
            "rule": rule,
            "rule_label": legal.RULE_LABELS.get(rule, rule),
            "planned": legal.RULE_LABELS.get(law.get("planned_cap"), law.get("planned_cap")) if law.get("planned_cap") else None,
            "legal_risk": float(law.get("risk", 0.35)),
            "access_note": info.get("access", ""),
            "law_summary": law.get("summary", ""),
        })
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows


def opportunity_dict(op: Opportunity) -> dict:
    """Opportunity → JSON-prijateljski rječnik za sučelje."""
    from karte.report import location

    d = json.loads(json.dumps(dataclasses.asdict(op), default=str))
    d["location"] = location(op.event)
    d["total_expected_value"] = op.total_expected_value
    d["listings_share"] = op.listings_share
    return d
