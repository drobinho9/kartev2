"""Demo podaci – IZMIŠLJENI izvođači i cijene, za isprobavanje bez API ključeva.

Datumi su relativni u odnosu na trenutak pokretanja, pa demo uvijek izgleda aktualno.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from karte.knowledge import load_json_resource
from karte.models import Event, Presale, SecondaryMarket
from karte.util import utcnow


def _at(now: datetime, days: float | None, time: str = "20:00") -> datetime | None:
    if days is None:
        return None
    hour, minute = (int(x) for x in time.split(":"))
    base = (now + timedelta(days=days)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return base


def load_demo(now: datetime | None = None) -> list[Event]:
    now = now or utcnow()
    events: list[Event] = []
    for i, d in enumerate(load_json_resource("demo_events.json")["events"]):
        sec = d.get("secondary")
        events.append(
            Event(
                id=f"demo:{i}",
                name=d.get("name") or d["artist"],
                artist=d["artist"],
                venue=d["venue"],
                city=d["city"],
                country=d["country"],
                date=_at(now, d["days"], d.get("time", "20:00")),
                source="demo",
                url=None,
                face_min=d.get("face_min"),
                face_max=d.get("face_max"),
                currency=d.get("currency", "EUR"),
                status=d.get("status", "onsale"),
                public_onsale=_at(now, d.get("onsale_days"), d.get("onsale_time", "10:00")),
                presales=[
                    Presale(name=p["name"], start=_at(now, p["start_days"], p.get("time", "10:00")), end=_at(now, p.get("end_days"), "22:00"))
                    for p in d.get("presales", [])
                ],
                capacity=d.get("capacity"),
                ticket_limit=d.get("ticket_limit"),
                personalized=d.get("personalized"),
                tags=list(d.get("tags", [])),
                secondary=SecondaryMarket(**sec) if sec else None,
                artist_listeners=d.get("listeners"),
                artist_upcoming_events=d.get("upcoming"),
                primary_vendor=d.get("vendor"),
                notes=d.get("notes"),
            )
        )
    return events
