"""Ticketmaster Discovery API v2 (besplatan ključ, 5000 poziva/dan, 5 zahtjeva/s).

Dokumentacija: https://developer.ticketmaster.com/products-and-docs/apis/discovery-api/v2/
Ticketmaster pokriva većinu zapadne/srednje Europe (AT, DE, PL, CZ, NL, BE, UK, IE, ES, skandinavija...).
Hrvatska, Slovenija i Srbija uglavnom nisu pokrivene – za njih koristi ručni CSV unos (Entrio, Eventim.hr, Ulaznice.hr).
"""

from __future__ import annotations

import re
from datetime import datetime

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
    )


class TicketmasterProvider:
    name = "ticketmaster"

    def __init__(self, api_key: str, http: HttpClient):
        self.api_key = api_key
        self.http = http

    def _paginate(self, params: dict) -> list[dict]:
        out: list[dict] = []
        page = 0
        while True:
            data = self.http.get_json(BASE_URL, {**params, "apikey": self.api_key, "size": PAGE_SIZE, "page": page}, cache_ttl=6 * 3600)
            out.extend(((data or {}).get("_embedded") or {}).get("events") or [])
            info = (data or {}).get("page") or {}
            total_pages = int(info.get("totalPages") or 0)
            page += 1
            if page >= total_pages or PAGE_SIZE * (page + 1) > MAX_DEEP:
                break
        return out

    def events_between(self, countries: list[str], start: datetime, end: datetime) -> list[Event]:
        """Koncerti koji se održavaju u zadanom razdoblju."""
        events: list[Event] = []
        for cc in countries:
            raws = self._paginate(
                {
                    "countryCode": cc,
                    "classificationName": "music",
                    "startDateTime": iso_z(start),
                    "endDateTime": iso_z(end),
                    "sort": "date,asc",
                    "includeTest": "no",
                }
            )
            events.extend(e for e in (parse_event(r) for r in raws) if e)
        return events

    def onsales_between(self, countries: list[str], onsale_start: datetime, onsale_end: datetime, event_end: datetime) -> list[Event]:
        """Koncerti (bilo kada do event_end) kojima prodaja počinje u zadanom razdoblju – prilika za kupnju."""
        events: list[Event] = []
        for cc in countries:
            raws = self._paginate(
                {
                    "countryCode": cc,
                    "classificationName": "music",
                    "onsaleStartDateTime": iso_z(onsale_start),
                    "onsaleEndDateTime": iso_z(onsale_end),
                    "endDateTime": iso_z(event_end),
                    "sort": "onSaleStartDate,asc",
                    "includeTest": "no",
                }
            )
            events.extend(e for e in (parse_event(r) for r in raws) if e)
        return events
