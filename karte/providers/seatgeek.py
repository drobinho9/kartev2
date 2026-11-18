"""SeatGeek Platform API – događaji sa statistikom sekundarnog tržišta (najniža/medijan/prosjek, broj oglasa).

Dokumentacija: https://platform.seatgeek.com/  (besplatan client_id; pokrivenost uglavnom SAD/Kanada/UK).
Koristi se primarno za obogaćivanje drugih događaja stvarnim cijenama sa sekundarnog tržišta.
"""

from __future__ import annotations

from datetime import datetime

from karte.models import Event, SecondaryMarket
from karte.net import HttpClient
from karte.util import parse_datetime

BASE_URL = "https://api.seatgeek.com/2/events"
PER_PAGE = 100
MAX_PAGES = 10


def parse_event(raw: dict) -> Event | None:
    when = parse_datetime(raw.get("datetime_local")) or parse_datetime(raw.get("datetime_utc"))
    if when is None:
        return None
    performers = raw.get("performers") or []
    primary = next((p for p in performers if p.get("primary")), performers[0] if performers else {})
    venue = raw.get("venue") or {}
    stats = raw.get("stats") or {}
    secondary = None
    if any(stats.get(k) for k in ("lowest_price", "median_price", "average_price")):
        secondary = SecondaryMarket(
            source="seatgeek",
            lowest=stats.get("lowest_price"),
            median=stats.get("median_price"),
            average=stats.get("average_price"),
            listing_count=stats.get("listing_count"),
            currency="USD",
        )
    capacity = venue.get("capacity") or None
    return Event(
        id=f"sg:{raw.get('id')}",
        name=raw.get("title") or raw.get("short_title") or "",
        artist=primary.get("name") or raw.get("title") or "",
        venue=venue.get("name", ""),
        city=venue.get("city", ""),
        country=(venue.get("country") or "").upper(),
        date=when,
        source="seatgeek",
        url=raw.get("url"),
        currency="USD",
        capacity=int(capacity) if capacity else None,
        secondary=secondary,
        primary_vendor="seatgeek",
    )


class SeatGeekProvider:
    name = "seatgeek"

    def __init__(self, client_id: str, http: HttpClient):
        self.client_id = client_id
        self.http = http

    def events_between(self, countries: list[str], start: datetime, end: datetime) -> list[Event]:
        events: list[Event] = []
        for cc in countries:
            for page in range(1, MAX_PAGES + 1):
                data = self.http.get_json(
                    BASE_URL,
                    {
                        "client_id": self.client_id,
                        "taxonomies.name": "concert",
                        "venue.country": cc,
                        "datetime_utc.gte": start.strftime("%Y-%m-%dT%H:%M:%S"),
                        "datetime_utc.lte": end.strftime("%Y-%m-%dT%H:%M:%S"),
                        "per_page": PER_PAGE,
                        "page": page,
                    },
                    cache_ttl=3 * 3600,
                )
                raws = (data or {}).get("events") or []
                events.extend(e for e in (parse_event(r) for r in raws) if e)
                total = ((data or {}).get("meta") or {}).get("total") or 0
                if page * PER_PAGE >= total or not raws:
                    break
        return events
