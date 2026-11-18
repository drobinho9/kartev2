"""Postavke iz okruženja i .env datoteke."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Zadano: regija "otvoreno" (tržišta bez zakonskog limita cijene i dostupna iz HR) – vidi karte/data/markets.toml
DEFAULT_COUNTRIES = ["otvoreno"]


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimalni .env parser (KLJUČ=vrijednost); ne prepisuje postojeće varijable."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _split_countries(value: str | None) -> list[str]:
    if not value:
        return list(DEFAULT_COUNTRIES)
    return [c.strip() for c in value.split(",") if c.strip()]


@dataclass
class Settings:
    ticketmaster_api_key: str | None
    seatgeek_client_id: str | None
    lastfm_api_key: str | None
    countries: list[str]
    budget: float
    cache_dir: Path
    seller_country: str = "HR"

    @classmethod
    def from_env(cls, dotenv: str | Path | None = ".env") -> "Settings":
        if dotenv:
            load_dotenv(dotenv)
        cache_dir = Path(os.environ.get("KARTE_CACHE_DIR") or Path.home() / ".cache" / "karte")
        try:
            budget = float(os.environ.get("KARTE_BUDGET") or 1000)
        except ValueError:
            budget = 1000.0
        return cls(
            ticketmaster_api_key=os.environ.get("TICKETMASTER_API_KEY") or None,
            seatgeek_client_id=os.environ.get("SEATGEEK_CLIENT_ID") or None,
            lastfm_api_key=os.environ.get("LASTFM_API_KEY") or None,
            countries=_split_countries(os.environ.get("KARTE_COUNTRIES")),
            budget=budget,
            cache_dir=cache_dir,
            seller_country=(os.environ.get("KARTE_SELLER_COUNTRY") or "HR").upper(),
        )
