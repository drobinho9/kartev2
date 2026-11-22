"""Učitavanje ugrađenih podataka (zakoni, platforme, dvorane, model) i korisničkih nadjačavanja."""

from __future__ import annotations

import copy
import json
import tomllib
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from karte.util import normalize


def _load_toml(name: str) -> dict[str, Any]:
    with resources.files("karte.data").joinpath(name).open("rb") as fh:
        return tomllib.load(fh)


def load_json_resource(name: str) -> Any:
    with resources.files("karte.data").joinpath(name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def deep_merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


@lru_cache(maxsize=1)
def laws() -> dict[str, Any]:
    return _load_toml("laws.toml")


@lru_cache(maxsize=1)
def platforms() -> dict[str, Any]:
    return _load_toml("platforms.toml")


@lru_cache(maxsize=1)
def vendors() -> dict[str, Any]:
    """Primarni prodavači ulaznica (vendors.toml)."""
    return _load_toml("vendors.toml")


def vendor_info(key: str | None) -> dict[str, Any]:
    return dict(vendors().get(key or "", {}))


def vendors_for_country(code: str | None) -> list[tuple[str, dict[str, Any]]]:
    """Prodavači važni u državi (redoslijed iz vendors.toml: veći prvi)."""
    code = (code or "").upper()
    return [(k, v) for k, v in vendors().items() if code in v.get("countries", [])]


def vendor_domain(key: str | None, country: str | None = None) -> str:
    info = vendors().get(key or "", {})
    return (info.get("domains") or {}).get((country or "").upper()) or info.get("domain") or ""


def vendor_key_for(text: str | None) -> str | None:
    """Prepoznaj prodavača iz naziva ili adrese ('Eventim.hr', 'www.ticketmaster.co.uk', 'See Tickets')."""
    t = normalize(text).replace(" ", "")
    if not t:
        return None
    for key, info in vendors().items():
        names = {normalize(key).replace(" ", ""), normalize(info.get("name")).replace(" ", "")}
        domains = [normalize(d).replace(" ", "") for d in [info.get("domain", ""), *(info.get("domains") or {}).values()] if d]
        if t in names or any(n and n in t for n in names if len(n) >= 6) or any(d and (d in t or (len(t) >= 6 and t in d)) for d in domains):
            return key
    return None


@lru_cache(maxsize=1)
def _venues_raw() -> dict[str, Any]:
    return _load_toml("venues.toml").get("venues", {})


@lru_cache(maxsize=1)
def _venue_index() -> dict[str, int]:
    index: dict[str, int] = {}
    for key, info in _venues_raw().items():
        cap = int(info["capacity"])
        index[normalize(key)] = cap
        for alias in info.get("aliases", []):
            index[normalize(alias)] = cap
    return index


@lru_cache(maxsize=1)
def _markets_raw() -> dict[str, Any]:
    return _load_toml("markets.toml")


def regions() -> dict[str, list[str]]:
    return dict(_markets_raw().get("regions", {}))


def markets() -> dict[str, dict]:
    return dict(_markets_raw().get("markets", {}))


def market_info(country: str | None) -> dict:
    """Veličina tržišta i dostupnost za prodavača iz HR/EU; prazno ako država nije u bazi."""
    return dict(markets().get((country or "").upper(), {}))


def expand_countries(items: list[str] | str | None) -> list[str]:
    """Pretvori popis država i/ili naziva regija (npr. 'otvoreno', 'dach', 'svijet') u ISO kodove."""
    if not items:
        return []
    if isinstance(items, str):
        items = [x for x in items.replace(";", ",").split(",")]
    presets = {k.lower(): v for k, v in regions().items()}
    out: list[str] = []
    for raw in items:
        token = raw.strip()
        if not token:
            continue
        key = token.lower().replace("-", "_").replace(" ", "_")
        codes = presets.get(key, [token.upper()])
        for code in codes:
            code = "ALL" if code.upper() in ("ALL", "SVE", "WORLD") else code.upper()
            if code not in out:
                out.append(code)
    if "ALL" in out:
        return ["ALL"]
    return out


# Procjena kapaciteta po ključnim riječima u nazivu dvorane (kad je nema u bazi)
VENUE_KEYWORDS: list[tuple[tuple[str, ...], int]] = [
    (("stadium", "stadion", "stadio", "estadio", "stade", "field", "park stadium"), 40000),
    (("hipodrom", "racecourse", "festival grounds", "showgrounds"), 30000),
    (("arena", "dome", "centre", "center", "coliseum", "forum", "palau", "palais", "halle d", "hall d"), 12000),
    (("amphitheatre", "amphitheater", "amfiteatar", "pavilion", "bowl", "open air"), 8000),
    (("sporthalle", "dvorana", "sports hall", "eventhalle", "messe"), 5000),
    (("theatre", "theater", "kazaliste", "opera", "concert hall", "konzerthaus", "philharmonie", "auditorium"), 2000),
    (("hall", "halle", "ballroom", "music hall", "o2 academy", "academy"), 2500),
    (("club", "klub", "bar", "pub", "lounge", "cafe", "kafana"), 600),
]


def estimate_capacity(venue_name: str | None) -> int | None:
    """Gruba procjena kapaciteta iz naziva dvorane (npr. '... Stadium' → 40.000)."""
    name = normalize(venue_name)
    if not name:
        return None
    for keywords, cap in VENUE_KEYWORDS:
        if any(f" {normalize(k)} " in f" {name} " for k in keywords):
            return cap
    return None


def venue_capacity(venue_name: str | None) -> int | None:
    """Pronađi približan kapacitet dvorane po nazivu (točno ili djelomično podudaranje)."""
    if not venue_name:
        return None
    name = normalize(venue_name)
    index = _venue_index()
    if name in index:
        return index[name]
    # djelomično: "Arena Zagreb, Lanište 32" ili "Wiener Stadthalle - Halle D"
    best: tuple[int, int] | None = None
    padded = f" {name} "
    for key, cap in index.items():
        if key and (f" {key} " in padded or (len(name) >= 6 and f" {name} " in f" {key} ")):
            score = len(key)
            if best is None or score > best[0]:
                best = (score, cap)
    return best[1] if best else None


class ModelConfig:
    """Parametri modela (model.toml) uz opcionalno korisničko nadjačavanje."""

    def __init__(self, data: dict[str, Any]):
        self.data = data

    @classmethod
    def load(cls, override_path: str | Path | None = None) -> "ModelConfig":
        data = _load_toml("model.toml")
        if override_path:
            with open(override_path, "rb") as fh:
                data = deep_merge(data, tomllib.load(fh))
        return cls(data)

    def section(self, name: str) -> dict[str, Any]:
        return self.data.get(name, {})

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.data.get(section, {}).get(key, default)

    def fx(self, currency: str | None) -> float:
        rates = self.section("fx")
        if not currency:
            return 1.0
        return float(rates.get(currency.upper(), 1.0))

    def to_eur(self, amount: float | None, currency: str | None) -> float | None:
        if amount is None:
            return None
        return amount * self.fx(currency)

    def known_currency(self, currency: str | None) -> bool:
        return bool(currency) and currency.upper() in self.section("fx")

    def primary_fee(self, vendor: str | None) -> tuple[float, float]:
        fees = self.section("primary_fees")
        vendors = fees.get("vendors", {})
        if vendor and vendor in vendors:
            v = vendors[vendor]
            return float(v.get("pct", 0.0)), float(v.get("fixed", 0.0))
        catalog = vendor_info(vendor)  # vendors.toml (strani prodavači)
        if catalog and "fee_pct" in catalog:
            return float(catalog.get("fee_pct", 0.0)), float(catalog.get("fee_fixed", 0.0))
        return float(fees.get("default_pct", 0.10)), float(fees.get("default_fixed", 1.0))
