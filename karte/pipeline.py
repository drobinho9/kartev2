"""Orkestracija pretrage: dohvat događaja → spajanje → obogaćivanje → procjena → savjeti."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from karte.advisor import build_advice
from karte.knowledge import ModelConfig, estimate_capacity, expand_countries, venue_capacity
from karte.models import Event, Opportunity
from karte.net import FileCache, HttpClient, ProviderError
from karte.providers.deezer import DeezerProvider
from karte.providers.demo import load_demo
from karte.providers.lastfm import LastFmProvider
from karte.providers.manual import load_csv, load_csv_text
from karte.providers.predicthq import PredictHQProvider
from karte.providers.seatgeek import SeatGeekProvider
from karte.providers.serpapi import SerpApiProvider, default_cities, parse_cities
from karte.providers.ticketmaster import TicketmasterProvider
from karte.providers.wikipedia import WikipediaProvider
from karte.scoring import Evaluator, sort_key
from karte.settings import Settings
from karte.snapshot import load_snapshot
from karte.util import hr_plural, normalize, utcnow


@dataclass
class ScanOptions:
    days: int = 60
    onsale_days: int = 30
    onsale_horizon_days: int = 365
    countries: list[str] = field(default_factory=list)
    budget: float = 1000.0
    category: str = "cheap"
    strict: bool = False
    demo: bool = False
    manual_files: list[str] = field(default_factory=list)
    csv_texts: list[tuple[str, str]] = field(default_factory=list)  # (naziv, sadržaj) – iz grafičkog sučelja
    use_lastfm: bool = True
    use_seatgeek: bool = True
    include_far_onsales: bool = True
    model_path: str | None = None
    now: datetime | None = None
    seller_country: str = "HR"
    max_artists: int = 300
    show_all: bool = False
    segment: str = "music"  # "music" (koncerti) | "sport" | "all"
    snapshot: bool = False  # snimka stvarnih događaja (bez ključeva) umjesto živih API-ja
    use_deezer: bool = True  # popularnost iz Deezera (bez ključa) kad nema Last.fm podatka
    use_wikipedia: bool = True  # trend pregleda na Wikipediji (bez ključa)
    trend_artists: int = 40  # za koliko izvođača dohvatiti trend (svaki je jedan zahtjev)
    serpapi_cities: list[str] = field(default_factory=list)  # gradovi za Google Events (SerpApi); prazno = zadani za države


@dataclass
class ScanResult:
    opportunities: list[Opportunity]
    warnings: list[str]
    sources: list[str]
    generated_at: datetime
    options: ScanOptions
    is_demo: bool
    is_snapshot: bool = False
    snapshot: dict | None = None  # podaci o snimci (stanje, broj događaja, turneje)
    evaluator: Evaluator | None = None  # isti model kojim su procijenjeni događaji (za plan zarade)


def event_key(e: Event) -> str:
    return f"{normalize(e.artist)}|{e.date.date().isoformat()}|{normalize(e.city)}"


def merge_events(events: list[Event]) -> list[Event]:
    """Spoji duplikate iz više izvora (isti izvođač, dan i grad); popuni prazna polja."""
    merged: dict[str, Event] = {}
    for e in events:
        key = event_key(e)
        if key not in merged:
            merged[key] = e
            continue
        base = merged[key]
        # Ticketmaster/CSV imaju nominalne cijene – neka budu osnova
        if not base.has_face_value and e.has_face_value:
            base, e = e, base
            merged[key] = base
        for attr in (
            "face_min", "face_max", "public_onsale", "capacity", "ticket_limit", "personalized",
            "secondary", "artist_listeners", "artist_upcoming_events", "url", "primary_vendor",
        ):
            if getattr(base, attr) in (None, [], "") and getattr(e, attr) not in (None, [], ""):
                setattr(base, attr, getattr(e, attr))
        if not base.presales and e.presales:
            base.presales = e.presales
        base.tags = sorted(set(base.tags) | set(e.tags))
    return list(merged.values())


def annotate_supply(events: list[Event]) -> None:
    """Broj koncerata istog izvođača u istoj državi (ponuda) i kapacitet dvorane."""
    counts = Counter((normalize(e.artist), e.country) for e in events if e.status not in ("cancelled",))
    for e in events:
        e.shows_in_region = max(e.shows_in_region, counts.get((normalize(e.artist), e.country), 1))
        if not e.capacity:
            cap = venue_capacity(e.venue) or estimate_capacity(e.venue)
            if cap:
                e.capacity = cap
                e.capacity_estimated = True


DISCOVERY_SOURCES = ("CSV", "Google Events", "PredictHQ")

TM_CLASSIFICATIONS = {
    "music": [("music", "koncerti")],
    "sport": [("sports", "sport")],
    "all": [("music", "koncerti"), ("sports", "sport")],
}
SG_TAXONOMIES = {"music": ["concert"], "sport": ["sports"], "all": ["concert", "sports"]}


def enrichment_targets(events: list[Event], max_artists: int) -> list[Event]:
    """Odaberi događaje za Last.fm obogaćivanje: prvo oni s cijenom, pa po najvišoj cijeni (signal veličine izvođača)."""
    config = ModelConfig.load()

    def priority(e: Event) -> tuple:
        top = config.to_eur(e.face_max or e.face_min, e.currency) or 0.0
        return (e.has_face_value or e.secondary is not None, e.secondary is not None, top, e.capacity or 0)

    chosen: list[str] = []
    for e in sorted(events, key=priority, reverse=True):
        key = normalize(e.artist)
        if key and key not in chosen:
            chosen.append(key)
        if len(chosen) >= max_artists:
            break
    wanted = set(chosen)
    return [e for e in events if normalize(e.artist) in wanted]


def collect_events(
    opts: ScanOptions, settings: Settings, http: HttpClient | None = None, meta: dict | None = None
) -> tuple[list[Event], list[str], list[str]]:
    now = opts.now or utcnow()
    warnings: list[str] = []
    sources: list[str] = []
    events: list[Event] = []
    opts.countries = expand_countries(opts.countries) or ["ALL"]
    live = not (opts.demo or opts.snapshot)

    if opts.demo:
        events.extend(e for e in load_demo(now) if opts.segment == "all" or e.segment == opts.segment)
        sources.append("demo (izmišljeni podaci)")

    if opts.snapshot:
        snap, info, snap_warnings = load_snapshot(now, opts.countries)
        warnings.extend(snap_warnings)
        chosen = [e for e in snap if opts.segment == "all" or e.segment == opts.segment]
        events.extend(chosen)
        if meta is not None:
            meta["snapshot"] = info.as_dict(now)
        sources.append(
            f"Snimka stvarnih događaja (stanje {info.date_hr}: {info.curated} provjerenih + {info.tour_events} "
            f"{hr_plural(info.tour_events, 'datum', 'datuma')} turneja s Wikipedije)"
        )
        age = info.age_days(now)
        if age is not None and age > 30:
            warnings.append(
                f"Snimka je stara {age} dana – osvježi turneje i popularnost (karte snimka --osvjezi) i provjeri cijene kod prodavača."
            )
        if opts.segment == "sport" and not chosen:
            warnings.append(
                "Snimka zasad nema sportskih događaja s potvrđenim datumom i cijenom – za utakmice koristi Kalkulator ili CSV (vodič 6)."
            )

    for path in opts.manual_files:
        try:
            loaded = load_csv(path)
            events.extend(loaded)
            sources.append(f"CSV {path} ({len(loaded)})")
        except OSError as exc:
            warnings.append(f"Ne mogu pročitati {path}: {exc}")
    for name, text in opts.csv_texts:
        loaded = load_csv_text(text, name)
        events.extend(loaded)
        sources.append(f"CSV {name} ({len(loaded)})")

    if live:
        http = http or HttpClient(cache=FileCache(settings.cache_dir, ttl_seconds=6 * 3600))
        end = now + timedelta(days=opts.days)
        if settings.ticketmaster_api_key:
            tm = TicketmasterProvider(settings.ticketmaster_api_key, http)
            try:
                for classification, label in TM_CLASSIFICATIONS[opts.segment]:
                    found = tm.events_between(opts.countries, now, end, classification)
                    events.extend(found)
                    sources.append(f"Ticketmaster – {label} u idućih {opts.days} dana ({len(found)})")
                    if opts.include_far_onsales and opts.onsale_days > 0:
                        onsales = tm.onsales_between(
                            opts.countries, now, now + timedelta(days=opts.onsale_days),
                            now + timedelta(days=opts.onsale_horizon_days), classification,
                        )
                        events.extend(onsales)
                        sources.append(f"Ticketmaster – {label}: prodaja počinje u idućih {opts.onsale_days} dana ({len(onsales)})")
            except ProviderError as exc:
                warnings.append(f"Ticketmaster: {exc}")
            if tm.truncated:
                warnings.append(
                    f"Ticketmaster: rezultati su djelomični ({tm.calls} poziva; limit poziva ili > 1000 događaja u 12 h) – suzi države ili smanji --days."
                )
        else:
            warnings.append(
                "Nema TICKETMASTER_API_KEY – preskačem Ticketmaster (besplatan ključ: developer.ticketmaster.com; "
                "zamjene bez Ticketmastera: docs/IZVORI_PODATAKA.md)."
            )

        if opts.use_seatgeek and settings.seatgeek_client_id:
            sg = SeatGeekProvider(settings.seatgeek_client_id, http)
            try:
                for taxonomy in SG_TAXONOMIES[opts.segment]:
                    found = sg.events_between(opts.countries, now, end, taxonomy)
                    events.extend(found)
                    sources.append(f"SeatGeek – {taxonomy} ({len(found)})")
            except ProviderError as exc:
                warnings.append(f"SeatGeek: {exc}")

        if settings.serpapi_key:
            sp = SerpApiProvider(settings.serpapi_key, http)
            cities = parse_cities(opts.serpapi_cities or settings.serpapi_cities) or default_cities(opts.countries)
            try:
                found = sp.events(cities, now, end, opts.segment)
                events.extend(found)
                sources.append(f"Google Events / SerpApi – {len(cities)} gradova ({len(found)})")
            except ProviderError as exc:
                warnings.append(f"SerpApi: {exc}")
            warnings.extend(sp.warnings)

        if settings.predicthq_token:
            phq = PredictHQProvider(settings.predicthq_token, http, settings.predicthq_locations)
            try:
                found = phq.events(opts.countries, now, end, opts.segment)
                events.extend(found)
                sources.append(f"PredictHQ ({len(found)})")
            except ProviderError as exc:
                warnings.append(f"PredictHQ: {exc}")

    events = merge_events(events)
    music = [e for e in events if e.segment == "music"]

    if live and opts.use_lastfm and music:
        if settings.lastfm_api_key:
            http = http or HttpClient(cache=FileCache(settings.cache_dir, ttl_seconds=6 * 3600))
            targets = enrichment_targets(music, opts.max_artists)
            warnings.extend(LastFmProvider(settings.lastfm_api_key, http).enrich(targets))
            artists = len({normalize(e.artist) for e in targets})
            sources.append(f"Last.fm (popularnost {artists} izvođača)")
            if len({normalize(e.artist) for e in music}) > artists:
                warnings.append(
                    f"Last.fm: obogaćeno samo {artists} najperspektivnijih izvođača (--max-artists); ostali imaju zadanu popularnost."
                )
        elif not opts.use_deezer:
            warnings.append("Nema LASTFM_API_KEY – potražnja se procjenjuje bez popularnosti izvođača (manja točnost).")

    if live and opts.use_deezer and music:
        http = http or HttpClient(cache=FileCache(settings.cache_dir, ttl_seconds=6 * 3600))
        targets = [e for e in enrichment_targets(music, opts.max_artists) if not e.artist_listeners]
        if targets:
            deezer_warnings, found = DeezerProvider(http).enrich(targets, limit=opts.max_artists)
            warnings.extend(deezer_warnings)
            sources.append(f"Deezer (popularnost {found} izvođača, bez ključa)")

    if live and opts.use_wikipedia and music and opts.trend_artists > 0:
        http = http or HttpClient(cache=FileCache(settings.cache_dir, ttl_seconds=6 * 3600))
        targets = enrichment_targets(music, opts.trend_artists)
        wiki_warnings, found = WikipediaProvider(http).enrich(targets, now, limit=opts.trend_artists)
        warnings.extend(wiki_warnings)
        if found:
            sources.append(f"Wikipedia (trend pregleda za {found} izvođača)")

    annotate_supply(events)

    if not events and not (opts.demo or opts.snapshot):
        warnings.append(
            "Nema događaja. Bez ključeva koristi snimku stvarnih događaja (--snimka), dodaj API ključeve u .env "
            "(vidi docs/IZVORI_PODATAKA.md) ili učitaj vlastiti CSV (--csv)."
        )
    return events, warnings, sources


def run_scan(opts: ScanOptions, settings: Settings, http: HttpClient | None = None) -> ScanResult:
    now = opts.now or utcnow()
    opts.now = now
    meta: dict = {}
    events, warnings, sources = collect_events(opts, settings, http, meta)
    config = ModelConfig.load(opts.model_path)
    evaluator = Evaluator(
        config, budget=opts.budget, category=opts.category, strict=opts.strict, now=now, seller_country=opts.seller_country
    )

    window_end = now + timedelta(days=opts.days)
    opportunities: list[Opportunity] = []
    hidden = 0
    for event in events:
        if event.date < now - timedelta(hours=6):
            continue
        op = evaluator.evaluate(event)
        # događaji izvan prozora ostaju samo ako im prodaja tek počinje (prilika za kupnju)
        in_window = event.date <= window_end
        onsale_soon = op.days_to_onsale is not None and op.days_to_onsale <= max(opts.onsale_days, 0)
        # ručni/otkrivajući izvori (bez nominalnih cijena po prirodi) uvijek se prikazuju
        manual = opts.demo or opts.snapshot or event.source.startswith(DISCOVERY_SOURCES)
        if not (in_window or (opts.include_far_onsales and onsale_soon) or manual):
            continue
        # bez nominalne cijene nema izračuna – iz API-ja ih skrivamo (CSV/demo/snimku uvijek prikazujemo)
        if op.verdict == "NEMA CIJENE" and not (manual or opts.show_all):
            hidden += 1
            continue
        op.advice = build_advice(op, config)
        opportunities.append(op)

    opportunities.sort(key=sort_key)
    if hidden:
        warnings.append(f"Skriveno {hidden} događaja bez nominalne cijene u izvoru (prikaži s --show-all).")
    return ScanResult(
        opportunities=opportunities,
        warnings=warnings,
        sources=sources,
        generated_at=now,
        options=opts,
        is_demo=opts.demo,
        is_snapshot=opts.snapshot,
        snapshot=meta.get("snapshot"),
        evaluator=evaluator,
    )
