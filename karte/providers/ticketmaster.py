"""Ticketmaster Discovery API v2 (besplatan ključ, 5000 poziva/dan, 5 zahtjeva/s).

Dokumentacija: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
Pokriva SAD, Kanadu, Meksiko, Australiju, Novi Zeland, UK, Irsku i većinu zapadne/srednje Europe.
Hrvatska, Slovenija i Srbija su slabo pokrivene – za njih koristi ručni CSV unos (Entrio, Eventim.hr, Ulaznice.hr).

API vraća najviše 1000 rezultata po upitu (size × page < 1000), pa se prozor datuma rekurzivno dijeli
dok svaki dio ne stane u limit. Država "ALL" = bez filtra države (sva tržišta odjednom).
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from karte.models import Event, Presale
from karte.net import HttpClient
from karte.util import iso_z, parse_datetime

BASE_URL = "https://app.ticketmaster.com/discovery/v2/events.json"
PAGE_SIZE = 200
MAX_DEEP = 1000  # API ograničenje: size × page < 1000

PERSONALIZED_RE = re.compile(
    r"personali[sz]ed|personalisiert|name on (the )?ticket|matching (photo )?id|ID will be checked|nominativ|non-transferable",
    re.IGNORECASE,
)

STATUS_MAP = {
    "onsale": "onsale",
    "offsale": "offsale",
    "canceled": "cancelled",
    "cancelled": "cancelled",
    "postponed": "postponed",
    "rescheduled": "rescheduled",
}


def _ticket_limit(raw: dict) -> int | None:
    info = (raw.get("ticketLimit") or {}).get("info") or ""
    for match in re.findall(r"\d+", info):
        value = int(match)
        if 0 < value <= 20:
            return value
    return None


def parse_event(raw: dict) -> Event | None:
    venues = (raw.get("_embedded") or {}).get("venues") or []
    attractions = (raw.get("_embedded") or {}).get("attractions") or []
    venue = venues[0] if venues else {}
    attraction = attractions[0] if attractions else {}

    dates = raw.get("dates") or {}
    start = dates.get("start") or {}
    when = parse_datetime(start.get("dateTime")) or parse_datetime(
        f"{start.get('localDate')} {start.get('localTime', '00:00')[:5]}" if start.get("localDate") else None
    )
    if when is None:
        return None

    prices = raw.get("priceRanges") or []
    mins = [p["min"] for p in prices if p.get("min") is not None]
    maxs = [p["max"] for p in prices if p.get("max") is not None]
    currency = prices[0].get("currency", "EUR") if prices else "EUR"

    sales = raw.get("sales") or {}
    public = sales.get("public") or {}
    presales = [
        Presale(name=p.get("name", "Presale"), start=parse_datetime(p.get("startDateTime")), end=parse_datetime(p.get("endDateTime")))
        for p in sales.get("presales") or []
    ]

    status = STATUS_MAP.get(((dates.get("status") or {}).get("code") or "onsale").lower(), "onsale")
    text_blob = " ".join(str(raw.get(k, "")) for k in ("info", "pleaseNote"))
    personalized = True if PERSONALIZED_RE.search(text_blob) else None

    upcoming = (attraction.get("upcomingEvents") or {}).get("_total")
    state = (venue.get("state") or {}).get("stateCode")
    return Event(
        id=f"tm:{raw.get('id')}",
        name=raw.get("name", ""),
        artist=attraction.get("name") or raw.get("name", ""),
        venue=venue.get("name", ""),
        city=(venue.get("city") or {}).get("name", ""),
        country=((venue.get("country") or {}).get("countryCode") or "").upper(),
        date=when,
        source="ticketmaster",
        url=raw.get("url"),
        face_min=min(mins) if mins else None,
        face_max=max(maxs) if maxs else None,
        currency=currency,
        status=status,
        public_onsale=parse_datetime(public.get("startDateTime")),
        presales=presales,
        ticket_limit=_ticket_limit(raw),
        personalized=personalized,
        artist_upcoming_events=int(upcoming) if upcoming else None,
        primary_vendor="ticketmaster",
        region=state.upper() if state else None,
    )


class TicketmasterProvider:
    name = "ticketmaster"

    def __init__(self, api_key: str, http: HttpClient, min_window: timedelta = timedelta(hours=12), max_calls: int = 1500):
        self.api_key = api_key
        self.http = http
        self.min_window = min_window
        self.max_calls = max_calls
        self.calls = 0
        self.truncated = False

    def _get(self, params: dict, page: int) -> dict:
        self.calls += 1
        return self.http.get_json(BASE_URL, {**params, "apikey": self.api_key, "size": PAGE_SIZE, "page": page}, cache_ttl=6 * 3600) or {}

    def _paginate(self, params: dict, first: dict | None = None) -> list[dict]:
        out: list[dict] = []
        page = 0
        data = first if first is not None else self._get(params, 0)
        while True:
            out.extend((data.get("_embedded") or {}).get("events") or [])
            total_pages = int((data.get("page") or {}).get("totalPages") or 0)
            page += 1
            if page >= total_pages or PAGE_SIZE * (page + 1) > MAX_DEEP or self.calls >= self.max_calls:
                break
            data = self._get(params, page)
        return out

    def _window(self, base: dict, start_key: str, end_key: str, start: datetime, end: datetime) -> list[dict]:
        """Dohvati sve događaje u prozoru; ako ih je više od 1000, podijeli prozor na pola."""
        if self.calls >= self.max_calls:
            self.truncated = True
            return []
        params = {**base, start_key: iso_z(start), end_key: iso_z(end)}
        first = self._get(params, 0)
        total = int((first.get("page") or {}).get("totalElements") or 0)
        if total > MAX_DEEP and end - start > self.min_window:
            mid = start + (end - start) / 2
            return self._window(base, start_key, end_key, start, mid) + self._window(base, start_key, end_key, mid, end)
        if total > MAX_DEEP:
            self.truncated = True
        return self._paginate(params, first)

    @staticmethod
    def _country_params(cc: str) -> dict:
        params = {"classificationName": "music", "includeTest": "no", "sort": "date,asc"}
        if cc and cc.upper() != "ALL":
            params["countryCode"] = cc.upper()
        return params

    def _parse_all(self, raws: list[dict]) -> list[Event]:
        seen: set[str] = set()
        events: list[Event] = []
        for raw in raws:
            if raw.get("id") in seen:
                continue
            seen.add(raw.get("id"))
            ev = parse_event(raw)
            if ev:
                events.append(ev)
        return events

    def events_between(self, countries: list[str], start: datetime, end: datetime) -> list[Event]:
        """Koncerti koji se održavaju u zadanom razdoblju."""
        raws: list[dict] = []
        for cc in countries:
            raws.extend(self._window(self._country_params(cc), "startDateTime", "endDateTime", start, end))
        return self._parse_all(raws)

    def onsales_between(self, countries: list[str], onsale_start: datetime, onsale_end: datetime, event_end: datetime) -> list[Event]:
        """Koncerti (bilo kada do event_end) kojima prodaja počinje u zadanom razdoblju – prilika za kupnju."""
        raws: list[dict] = []
        for cc in countries:
            base = {**self._country_params(cc), "endDateTime": iso_z(event_end), "sort": "onSaleStartDate,asc"}
            raws.extend(self._window(base, "onsaleStartDateTime", "onsaleEndDateTime", onsale_start, onsale_end))
        return self._parse_all(raws)
