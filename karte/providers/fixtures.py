"""Raspored nogometnih utakmica – bez ključa (fixturedownload.com) i, uz besplatan ključ, API-Football (HNL).

fixturedownload.com objavljuje rasporede kao JSON (https://fixturedownload.com/feed/json/<natjecanje>-<godina>):
Liga prvaka, Europska i Konferencijska liga te pet najvećih liga, s datumom (UTC) i stadionom. Nema cijena ulaznica –
one se ionako ne objavljuju u API-jima, a za europski nogomet preprodaja radi zarade uglavnom nije dopuštena
(vidi sport.toml). Raspored služi da aplikacija pokaže koje utakmice postoje, zašto su zanimljive i kako se kupuju.

API-Football (https://www.api-football.com, besplatno 100 zahtjeva dnevno, ključ odmah): hrvatska HNL i druge lige
koje fixturedownload nema. Ključ ide u .env kao API_FOOTBALL_KEY.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

from karte import football
from karte.models import Event
from karte.net import HttpClient, ProviderError
from karte.util import parse_datetime

FIXTURE_URL = "https://fixturedownload.com/feed/json/{slug}-{season}"
SOURCE = "Raspored (fixturedownload.com)"
CACHE_TTL = 12 * 3600

# slug → (naziv natjecanja, država ili None za europska natjecanja)
FEEDS: dict[str, tuple[str, str | None]] = {
    "champions-league": ("UEFA Liga prvaka", None),
    "europa-league": ("UEFA Europska liga", None),
    "conference-league": ("UEFA Konferencijska liga", None),
    "epl": ("Premier League", "GB"),
    "bundesliga": ("Bundesliga", "DE"),
    "la-liga": ("LaLiga", "ES"),
    "serie-a": ("Serie A", "IT"),
    "ligue-1": ("Ligue 1", "FR"),
}

API_FOOTBALL_URL = "https://v3.football.api-sports.io/fixtures"
API_FOOTBALL_SOURCE = "API-Football"
# id lige → (naziv, država); popis id-eva: https://dashboard.api-football.com/soccer/ids
API_FOOTBALL_LEAGUES: dict[int, tuple[str, str]] = {210: ("SuperSport HNL", "HR")}
CANCELLED = {"CANC": "cancelled", "ABD": "cancelled", "PST": "postponed", "SUSP": "postponed"}


def season_start_year(now: datetime) -> int:
    """Europska sezona 2026./27. počinje u ljeto 2026. → 2026."""
    return now.year if now.month >= 7 else now.year - 1


def _last_sunday(year: int, month: int) -> date:
    d = date(year, month, 31)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def to_cet(utc: datetime) -> datetime:
    """UTC → srednjoeuropsko vrijeme (CET/CEST, pravilo EU) bez baze vremenskih zona."""
    start = datetime.combine(_last_sunday(utc.year, 3), datetime.min.time()).replace(hour=1)
    end = datetime.combine(_last_sunday(utc.year, 10), datetime.min.time()).replace(hour=1)
    return utc + timedelta(hours=2 if start <= utc < end else 1)


def _event(ident: str, home: str, away: str, when: datetime, competition: str, country: str | None, venue: str,
           city: str, source: str, seller_country: str, status: str = "onsale") -> tuple[Event, football.MatchInfo]:
    info = football.match_info(home, away, seller_country, competition)
    code = country or info.country
    if not city and info.home:
        city = info.home.city
    ticket_url = next((c.tickets for c in (info.home, info.away) if c and c.tickets), None)
    note = f"{info.reason[:1].upper() + info.reason[1:]}. " if info.reason else ""
    event = Event(
        id=ident,
        name=f"{home} – {away}",
        artist=f"{home} – {away}",
        venue=venue,
        city=city,
        country=code,
        date=when,
        source=source,
        url=ticket_url,
        status=status,
        tags=list(info.tags),
        notes=note + "Ulaznice i cijene objavljuje klub domaćin (obično 1–3 tjedna prije utakmice).",
        segment="sport",
        sport="football",
        league=competition,
    )
    return event, info


def parse_fixturedownload(data, slug: str, now: datetime, end: datetime, seller_country: str = "HR") -> list[tuple[Event, football.MatchInfo]]:
    competition, country = FEEDS.get(slug, (slug, None))
    out = []
    for m in data or []:
        if not isinstance(m, dict) or m.get("HomeTeamScore") is not None:
            continue  # odigrano
        home, away = (m.get("HomeTeam") or "").strip(), (m.get("AwayTeam") or "").strip()
        utc = parse_datetime(m.get("DateUtc"))
        if not home or not away or utc is None or "to be" in home.lower() or "to be" in away.lower():
            continue
        when = to_cet(utc)
        if not (to_cet(now) - timedelta(hours=2) <= when <= end):
            continue
        ident = f"fixture:{slug}:{m.get('MatchNumber') or f'{home}-{away}-{when:%Y%m%d}'}"
        out.append(_event(ident, home, away, when, competition, country, (m.get("Location") or "").strip(), "", SOURCE, seller_country))
    return out


def parse_api_football(data, now: datetime, end: datetime, leagues: dict[int, tuple[str, str]] | None = None,
                       seller_country: str = "HR") -> list[tuple[Event, football.MatchInfo]]:
    if not isinstance(data, dict):
        raise ProviderError("API-Football: neočekivan odgovor")
    errors = data.get("errors")
    if errors:  # npr. {"token": "..."} ili {"plan": "Free plans do not have access to this season ..."}
        text = "; ".join(f"{k}: {v}" for k, v in errors.items()) if isinstance(errors, dict) else "; ".join(map(str, errors))
        raise ProviderError(f"API-Football: {text}")
    leagues = leagues or API_FOOTBALL_LEAGUES
    out = []
    for item in data.get("response") or []:
        fx, lg, teams = item.get("fixture") or {}, item.get("league") or {}, item.get("teams") or {}
        utc = parse_datetime(fx.get("date"))
        home, away = ((teams.get("home") or {}).get("name") or "").strip(), ((teams.get("away") or {}).get("name") or "").strip()
        short = ((fx.get("status") or {}).get("short") or "NS").upper()
        if not home or not away or utc is None or short in ("FT", "AET", "PEN", "AWD", "WO"):
            continue
        when = to_cet(utc)
        if not (to_cet(now) - timedelta(hours=2) <= when <= end):
            continue
        name, country = leagues.get(lg.get("id"), (lg.get("name") or "Liga", None))
        venue = (fx.get("venue") or {})
        out.append(_event(f"apifootball:{fx.get('id')}", home, away, when, name, country, (venue.get("name") or "").strip(),
                          (venue.get("city") or "").strip(), API_FOOTBALL_SOURCE, seller_country, CANCELLED.get(short, "onsale")))
    return out


# ---------------------------------------------------------------------- tržište (viagogo/StubHub), ručno prikupljeno

MARKET_FILE = "nogomet_trziste.csv"
MARKET_SOURCE = "Tržište – nogomet (snimka)"
SPECULATIVE_DAYS = 21  # klubovi prodaju 1–3 tjedna prije utakmice; raniji oglasi su spekulativni


def _market_rows() -> list[dict]:
    """Ugrađeni retci + moji (~/.karte/snimka/nogomet_trziste.csv); moj redak za istu utakmicu zamjenjuje ugrađeni."""
    import csv
    import io

    from karte.snapshot import _read_package, _read_user

    rows: dict[tuple, dict] = {}
    for text in (_read_package(MARKET_FILE), _read_user(MARKET_FILE)):
        if not text:
            continue
        for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
            row = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            key = _match_key(row.get("domacin", ""), row.get("gost", ""), row.get("datum", ""))
            if key:
                rows[key] = {**rows.get(key, {}), **{k: v for k, v in row.items() if v}}
    return list(rows.values())


def _match_key(home: str, away: str, day: str) -> tuple | None:
    if not home or not away or not day:
        return None
    h, a = football.find_club(home), football.find_club(away)
    return (h.name if h else home.lower(), a.name if a else away.lower(), day[:10])


def _secondary(row: dict):
    from karte.models import SecondaryMarket
    from karte.util import parse_float, parse_int

    lowest = parse_float(row.get("sek_najniza"))
    if not lowest:
        return None
    return SecondaryMarket(
        source=row.get("sek_izvor") or "preprodaja",
        lowest=lowest,
        median=parse_float(row.get("sek_medijan")),
        listing_count=parse_int(row.get("broj_oglasa")),
        currency=(row.get("sek_valuta") or "EUR").upper(),
        observed=row.get("sek_datum") or None,
    )


def market_events(now: datetime, seller_country: str = "HR") -> list[Event]:
    """Utakmice za koje imamo cijene s preprodaje (viagogo/StubHub) – i kad ih nema u rasporedu (npr. HNL bez ključa)."""
    from karte.util import parse_float

    out = []
    for row in _market_rows():
        when = parse_datetime(f"{row.get('datum')} {row.get('vrijeme') or '00:00'}")  # 00:00 = vrijeme još nije objavljeno
        if when is None or when < to_cet(now) - timedelta(hours=2):
            continue
        event, _ = _event(f"trziste:{row.get('domacin')}-{row.get('gost')}-{row.get('datum')}", row["domacin"], row["gost"], when,
                          row.get("natjecanje") or "", (row.get("drzava") or "").upper() or None, row.get("stadion") or "",
                          row.get("grad") or "", MARKET_SOURCE, seller_country)
        event.secondary = _secondary(row)
        seen = parse_datetime(row.get("sek_datum")) if row.get("sek_datum") else None
        if event.secondary and seen and (when - seen).days > SPECULATIVE_DAYS:
            # oglasi daleko prije službene prodaje kluba: prodavač još nema ulaznice – model ih uzima s velikim popustom
            event.secondary.source = f"{event.secondary.source} (spekulativno)"
        event.face_min, event.face_max = parse_float(row.get("nominalna_od")), parse_float(row.get("nominalna_do"))
        event.url = row.get("url") or event.url
        note = " ".join(x for x in (row.get("biljeske"), f"Nominalna: {row['nominalna_izvor']}." if row.get("nominalna_izvor") else "") if x)
        event.notes = note or event.notes
        out.append(event)
    return out


def apply_market(events: list[Event], market: list[Event]) -> list[Event]:
    """Utakmice s tržišta spoji s rasporedom (isti domaćin, gost i dan); ostale dodaj kao nove događaje."""
    index = {}
    for e in events:
        if e.segment == "sport" and e.sport == "football":
            home, away = football.split_match(e)
            key = _match_key(home, away, e.date.date().isoformat())
            if key:
                index[key] = e
    extra = []
    for m in market:
        home, away = football.split_match(m)
        target = index.get(_match_key(home, away, m.date.date().isoformat()))
        if target is None:
            extra.append(m)
            continue
        target.secondary = target.secondary or m.secondary
        target.face_min = target.face_min if target.face_min is not None else m.face_min
        target.face_max = target.face_max if target.face_max is not None else m.face_max
        target.notes = " ".join(x for x in (target.notes, m.notes) if x)
        target.url = target.url or m.url
    return events + extra


def football_events(
    http: HttpClient,
    now: datetime,
    end: datetime,
    countries: list[str],
    seller_country: str = "HR",
    api_football_key: str | None = None,
    api_football_leagues: dict[int, tuple[str, str]] | None = None,
    feeds: list[str] | None = None,
    only_notable: bool = True,
) -> tuple[list[Event], list[str], list[str]]:
    """Utakmice iz svih izvora rasporeda → (događaji, upozorenja, izvori).

    Zadržava derbije, velike utakmice i sve utakmice klubova iz države prodavatelja; utakmice u državama izvan
    odabranih prikazuju se samo ako igra klub iz države prodavatelja.
    """
    warnings: list[str] = []
    sources: list[str] = []
    found: list[tuple[Event, football.MatchInfo]] = []
    season = season_start_year(now)
    ok = 0
    for slug in feeds or list(FEEDS):
        try:
            data = http.get_json(FIXTURE_URL.format(slug=slug, season=season), cache_ttl=CACHE_TTL,
                                 cache_if=lambda d: isinstance(d, list) and len(d) > 0)
            found.extend(parse_fixturedownload(data, slug, now, end, seller_country))
            ok += 1
        except ProviderError as exc:
            warnings.append(f"Raspored {FEEDS.get(slug, (slug,))[0]}: {exc}")
    if ok:
        sources.append(f"Nogomet – raspored bez ključa (fixturedownload.com: {ok} natjecanja)")
    if api_football_key:
        leagues = api_football_leagues or API_FOOTBALL_LEAGUES
        for league_id, (name, _) in leagues.items():
            try:
                data = http.get_json(
                    API_FOOTBALL_URL,
                    {"league": league_id, "season": season, "from": now.date().isoformat(), "to": end.date().isoformat()},
                    headers={"x-apisports-key": api_football_key}, cache_ttl=CACHE_TTL,
                    cache_if=lambda d: isinstance(d, dict) and not d.get("errors"),
                )
                rows = parse_api_football(data, now, end, leagues, seller_country)
                found.extend(rows)
                sources.append(f"API-Football – {name} ({len(rows)})")
            except ProviderError as exc:
                warnings.append(str(exc))

    wanted = {c.upper() for c in countries or ["ALL"]}
    events = []
    for event, info in found:
        local = info.involves(seller_country) or event.country == seller_country
        if only_notable and not (football.is_notable(info, seller_country) or event.country == seller_country):
            continue
        if "ALL" not in wanted and event.country not in wanted and not local:
            continue
        events.append(event)
    return events, warnings, sources
