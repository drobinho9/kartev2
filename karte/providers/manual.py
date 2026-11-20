"""Ručni unos događaja iz CSV datoteke.

Namijenjeno tržištima bez javnog API-ja (Hrvatska: Entrio, Eventim.hr, Ulaznice.hr; Slovenija, Srbija, BiH...)
i za ručno upisane cijene sa sekundarnog tržišta (npr. najniži oglas na viagogu).

Zaglavlja mogu biti na hrvatskom ili engleskom – vidi primjeri/dogadaji.csv.
"""

from __future__ import annotations

import csv
import hashlib
import io
from pathlib import Path

from karte.models import Event, Presale, SecondaryMarket
from karte.sport import detect_sport
from karte.util import normalize, parse_bool, parse_datetime, parse_float, parse_int

ALIASES = {
    "artist": ["izvodjac", "izvođač", "artist"],
    "name": ["naziv", "name", "event"],
    "venue": ["dvorana", "venue", "mjesto"],
    "city": ["grad", "city"],
    "country": ["drzava", "država", "country"],
    "region": ["regija", "savezna_drzava", "state", "region"],
    "segment": ["vrsta", "segment", "type"],
    "sport": ["sport"],
    "league": ["natjecanje", "liga", "league", "competition"],
    "date": ["datum", "date"],
    "time": ["vrijeme", "time"],
    "face_min": ["cijena_min", "face_min", "min"],
    "face_max": ["cijena_max", "face_max", "max"],
    "currency": ["valuta", "currency"],
    "status": ["status"],
    "public_onsale": ["prodaja_od", "public_onsale", "onsale"],
    "presale_name": ["presale_naziv", "presale_name"],
    "presale_start": ["presale_od", "presale_start"],
    "capacity": ["kapacitet", "capacity"],
    "ticket_limit": ["limit", "ticket_limit"],
    "personalized": ["personalizirano", "personalized"],
    "tags": ["oznake", "tags"],
    "secondary_lowest": ["sek_najniza", "sek_najniža", "secondary_lowest"],
    "secondary_median": ["sek_medijan", "secondary_median"],
    "secondary_source": ["sek_izvor", "secondary_source"],
    "listing_count": ["sek_broj_oglasa", "broj_oglasa", "listing_count"],
    "listeners": ["slusatelji", "slušatelji", "listeners"],
    "upcoming": ["broj_koncerata_turneje", "upcoming"],
    "url": ["url", "link"],
    "vendor": ["prodavac", "vendor"],
    "notes": ["biljeske", "bilješke", "notes"],
}

STATUS_ALIASES = {
    "u prodaji": "onsale",
    "prodaja": "onsale",
    "onsale": "onsale",
    "najava": "announced",
    "announced": "announced",
    "rasprodano": "soldout",
    "soldout": "soldout",
    "otkazano": "cancelled",
    "cancelled": "cancelled",
    "odgodeno": "postponed",
    "odgođeno": "postponed",
    "postponed": "postponed",
}


def _segment(value: str | None, sport_value: str | None) -> str:
    v = normalize(value or "")
    if v in ("sport", "sports", "utakmica", "nogomet", "match") or (not v and sport_value):
        return "sport"
    return "music"


def _get(row: dict[str, str], field: str) -> str | None:
    for alias in ALIASES[field]:
        if alias in row and row[alias] not in (None, ""):
            return row[alias].strip()
    return None


def parse_row(row: dict[str, str], source: str = "ručni unos") -> Event | None:
    row = {(k or "").strip().lower(): (v or "") for k, v in row.items()}
    artist = _get(row, "artist")
    date_str = _get(row, "date")
    if not artist or not date_str:
        return None
    time_str = _get(row, "time")
    when = parse_datetime(f"{date_str} {time_str}" if time_str else date_str)
    if when is None:
        return None
    tags = [t.strip().lower() for t in (_get(row, "tags") or "").replace(";", "|").replace(",", "|").split("|") if t.strip()]
    lowest = parse_float(_get(row, "secondary_lowest"))
    median = parse_float(_get(row, "secondary_median"))
    currency = (_get(row, "currency") or "EUR").upper()
    secondary = None
    if lowest or median:
        secondary = SecondaryMarket(
            source=_get(row, "secondary_source") or "ručni unos",
            lowest=lowest,
            median=median,
            currency=currency,
            listing_count=parse_int(_get(row, "listing_count")),
        )
    presales = []
    if _get(row, "presale_start"):
        presales.append(Presale(name=_get(row, "presale_name") or "Presale", start=parse_datetime(_get(row, "presale_start"))))
    status_raw = normalize(_get(row, "status") or "onsale")
    status = STATUS_ALIASES.get(status_raw, STATUS_ALIASES.get(_get(row, "status") or "", "onsale"))
    venue = _get(row, "venue") or ""
    country = (_get(row, "country") or "HR").upper()
    ident = hashlib.sha1(f"{artist}|{venue}|{when.isoformat()}".encode()).hexdigest()[:10]
    return Event(
        id=f"csv:{ident}",
        name=_get(row, "name") or artist,
        artist=artist,
        venue=venue,
        city=_get(row, "city") or "",
        country=country,
        date=when,
        source=source,
        url=_get(row, "url"),
        face_min=parse_float(_get(row, "face_min")),
        face_max=parse_float(_get(row, "face_max")),
        currency=currency,
        status=status,
        public_onsale=parse_datetime(_get(row, "public_onsale")),
        presales=presales,
        capacity=parse_int(_get(row, "capacity")),
        ticket_limit=parse_int(_get(row, "ticket_limit")),
        personalized=parse_bool(_get(row, "personalized")),
        tags=tags,
        secondary=secondary,
        artist_listeners=parse_int(_get(row, "listeners")),
        artist_upcoming_events=parse_int(_get(row, "upcoming")),
        primary_vendor=(_get(row, "vendor") or "").lower() or None,
        notes=_get(row, "notes"),
        region=(_get(row, "region") or "").upper() or None,
        segment=_segment(_get(row, "segment"), _get(row, "sport")),
        sport=detect_sport(_get(row, "sport"), country) if _segment(_get(row, "segment"), _get(row, "sport")) == "sport" else None,
        league=_get(row, "league"),
    )


def _read(fh, name: str) -> list[Event]:
    sample = fh.read(4096)
    fh.seek(0)
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(fh, dialect=dialect)
    return [e for e in (parse_row(r, source=f"CSV ({name})") for r in reader) if e]


def load_csv(path: str | Path) -> list[Event]:
    path = Path(path)
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        return _read(fh, path.name)


def load_csv_text(text: str, name: str = "upload") -> list[Event]:
    """CSV iz teksta (npr. datoteka učitana u grafičkom sučelju)."""
    return _read(io.StringIO(text.lstrip("\ufeff")), name)
