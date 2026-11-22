"""Google Events preko SerpApi – zamjena za Ticketmaster Discovery kad ključ nije odobren.

Google Events skuplja događaje sa stranica prodavača (Eventim, Entrio, Ticketmaster, Ulaznice.hr, dvorane…),
pa pokriva i Hrvatsku/regiju. Ključ: https://serpapi.com (besplatni plan: 250 pretraga mjesečno,
registracija e-mailom). Svaki grad = 1 pretraga (10 događaja) → rezultati se cacheiraju 24 h.

Ograničenja: nema nominalnih cijena (samo poveznice na prodavače) ni godine u datumu (izvodimo je),
a izvođač se izvodi iz naslova. Parser je napisan prema službenoj dokumentaciji SerpApi
(engine=google_events: title, date.start_date/when, address, venue, ticket_info) – BETA.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta

from karte.geo import CA_PROVINCES, US_STATES, country_code
from karte.models import Event
from karte.net import HttpClient, ProviderError
from karte.providers.wikipedia import MONTHS
from karte.util import normalize

BASE_URL = "https://serpapi.com/search.json"
CACHE_TTL = 24 * 3600
MAX_CITIES = 15

# Glavni gradovi po državi (za upit "concerts in <grad>"); prilagodi s --gradovi ili KARTE_SERPAPI_GRADOVI
CITIES = {
    "HR": ["Zagreb", "Split", "Pula"], "SI": ["Ljubljana"], "RS": ["Belgrade"], "BA": ["Sarajevo"], "ME": ["Podgorica"],
    "MK": ["Skopje"], "HU": ["Budapest"], "AT": ["Vienna"], "CZ": ["Prague"], "SK": ["Bratislava"], "PL": ["Warsaw", "Krakow"],
    "RO": ["Bucharest"], "BG": ["Sofia"], "GR": ["Athens"], "DE": ["Berlin", "Munich", "Hamburg", "Cologne"],
    "CH": ["Zurich"], "NL": ["Amsterdam"], "BE": ["Brussels"], "LU": ["Luxembourg"], "FR": ["Paris"], "ES": ["Madrid", "Barcelona"],
    "PT": ["Lisbon"], "IT": ["Milan", "Rome"], "GB": ["London", "Manchester"], "IE": ["Dublin"], "SE": ["Stockholm"],
    "NO": ["Oslo"], "DK": ["Copenhagen"], "FI": ["Helsinki"], "TR": ["Istanbul"], "US": ["New York", "Los Angeles"],
    "CA": ["Toronto"], "MX": ["Mexico City"], "AU": ["Sydney", "Melbourne"], "NZ": ["Auckland"], "JP": ["Tokyo"],
    "KR": ["Seoul"], "SG": ["Singapore"], "HK": ["Hong Kong"], "AE": ["Dubai"], "BR": ["Sao Paulo"], "AR": ["Buenos Aires"],
    "CL": ["Santiago"], "CO": ["Bogota"],
}
QUERIES = {"music": ["concerts in {city}"], "sport": ["sports events in {city}"], "all": ["concerts in {city}", "sports events in {city}"]}
SPORT_WORDS = re.compile(r"\b(vs\.?|v\.|fc|nk|hnk|gnk|derby|derbi|match|utakmica|league|liga|cup|kup|football|basketball|hockey)\b", re.I)
TITLE_SPLIT = re.compile(r"\s+[-–—|@]\s+|:\s+|\s+at\s+|\s+u\s+(?=[A-ZČĆŠŽĐ])")


def default_cities(countries: list[str]) -> list[tuple[str, str]]:
    """(grad, država) za zadane države – najviše MAX_CITIES (štedi besplatnu kvotu)."""
    out: list[tuple[str, str]] = []
    for code in countries or []:
        for city in CITIES.get(code.upper(), []):
            out.append((city, code.upper()))
    return out[:MAX_CITIES]


def parse_cities(value: str | list | None) -> list[tuple[str, str | None]]:
    """'Zagreb, Beč:AT, Budimpešta:HU' → [(grad, država|None)]."""
    if not value:
        return []
    items = value if isinstance(value, list) else str(value).split(",")
    out = []
    for item in items:
        if isinstance(item, tuple):
            out.append(item)
            continue
        city, _, cc = str(item).strip().partition(":")
        if city.strip():
            out.append((city.strip(), cc.strip().upper() or None))
    return out


def _start(date_info: dict, now: datetime) -> datetime | None:
    start = (date_info or {}).get("start_date") or ""
    when = (date_info or {}).get("when") or ""
    m = re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})", start) or re.search(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})", when)
    if not m or m.group(1).lower() not in MONTHS:
        m2 = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})", start or when)
        if not m2 or m2.group(2).lower() not in MONTHS:
            return None
        month, day = MONTHS[m2.group(2).lower()], int(m2.group(1))
    else:
        month, day = MONTHS[m.group(1).lower()], int(m.group(2))
    year_m = re.search(r"\b(20\d{2})\b", when)
    hour, minute = 20, 0
    t = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(?:[–\-]\s*\d{1,2}(?::\d{2})?\s*)?(AM|PM)", when, re.I)
    if t:
        hour = int(t.group(1)) % 12 + (12 if t.group(3).upper() == "PM" else 0)
        minute = int(t.group(2) or 0)
    else:
        t24 = re.search(r"\b(\d{1,2}):(\d{2})\b", when)
        if t24:
            hour, minute = int(t24.group(1)), int(t24.group(2))
    try:
        if year_m:
            return datetime(int(year_m.group(1)), month, day, hour, minute)
        candidate = datetime(now.year, month, day, hour, minute)
    except ValueError:
        return None
    if candidate < now - timedelta(days=2):  # Google ne piše godinu – "Jan 12" u studenom znači iduću godinu
        candidate = candidate.replace(year=now.year + 1)
    return candidate


def _artist_from_title(title: str) -> str:
    parts = TITLE_SPLIT.split(title or "", maxsplit=1)
    return (parts[0] if parts and parts[0].strip() else title).strip()


def _location(address: list, fallback_country: str | None) -> tuple[str, str | None, str | None]:
    """(grad, država, savezna država) iz Googleove adrese ['Arena Zagreb, Ulica…', 'Zagreb, Croatia']."""
    last = (address or [""])[-1] if address else ""
    parts = [p.strip() for p in str(last).split(",") if p.strip()]
    city = parts[0] if parts else ""
    tail = parts[-1] if len(parts) > 1 else ""
    if tail.upper() in US_STATES:
        return city, "US", tail.upper()
    if tail.upper() in CA_PROVINCES:
        return city, "CA", tail.upper()
    return city, country_code(tail) or fallback_country, None


def parse_events(data: dict, now: datetime, fallback_country: str | None = None, query: str = "") -> list[Event]:
    events: list[Event] = []
    for item in (data or {}).get("events_results") or []:
        title = (item.get("title") or "").strip()
        when = _start(item.get("date") or {}, now)
        if not title or when is None:
            continue
        city, country, region = _location(item.get("address") or [], fallback_country)
        if not country:
            continue
        venue = ((item.get("venue") or {}).get("name") or ((item.get("address") or [""])[0].split(",")[0])).strip()
        tickets = [t for t in item.get("ticket_info") or [] if isinstance(t, dict)]
        vendor_link = next((t for t in tickets if t.get("link_type") == "tickets"), tickets[0] if tickets else None)
        vendor = normalize((vendor_link or {}).get("source", "")).replace(" ", "")
        segment = "sport" if ("sports" in query or SPORT_WORDS.search(title)) else "music"
        ident = hashlib.sha1(f"{title}|{venue}|{when.isoformat()}".encode()).hexdigest()[:10]
        sources = ", ".join(sorted({t.get("source", "") for t in tickets if t.get("source")}))
        events.append(
            Event(
                id=f"gevents:{ident}",
                name=title,
                artist=_artist_from_title(title),
                venue=venue,
                city=city,
                country=country,
                date=when,
                source="Google Events (SerpApi)",
                url=(vendor_link or {}).get("link") or item.get("link"),
                status="onsale",
                primary_vendor=_vendor_key(vendor),
                notes=("Prodaja/poveznice: " + sources + ". " if sources else "")
                + "Izvođač je izveden iz naslova; nominalnu cijenu provjeri kod prodavača.",
                region=region,
                segment=segment,
            )
        )
    return events


def _vendor_key(source: str) -> str | None:
    for key in ("ticketmaster", "eventim", "entrio", "ulaznice", "seatgeek", "axs", "seetickets"):
        if key in source:
            return "ulaznice_hr" if key == "ulaznice" else key
    return None


class SerpApiProvider:
    name = "serpapi"

    def __init__(self, api_key: str, http: HttpClient):
        self.api_key = api_key
        self.http = http
        self.calls = 0
        self.warnings: list[str] = []

    def search(self, query: str, country: str | None, start: int = 0) -> dict:
        self.calls += 1
        data = self.http.get_json(
            BASE_URL,
            {"engine": "google_events", "q": query, "hl": "en", "gl": (country or "").lower() or None, "start": start or None,
             "api_key": self.api_key},
            cache_ttl=CACHE_TTL,
            cache_if=lambda d: isinstance(d, dict) and "error" not in d,
        )
        if isinstance(data, dict) and data.get("error"):
            message = str(data["error"])
            if "hasn't returned any results" in message or "no results" in message.lower():
                return {}
            raise ProviderError(message)
        return data or {}

    def events(self, cities: list[tuple[str, str | None]], now: datetime, end: datetime, segment: str = "music") -> list[Event]:
        found: list[Event] = []
        for city, country in cities:
            for template in QUERIES.get(segment, QUERIES["music"]):
                query = template.format(city=city)
                data = self.search(query, country)
                found.extend(
                    e for e in parse_events(data, now, country, query)
                    if now - timedelta(hours=6) <= e.date <= end and (segment == "all" or e.segment == segment)
                )
        if self.calls:
            self.warnings.append(
                f"SerpApi: {self.calls} upita (besplatno 250 pretraga/mjesec; isti upit unutar 24 h ide iz cachea i ne troši kvotu)."
            )
        return found
