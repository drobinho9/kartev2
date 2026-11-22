"""Snimka stvarnih događaja – zadani izvor podataka kad nema API ključeva.

Ugrađena snimka (karte/data/snimka) sadrži ručno provjerene događaje s izvorima, europske datume
velikih turneja s Wikipedije i popularnost izvođača (Deezer + Wikipedia). `karte snimka --osvjezi`
dohvaća svježe turneje i popularnost (bez ključeva) i sprema ih u korisničku mapu
(~/.karte/snimka ili KARTE_DATA_DIR/snimka) – datoteke odande imaju prednost pred ugrađenima.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field
from datetime import datetime
from importlib import resources
from pathlib import Path

from karte.knowledge import expand_countries
from karte.models import Event
from karte.net import HttpClient, ProviderError
from karte.providers.deezer import DeezerProvider
from karte.providers.manual import load_csv_text
from karte.providers.wikipedia import WikipediaProvider, events_from_shows, parse_tour_html, wiki_url
from karte.util import days_between, normalize, parse_datetime, utcnow

FILES = ("snimka.toml", "dogadaji.csv", "turneje.json", "popularnost.json")
CURATED_SOURCE = "Snimka – provjereni izvori"
USER_SOURCE = "Snimka – moji događaji"
CSV_HEADER = (
    "izvodjac,naziv,dvorana,grad,drzava,datum,vrijeme,cijena_min,cijena_max,valuta,status,prodaja_od,kapacitet,limit,"
    "personalizirano,oznake,sek_najniza,sek_medijan,sek_izvor,sek_valuta,sek_datum,prodavac,url,biljeske\n"
)


def data_dir() -> Path:
    return Path(os.environ.get("KARTE_DATA_DIR") or (Path.home() / ".karte"))


def user_dir() -> Path:
    return data_dir() / "snimka"


def _package_file(name: str):
    return resources.files("karte.data").joinpath("snimka", name)


def _read_user(name: str) -> str | None:
    path = user_dir() / name
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else None
    except OSError:
        return None


def _read_package(name: str) -> str | None:
    try:
        return _package_file(name).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return None


def read_file(name: str) -> tuple[str | None, str]:
    """(sadržaj, porijeklo) – korisnička datoteka ako postoji, inače ugrađena."""
    user = _read_user(name)
    if user is not None:
        return user, str(user_dir() / name)
    pkg = _read_package(name)
    return (pkg, "ugrađena") if pkg is not None else (None, "—")


def _parse_json(text: str | None) -> dict:
    try:
        return json.loads(text) if text else {}
    except ValueError:
        return {}


def _json(name: str) -> tuple[dict, str]:
    """Novija od korisničke (osvježene) i ugrađene verzije – prema polju 'azurirano'."""
    user, pkg = _parse_json(_read_user(name)), _parse_json(_read_package(name))
    if user and (not pkg or str(user.get("azurirano", "")) >= str(pkg.get("azurirano", ""))):
        return user, str(user_dir() / name)
    return pkg, "ugrađena"


def _key(e: Event) -> str:
    return f"{normalize(e.artist)}|{e.date.date().isoformat()}|{normalize(e.city)}"


def load_curated() -> tuple[list[Event], str]:
    """Ugrađeni provjereni događaji + korisnikovi (~/.karte/snimka/dogadaji.csv); korisnički redak zamjenjuje isti događaj."""
    merged: dict[str, Event] = {}
    pkg_text = _read_package("dogadaji.csv")
    for e in load_csv_text(pkg_text, "snimka") if pkg_text else []:
        e.source = CURATED_SOURCE
        e.id = e.id.replace("csv:", "snimka:", 1)
        merged[_key(e)] = e
    origin = "ugrađena"
    user_text = _read_user("dogadaji.csv")
    user_events = load_csv_text(user_text, "moji") if user_text else []
    for e in user_events:
        e.source = USER_SOURCE
        e.id = e.id.replace("csv:", "moji:", 1)
        merged[_key(e)] = e
    if user_events:
        origin = f"ugrađena + {user_dir() / 'dogadaji.csv'} ({len(user_events)})"
    return list(merged.values()), origin


@dataclass
class SnapshotInfo:
    date: str  # stanje provjerenih podataka (YYYY-MM-DD)
    description: str
    curated: int = 0
    tour_events: int = 0
    tours: list[dict] = field(default_factory=list)
    popularity_date: str | None = None
    tours_date: str | None = None
    origin: str = "ugrađena"

    def age_days(self, now: datetime | None = None) -> int | None:
        when = parse_datetime(self.date)
        return days_between(when, now or utcnow()) if when else None

    @property
    def date_hr(self) -> str:
        when = parse_datetime(self.date)
        return when.strftime("%d.%m.%Y.") if when else self.date

    def as_dict(self, now: datetime | None = None) -> dict:
        return {
            "date": self.date,
            "date_hr": self.date_hr,
            "age_days": self.age_days(now),
            "description": self.description,
            "curated": self.curated,
            "tour_events": self.tour_events,
            "tours": self.tours,
            "popularity_date": self.popularity_date,
            "tours_date": self.tours_date,
            "origin": self.origin,
        }


def load_meta() -> dict:
    text, _ = read_file("snimka.toml")
    return tomllib.loads(text) if text else {}


def apply_popularity(events: list[Event], popularity: dict) -> None:
    """Upiši Deezer fanove i Wikipedia trend iz popularnost.json (ne prepisuje postojeće vrijednosti)."""
    by_name = {normalize(name): info for name, info in (popularity.get("izvodjaci") or {}).items()}
    for e in events:
        info = by_name.get(normalize(e.artist))
        if not info:
            continue
        if not e.artist_fans and info.get("deezer_fanovi"):
            e.artist_fans = int(info["deezer_fanovi"])
        if e.artist_trend is None and info.get("trend") is not None:
            e.artist_trend = float(info["trend"])
        if e.artist_pageviews is None and info.get("pregledi_dnevno") is not None:
            e.artist_pageviews = int(info["pregledi_dnevno"])


def load_snapshot(now: datetime | None = None, countries: list[str] | None = None) -> tuple[list[Event], SnapshotInfo, list[str]]:
    """Događaji iz snimke (provjereni + turneje), s popularnošću. countries=None ili ['ALL'] → bez filtra."""
    now = now or utcnow()
    warnings: list[str] = []
    meta = load_meta()
    info = SnapshotInfo(date=str(meta.get("stanje", "")), description=meta.get("opis", ""))

    curated, info.origin = load_curated()

    tours_data, _ = _json("turneje.json")
    info.tours_date = tours_data.get("azurirano")
    cached = {t.get("naslov"): t for t in tours_data.get("turneje", [])}
    tour_events: list[Event] = []
    for tour in meta.get("turneja", []):
        title, artist = tour.get("naslov", ""), tour.get("izvodjac", "")
        rows = cached.get(title, {}).get("koncerti")
        if rows is None:
            warnings.append(f"Snimka: nema spremljenih datuma za turneju '{title}' – pokreni: karte snimka --osvjezi")
            continue
        shows = []
        for r in rows:
            when = parse_datetime(r.get("date"))
            if when:
                shows.append({**r, "date": when.date()})
        region = expand_countries([tour["regija"]]) if tour.get("regija") else None
        found = events_from_shows(shows, title, artist, tour.get("oznake"), region, now)
        tour_events.extend(found)
        info.tours.append({"artist": artist, "title": title, "url": wiki_url(title), "events": len(found)})

    events = curated + tour_events
    popularity, _ = _json("popularnost.json")
    info.popularity_date = popularity.get("azurirano")
    apply_popularity(events, popularity)

    wanted = {c.upper() for c in (countries or [])} - {"ALL"}
    if wanted:
        events = [e for e in events if e.country in wanted]
    events = [e for e in events if e.date >= now.replace(hour=0, minute=0, second=0, microsecond=0)]
    info.curated = sum(1 for e in events if e.source in (CURATED_SOURCE, USER_SOURCE))
    info.tour_events = len(events) - info.curated
    return events, info, warnings


def refresh_snapshot(http: HttpClient, now: datetime | None = None, log=print) -> dict:
    """Osvježi turneje (Wikipedia) i popularnost (Deezer + Wikipedia pregledi) u korisničkoj mapi."""
    now = now or utcnow()
    target = user_dir()
    target.mkdir(parents=True, exist_ok=True)
    meta = load_meta()
    wp = WikipediaProvider(http)
    stamp = now.date().isoformat()
    summary = {"tours": [], "artists": 0, "errors": [], "dir": str(target)}

    # 1) turneje
    old_tours, _ = _json("turneje.json")
    old_by_title = {t.get("naslov"): t for t in old_tours.get("turneje", [])}
    tours_out = []
    for tour in meta.get("turneja", []):
        title = tour.get("naslov", "")
        try:
            shows = parse_tour_html(wp.tour_html(title))
            rows = [{"date": s["date"].isoformat(), "city": s["city"], "country": s["country"], "country_name": s["country_name"],
                     "venue": s["venue"]} for s in shows if s["country"]]
            tours_out.append({"izvodjac": tour.get("izvodjac"), "naslov": title, "url": wiki_url(title), "koncerti": rows})
            summary["tours"].append((title, len(rows)))
            log(f"  ✓ {title}: {len(rows)} koncerata")
        except ProviderError as exc:
            summary["errors"].append(f"{title}: {exc}")
            log(f"  ✗ {title}: {exc} (ostaje prethodna verzija)")
            if title in old_by_title:
                tours_out.append(old_by_title[title])
    (target / "turneje.json").write_text(
        json.dumps({"azurirano": stamp, "izvor": "en.wikipedia.org (tablice 'Tour dates', CC BY-SA 4.0)", "turneje": tours_out},
                   ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    # 2) popularnost za sve izvođače iz snimke
    curated, _ = load_curated()
    artists = list(dict.fromkeys(
        [e.artist for e in curated] + [t.get("izvodjac") for t in meta.get("turneja", []) if t.get("izvodjac")]
    ))
    deezer = DeezerProvider(http)
    old_pop, _ = _json("popularnost.json")
    pop = dict(old_pop.get("izvodjaci") or {})
    try:
        titles = wp.resolve_titles(artists)
    except ProviderError as exc:
        titles = {}
        summary["errors"].append(f"Wikipedia naslovi: {exc}")
    for artist in artists:
        entry = dict(pop.get(artist) or {})
        try:
            found = deezer.lookup(artist)
            if found:
                entry.update({"deezer_fanovi": found["fans"], "deezer_id": found["id"]})
        except ProviderError as exc:
            summary["errors"].append(f"Deezer {artist}: {exc}")
        title = titles.get(artist)
        if title:
            entry["wikipedia"] = title
            try:
                avg, ratio = wp.trend(title, now)
                entry.update({"pregledi_dnevno": avg, "trend": ratio})
            except ProviderError as exc:
                summary["errors"].append(f"Wikimedia {artist}: {exc}")
        pop[artist] = entry
        log(f"  · {artist}: Deezer {entry.get('deezer_fanovi', '—')} fanova, trend {entry.get('trend', '—')}")
    summary["artists"] = len(artists)
    (target / "popularnost.json").write_text(
        json.dumps({"azurirano": stamp, "izvor": "api.deezer.com (nb_fan) + wikimedia.org (pregledi, zadnjih 14 / prethodnih 60 dana)",
                    "izvodjaci": pop}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    # 3) predložak za vlastite događaje (dopunjuju ugrađenu snimku; isti događaj u njemu zamjenjuje ugrađeni)
    own = target / "dogadaji.csv"
    if not own.exists():
        own.write_text(CSV_HEADER, encoding="utf-8")
    return summary
