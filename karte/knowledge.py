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
    for key, cap in index.items():
        if key and (key in name or name in key):
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
        return float(fees.get("default_pct", 0.10)), float(fees.get("default_fixed", 1.0))
