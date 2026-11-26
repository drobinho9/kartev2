"""Postavke iz okruženja i .env datoteke."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
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
    # Zamjene/dopune za Ticketmaster (vidi docs/IZVORI_PODATAKA.md)
    serpapi_key: str | None = None  # Google Events preko SerpApi (besplatno 250 pretraga/mjesec)
    serpapi_cities: str | None = None  # npr. "Zagreb, Split, Beč:AT, Budimpešta:HU"
    predicthq_token: str | None = None
    predicthq_locations: list[str] = field(default_factory=list)  # besplatni plan: ID-evi spremljenih lokacija
    api_football_key: str | None = None  # API-Football (api-sports.io): raspored HNL-a i drugih liga, besplatno 100 zahtjeva/dan
    telegram_bot_token: str | None = None  # obavijesti radara (karte radar --posalji)
    telegram_chat_id: str | None = None
    football_risk: bool = True  # utakmice koje zabranjuju samo uvjeti kluba/UEFA-e računaj uz rizik poništenja (KARTE_NOGOMET_RIZIK=0 isključuje)

    @property
    def live_sources(self) -> list[str]:
        """Izvori koji traže ključ i dohvaćaju događaje (bez Last.fm-a, koji samo obogaćuje)."""
        names = {
            "Ticketmaster": self.ticketmaster_api_key,
            "SeatGeek": self.seatgeek_client_id,
            "SerpApi (Google Events)": self.serpapi_key,
            "PredictHQ": self.predicthq_token,
        }
        return [name for name, value in names.items() if value]

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
            serpapi_key=os.environ.get("SERPAPI_KEY") or None,
            serpapi_cities=os.environ.get("KARTE_SERPAPI_GRADOVI") or None,
            predicthq_token=os.environ.get("PREDICTHQ_TOKEN") or None,
            predicthq_locations=[x.strip() for x in (os.environ.get("PREDICTHQ_LOCATIONS") or "").split(",") if x.strip()],
            api_football_key=os.environ.get("API_FOOTBALL_KEY") or None,
            telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN") or None,
            telegram_chat_id=os.environ.get("TELEGRAM_CHAT_ID") or None,
            football_risk=(os.environ.get("KARTE_NOGOMET_RIZIK") or "1").strip().lower() not in ("0", "ne", "false", "no"),
        )
