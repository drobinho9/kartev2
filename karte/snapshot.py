"""Snimka stvarnih događaja – zadani izvor podataka kad nema API ključeva.

Ugrađena snimka (karte/data/snimka) sadrži ručno provjerene događaje s izvorima, europske datume
velikih turneja s Wikipedije i popularnost izvođača (Deezer + Wikipedia). `karte snimka --osvjezi`
dohvaća svježe turneje i popularnost (bez ključeva) i sprema ih u korisničku mapu
(~/.karte/snimka ili KARTE_DATA_DIR/snimka) – datoteke odande imaju prednost pred ugrađenima.
"""

from __future__ import annotations

import csv
import io
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
from karte.providers.manual import load_csv_text, parse_row
from karte.providers.wikipedia import WikipediaProvider, events_from_shows, parse_tour_html, tour_artist, wiki_url
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


def _rows(text: str | None) -> list[dict]:
    if not text:
        return []
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    return [{(k or "").strip().lower(): (v or "").strip() for k, v in row.items()} for row in reader]


def _row_key(row: dict) -> str:
    return f"{normalize(row.get('izvodjac') or row.get('naziv'))}|{(row.get('datum') or '').strip()}|{normalize(row.get('grad'))}"


def load_curated() -> tuple[list[Event], str]:
    """Ugrađeni provjereni događaji + moji događaji (~/.karte/snimka/dogadaji.csv).

    Moj redak za isti događaj (izvođač + datum + grad) DOPUNJUJE ugrađeni: popunjena polja zamjenjuju ugrađena,
    a prazna zadržavaju ugrađene podatke (oznake, izvore, bilješke).
    """
    merged: dict[str, tuple[dict, str]] = {}
    for row in _rows(_read_package("dogadaji.csv")):
        merged[_row_key(row)] = (row, CURATED_SOURCE)
    user_rows = _rows(_read_user("dogadaji.csv"))
    for row in user_rows:
        key = _row_key(row)
        if key in merged:
            base, _ = merged[key]
            merged[key] = ({**base, **{k: v for k, v in row.items() if v}}, USER_SOURCE)
        else:
            merged[key] = (row, USER_SOURCE)
    events: list[Event] = []
    for row, source in merged.values():
        e = parse_row(row, source=source)
        if e is None:
            continue
        e.id = e.id.replace("csv:", "moji:" if source == USER_SOURCE else "snimka:", 1)
        events.append(e)
    origin = "ugrađena"
    if user_rows:
        origin = f"ugrađena + {user_dir() / 'dogadaji.csv'} ({len(user_rows)})"
    return events, origin


def list_user_events() -> list[dict]:
    return _rows(_read_user("dogadaji.csv"))


def _write_user_rows(rows: list[dict]) -> Path:
    target = user_dir() / "dogadaji.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    header = [h.strip() for h in CSV_HEADER.strip().split(",")]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=header, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in header})
    target.write_text(buf.getvalue(), encoding="utf-8")
    return target


def save_user_events(rows: list[dict]) -> tuple[int, int]:
    """Dodaj ili dopuni moje događaje. Vraća (dodano, dopunjeno)."""
    existing = list_user_events()
    index = {_row_key(r): i for i, r in enumerate(existing)}
    added = updated = 0
    for row in rows:
        clean = {k: str(v).strip() for k, v in row.items() if v not in (None, "") and str(v).strip()}
        when = parse_datetime(clean.get("datum"))
        if not (clean.get("izvodjac") or clean.get("naziv")) or when is None:
            continue
        clean["datum"] = when.date().isoformat()  # "12.12.2026." → "2026-12-12" (isti ključ kao ugrađeni redak)
        key = _row_key(clean)
        if key in index:
            existing[index[key]] = {**existing[index[key]], **clean}
            updated += 1
        else:
            index[key] = len(existing)
            existing.append(clean)
            added += 1
    if added or updated:
        _write_user_rows(existing)
    return added, updated


def delete_user_event(key: str) -> bool:
    rows = list_user_events()
    kept = [r for r in rows if _row_key(r) != key]
    if len(kept) == len(rows):
        return False
    _write_user_rows(kept)
    return True


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
    configured = {t.get("naslov"): t for t in meta.get("turneja", [])}
    default_region = expand_countries([meta.get("regija_otkrivanja", "europa")])
    tour_events: list[Event] = []
    for title in list(configured) + [t for t in cached if t not in configured]:
        conf = configured.get(title, {})
        entry = cached.get(title)
        if entry is None:
            warnings.append(f"Snimka: nema spremljenih datuma za turneju '{title}' – pokreni: karte snimka --osvjezi")
            continue
        artist = conf.get("izvodjac") or entry.get("izvodjac") or title
        shows = []
        for r in entry.get("koncerti") or []:
            when = parse_datetime(r.get("date"))
            if when and r.get("country"):
                shows.append({**r, "date": when.date()})
        region = expand_countries([conf["regija"]]) if conf.get("regija") else default_region
        found = events_from_shows(shows, title, artist, conf.get("oznake"), region, now)
        found_on = entry.get("otkriveno")
        is_new = bool(found_on and parse_datetime(found_on) and days_between(parse_datetime(found_on), now) <= 14)
        for e in found:
            if is_new:
                e.notes = f"NOVA turneja (otkrivena {found_on}). " + (e.notes or "")
        tour_events.extend(found)
        if found:
            info.tours.append({"artist": artist, "title": title, "url": wiki_url(title), "events": len(found),
                               "new": is_new, "discovered": title not in configured})

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


def _tour_rows(shows: list[dict], keep_countries: set[str] | None, now: datetime) -> list[dict]:
    rows = []
    for s in shows:
        if not s["country"]:
            continue
        if keep_countries is not None and (s["country"] not in keep_countries or s["date"] < now.date()):
            continue
        rows.append({"date": s["date"].isoformat(), "city": s["city"], "country": s["country"],
                     "country_name": s["country_name"], "venue": s["venue"]})
    return rows


UPCOMING_CATEGORY = "Category:Upcoming concert tours"


def refresh_snapshot(http: HttpClient, now: datetime | None = None, log=print, discover: bool = True,
                     years: list[int] | None = None) -> dict:
    """Osvježi turneje (Wikipedia) i popularnost (Deezer + Wikipedia pregledi) u korisničkoj mapi.

    discover=True: uz turneje iz snimka.toml pronađe SVE članke u kategorijama "<godina> concert tours"
    (tekuća i iduća godina) i zadrži one s budućim datumima u regiji `regija_otkrivanja` (zadano Europa).
    Nepromijenjeni članci (ista revizija) se ne dohvaćaju ponovno.
    """
    now = now or utcnow()
    target = user_dir()
    target.mkdir(parents=True, exist_ok=True)
    meta = load_meta()
    wp = WikipediaProvider(http)
    stamp = now.date().isoformat()
    summary = {"tours": [], "artists": 0, "errors": [], "dir": str(target)}

    # 1) turneje: iz snimka.toml + (opcionalno) otkrivene iz kategorija Wikipedije
    old_tours, _ = _json("turneje.json")
    old_by_title = {t.get("naslov"): t for t in old_tours.get("turneje", [])}
    # otkrivene turneje bez datuma u regiji ili bez izvođača (tribute showovi, festivali): pamti se samo revizija,
    # da se ne dohvaćaju svaki put
    old_skipped = dict(old_tours.get("preskoceno") or {})
    skipped: dict[str, int] = {}
    configured = {t.get("naslov", ""): t for t in meta.get("turneja", [])}
    keep = set(expand_countries([meta.get("regija_otkrivanja", "europa")]))
    discovered: list[str] = []
    if discover:
        categories = [f"Category:{year} concert tours" for year in years or [now.year, now.year + 1]]
        categories.append(UPCOMING_CATEGORY)  # najavljene turneje koje još nemaju kategoriju za godinu (npr. Oasis Live '27)
        for category in categories:
            try:
                discovered += wp.category_members(category)
            except ProviderError as exc:
                summary["errors"].append(f"{category}: {exc}")
        discovered = [t for t in dict.fromkeys(discovered) if t not in configured]
        log(f"  Otkriveno {len(discovered)} turneja u kategorijama Wikipedije ({', '.join(c.removeprefix('Category:') for c in categories)}).")
    try:
        revisions = wp.revisions(list(configured) + discovered)
    except ProviderError as exc:
        revisions = {}
        summary["errors"].append(f"Revizije: {exc}")
    tours_out = []
    summary["new"] = []
    for title in list(configured) + discovered:
        is_configured = title in configured
        old = old_by_title.get(title)
        rev = revisions.get(title)
        source = "popis" if is_configured else "kategorija"
        if old and rev and old.get("revid") == rev and old.get("izvor", "popis") == source:
            if old.get("koncerti"):  # članak se nije promijenio od zadnjeg dohvata
                tours_out.append(old)
            continue
        if not is_configured and not old and rev and old_skipped.get(title) == rev:
            skipped[title] = rev
            continue
        try:
            html = wp.tour_html(title)
        except ProviderError as exc:
            summary["errors"].append(f"{title}: {exc}")
            if old:
                tours_out.append(old)
            continue
        shows = parse_tour_html(html)
        rows = _tour_rows(shows, None if is_configured else keep, now)
        if not rows:
            if not is_configured and rev:
                skipped[title] = rev
            continue
        artist = configured.get(title, {}).get("izvodjac") or (old or {}).get("izvodjac") or tour_artist(html)
        if artist and not is_configured and normalize(artist) == normalize(title):
            artist = None  # "Tour by Worlds Collide Concert Tour" – show bez izvođača (franšiza, tribute)
        if not artist and not is_configured:
            if rev:
                skipped[title] = rev
            log(f"  · {title}: u infookviru nema izvođača (tribute show, festival…) – preskačem")
            continue
        artist = artist or title
        entry = {"izvodjac": artist, "naslov": title, "url": wiki_url(title), "revid": rev, "koncerti": rows,
                 # "" = turneja iz početne (ugrađene) snimke – nije "nova"; inače datum prvog otkrivanja
                 "otkriveno": old.get("otkriveno", "") if old else stamp, "izvor": source}
        if not old:
            summary["new"].append(title)
        tours_out.append(entry)
        summary["tours"].append((title, len(rows)))
        log(f"  ✓ {title} ({artist}): {len(rows)} koncerata{'' if is_configured else ' u regiji'}{' – NOVO' if not old else ''}")
    (target / "turneje.json").write_text(
        json.dumps({"azurirano": stamp, "izvor": "en.wikipedia.org (tablice 'Tour dates', CC BY-SA 4.0)", "turneje": tours_out,
                    "preskoceno": skipped}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )

    # 2) popularnost za sve izvođače iz snimke
    curated, _ = load_curated()
    artists = list(dict.fromkeys(
        [e.artist for e in curated] + [t.get("izvodjac") for t in tours_out if t.get("izvodjac")]
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
