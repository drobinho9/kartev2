"""Sport (posebno nogomet): prepoznavanje sporta i natjecanja te posebna pravila preprodaje.

Pravila su u karte/data/sport.toml i primjenjuju se DODATNO uz opća pravila države (laws.toml) –
uvijek pobjeđuje strože pravilo. Vidi vodič karte/data/guides/6_nogomet_sport.md.
"""

from __future__ import annotations

import dataclasses
import tomllib
from functools import lru_cache
from importlib import resources

from karte.models import Event, LegalResult
from karte.platforms import Platform
from karte.util import normalize

RULE_LABELS = {
    "criminal": "neovlaštena preprodaja je kazneno djelo",
    "face": "zabranjeno iznad nominalne cijene",
    "club_terms": "uvjeti kluba/saveza zabranjuju preprodaju (poništavanje ulaznica, zabrane)",
    "official_only": "preprodaja samo preko službenog kanala organizatora",
    "official_marketplace": "preprodaja samo na službenom tržištu organizatora (uz naknade)",
    "none": "bez posebnih sportskih ograničenja",
}
STRICTNESS = {"criminal": 5, "face": 4, "club_terms": 3, "official_only": 3, "official_marketplace": 2, "none": 0}
LEGAL_RULES = {"criminal", "face"}
CONTRACT_RULES = {"club_terms", "official_only"}
OFFICIAL_RULES = CONTRACT_RULES | {"official_marketplace"}

SPORT_LABELS = {
    "football": "Nogomet",
    "american_football": "Američki nogomet",
    "basketball": "Košarka",
    "baseball": "Bejzbol",
    "hockey": "Hokej",
    "tennis": "Tenis",
    "motorsport": "Motosport",
    "other": "Ostali sportovi",
}
_GENRE_MAP = {
    "soccer": "football", "fussball": "football", "fußball": "football", "voetbal": "football", "nogomet": "football",
    "calcio": "football", "futbol": "football", "fútbol": "football",
    "basketball": "basketball", "kosarka": "basketball", "košarka": "basketball",
    "baseball": "baseball", "bejzbol": "baseball",
    "hockey": "hockey", "ice hockey": "hockey", "hokej": "hockey",
    "tennis": "tennis", "tenis": "tennis",
    "motorsports/racing": "motorsport", "motorsport": "motorsport", "motorsports": "motorsport", "formula 1": "motorsport",
}
NORTH_AMERICA = {"US", "CA"}


@lru_cache(maxsize=1)
def data() -> dict:
    with resources.files("karte.data").joinpath("sport.toml").open("rb") as fh:
        return tomllib.load(fh)


def detect_sport(genre: str | None, country: str | None = None) -> str:
    """Iz Ticketmaster/SeatGeek žanra (npr. 'Soccer', 'Football', 'Basketball') u interni ključ."""
    g = (genre or "").strip().lower()
    if not g:
        return "other"
    if g in ("football", "american football", "nfl"):
        # Ticketmaster: 'Football' u SAD/Kanadi = američki nogomet, u Europi = nogomet
        return "american_football" if (country or "").upper() in NORTH_AMERICA or g != "football" else "football"
    if g in _GENRE_MAP:
        return _GENRE_MAP[g]
    for key, value in _GENRE_MAP.items():
        if key in g:
            return value
    return "other"


def detect_competition(event: Event) -> tuple[str, dict] | None:
    """Prepoznaj natjecanje (UEFA, FIFA, NFL u inozemstvu, NBA Europe, F1) iz naziva/lige događaja."""
    text = f" {normalize(' '.join(x for x in (event.name, event.artist, event.league or '') if x))} "
    for key, comp in data().get("competitions", {}).items():
        if comp.get("sports") and (event.sport or "other") not in comp["sports"]:
            continue
        if (event.country or "").upper() in [c.upper() for c in comp.get("exclude_countries", [])]:
            continue
        for kw in comp.get("match", []):
            k = normalize(kw)
            if k and f" {k} " in text:
                return key, comp
    return None


def football_rule(country: str | None) -> dict:
    football = data().get("football", {})
    code = (country or "").upper()
    return dict(football.get(code) or football["default"])


def rule_for(event: Event) -> dict | None:
    """Najstrože primjenjivo sportsko pravilo za događaj (ili None ako nije sport / nema posebnog pravila)."""
    if event.segment != "sport":
        return None
    candidates: list[tuple[str, dict]] = []
    comp = detect_competition(event)
    if comp:
        candidates.append((f"natjecanje:{comp[0]}", comp[1]))
    if event.sport == "football":
        candidates.append((f"nogomet:{(event.country or '').upper() or 'default'}", football_rule(event.country)))
    if not candidates:
        return None
    candidates.sort(key=lambda kv: STRICTNESS.get(kv[1].get("rule", "none"), 0), reverse=True)
    key, rule = candidates[0]
    merged = dict(rule)
    merged["key"] = key
    # kombiniraj savjete za kupnju i izvore iz svih primjenjivih pravila
    merged["how_to_buy"] = [line for _, r in candidates for line in r.get("how_to_buy", [])]
    merged["sources"] = [src for _, r in candidates for src in r.get("sources", [])]
    merged["personalized"] = any(r.get("personalized") for _, r in candidates)
    names = [r.get("name", k) for k, r in candidates]
    merged["names"] = names
    # službeni kanal: od natjecanja ako postoji, inače od nogometnog pravila
    for _, r in candidates:
        if r.get("official"):
            merged.setdefault("official", r["official"])
            merged.setdefault("official_fee", r.get("official_fee", 0.0))
            merged.setdefault("official_cap", r.get("official_cap", "face"))
            break
    return merged


def apply(legal_result: LegalResult, rule: dict, face_ref: float | None, buy_cost: float | None) -> LegalResult:
    """Spoji sportsko pravilo s općim zakonskim rezultatom (strože pobjeđuje)."""
    kind = rule.get("rule", "none")
    summary = f"{rule.get('name', 'Sport')}: {rule.get('summary', '')}"
    if legal_result.summary:
        summary += f" (Opća pravila države: {legal_result.summary})"
    changes = dict(
        summary=summary,
        risk=max(legal_result.risk, float(rule.get("risk", 0.5))),
        sources=list(dict.fromkeys(list(rule.get("sources", [])) + list(legal_result.sources))),
        sport_rule=kind,
        official_channel=rule.get("official"),
        sport_notes=list(rule.get("how_to_buy", [])),
    )
    if kind in LEGAL_RULES:
        changes.update(rule=kind, profit_prohibited=True, cap_price=face_ref if face_ref is not None else legal_result.cap_price)
    elif kind in CONTRACT_RULES:
        changes.update(contract_prohibited=True)
    return dataclasses.replace(legal_result, **changes)


def official_platform(rule: dict) -> Platform:
    """Službeni kanal (UEFA preprodaja, razmjena kluba, FIFA tržište) kao 'platforma' za izračun."""
    cap = rule.get("official_cap", "face")
    return Platform(
        key="sluzbeni_kanal",
        name=rule.get("official") or "Službena razmjena organizatora",
        url="",
        seller_fee_pct=float(rule.get("official_fee", 0.0)),
        seller_fee_fixed=0.0,
        cap=cap,
        cap_pct=0.0,
        cap_basis="face",
        reach=0.85 if rule.get("rule") == "official_marketplace" else 0.6,
        price_factor=1.0,
        trust_risk=0.05,
        countries=["*"],
        requires_vendor=None,
        payout="Prema pravilima službenog kanala.",
        notes="Jedini dopušteni kanal preprodaje za ovaj događaj.",
    )


def rules_overview(country: str | None = None) -> list[dict]:
    """Za CLI/GUI: pravila za nogomet po državama i natjecanja."""
    out = []
    football = data().get("football", {})
    codes = [country.upper()] if country else [c for c in football if c != "default"] + ["default"]
    for code in codes:
        r = football.get(code) or football["default"]
        out.append({"scope": "nogomet", "code": code, **r, "rule_label": RULE_LABELS.get(r.get("rule"), r.get("rule"))})
    if not country:
        for key, comp in data().get("competitions", {}).items():
            out.append({"scope": "natjecanje", "code": key, **comp, "rule_label": RULE_LABELS.get(comp.get("rule"), comp.get("rule"))})
    return out
