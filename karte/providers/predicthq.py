"""PredictHQ – baza događaja (koncerti, sport…) s procjenom posjećenosti (phq_attendance) i rangom utjecaja.

Ključ (access token): https://control.predicthq.com → 14 dana probnog pristupa cijelom API-ju, zatim besplatni plan
koji radi samo sa spremljenim lokacijama (Location Insights) → postavi PREDICTHQ_LOCATIONS=id1,id2.
Plaćeni planovi su skupi (okvirno od ~500 $/god.) – isplati se tek uz ozbiljniji obim.

Korisno za: otkrivanje događaja po državama i procjenu kapaciteta (phq_attendance ≈ očekivana publika).
Nema nominalnih cijena. Parser prema službenoj dokumentaciji (/v1/events: title, category, start, country,
entities, phq_attendance, rank, labels, state) – BETA.
"""

from __future__ import annotations

from datetime import datetime

from karte.models import Event
from karte.net import HttpClient, ProviderError
from karte.providers.serpapi import _artist_from_title
from karte.sport import detect_sport
from karte.util import iso_z, parse_datetime

BASE_URL = "https://api.predicthq.com/v1/events/"
CACHE_TTL = 12 * 3600
CATEGORIES = {"music": "concerts", "sport": "sports", "all": "concerts,sports"}
STATUS = {"active": "onsale", "predicted": "announced", "cancelled": "cancelled", "postponed": "postponed", "deleted": "cancelled"}
MAX_PAGES = 5


def parse_events(data: dict) -> list[Event]:
    events: list[Event] = []
    for item in (data or {}).get("results") or []:
        when = parse_datetime(item.get("start"))
        title = (item.get("title") or "").strip()
        country = (item.get("country") or "").upper()
        if not when or not title or not country:
            continue
        entities = [e for e in item.get("entities") or [] if isinstance(e, dict)]
        venue = next((e for e in entities if e.get("type") == "venue"), {})
        address = venue.get("formatted_address") or ""
        city = ""
        if address:
            parts = [p.strip() for p in address.split("\n") if p.strip()] or [address]
            city = parts[-2].split(",")[0] if len(parts) >= 2 else parts[0].split(",")[0]
        labels = [str(x) for x in item.get("labels") or []]
        labels += [str(x.get("label")) for x in item.get("phq_labels") or [] if isinstance(x, dict) and x.get("label")]
        segment = "sport" if item.get("category") == "sports" else "music"
        attendance = item.get("phq_attendance")
        rank = item.get("rank")
        notes = "Izvođač izveden iz naslova (PredictHQ)."
        if rank is not None:
            notes += f" PredictHQ rang utjecaja: {rank}/100."
        events.append(
            Event(
                id=f"phq:{item.get('id')}",
                name=title,
                artist=_artist_from_title(title),
                venue=venue.get("name") or "",
                city=city,
                country=country,
                date=when,
                source="PredictHQ",
                status=STATUS.get(item.get("state") or "active", "onsale"),
                capacity=int(attendance) if attendance else None,
                capacity_estimated=bool(attendance),
                notes=notes,
                segment=segment,
                sport=detect_sport(" ".join(labels).replace("-", " "), country) if segment == "sport" else None,
                tags=["playoff"] if segment == "sport" and any(x in ("playoff", "final") for x in labels) else [],
            )
        )
    return events


class PredictHQProvider:
    name = "predicthq"

    def __init__(self, token: str, http: HttpClient, locations: list[str] | None = None):
        self.token = token
        self.http = http
        self.locations = [x for x in (locations or []) if x]

    def _get(self, params: dict) -> list[Event]:
        events: list[Event] = []
        offset = 0
        for _ in range(MAX_PAGES):
            data = self.http.get_json(
                BASE_URL,
                {**params, "limit": 100, "offset": offset or None},
                cache_ttl=CACHE_TTL,
                headers={"Authorization": f"Bearer {self.token}"},
            )
            if isinstance(data, dict) and data.get("error"):
                raise ProviderError(str(data.get("error")))
            events.extend(parse_events(data))
            if not (data or {}).get("next"):
                break
            offset += 100
        return events

    def events(self, countries: list[str], start: datetime, end: datetime, segment: str = "music") -> list[Event]:
        base = {
            "category": CATEGORIES.get(segment, "concerts"),
            "active.gte": iso_z(start),
            "active.lte": iso_z(end),
            "sort": "-phq_attendance",
            "state": "active,predicted,postponed",
        }
        if self.locations:  # besplatni plan: samo spremljene lokacije
            out: list[Event] = []
            for loc in self.locations:
                out.extend(self._get({**base, "saved_location.location_id": loc}))
            return out
        codes = [c for c in countries if c and c.upper() != "ALL"]
        if codes:
            base["country"] = ",".join(codes)
        return self._get(base)
