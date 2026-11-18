"""Naredbeni redak: karte scan | calc | platforms | laws | doctor."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from karte import __version__, legal
from karte.knowledge import ModelConfig
from karte.models import Event, SecondaryMarket
from karte.net import FileCache, HttpClient, ProviderError
from karte.pipeline import ScanOptions, run_scan
from karte.platforms import available_platforms, load_platforms
from karte.report import RENDERERS, render_detail_text
from karte.scoring import CATEGORIES, Evaluator
from karte.settings import Settings
from karte.advisor import build_advice
from karte.util import add_days, fmt_eur, fmt_pct, utcnow


def _countries(value: str | None, settings: Settings) -> list[str]:
    if not value:
        return settings.countries
    return [c.strip().upper() for c in value.split(",") if c.strip()]


def cmd_scan(args, settings: Settings) -> int:
    opts = ScanOptions(
        days=args.days,
        onsale_days=args.onsale_days,
        countries=_countries(args.countries, settings),
        budget=args.budget if args.budget is not None else settings.budget,
        category=args.category,
        strict=args.strict,
        demo=args.demo,
        manual_files=args.csv or [],
        use_lastfm=not args.no_lastfm,
        use_seatgeek=not args.no_seatgeek,
        include_far_onsales=not args.no_onsales,
        model_path=args.model,
    )
    result = run_scan(opts, settings)
    if args.only:
        wanted = {v.strip().upper() for v in args.only.split(",")}
        result.opportunities = [op for op in result.opportunities if op.verdict.upper() in wanted]
    if args.min_roi is not None:
        result.opportunities = [op for op in result.opportunities if op.roi is not None and op.roi >= args.min_roi]

    renderer = RENDERERS[args.format]
    if args.format == "table":
        text = renderer(result, top=args.top, details=args.details)
    elif args.format in ("md", "html"):
        text = renderer(result, top=args.top)
    else:
        text = renderer(result)

    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"Izvještaj spremljen: {args.out} ({len(result.opportunities)} događaja)")
        for w in result.warnings:
            print(f"! {w}")
    else:
        print(text)
    return 0


def cmd_calc(args, settings: Settings) -> int:
    """Brzi kalkulator za jedan događaj (npr. iz oglasa na Entriju + najniže cijene na viagogu)."""
    now = utcnow()
    secondary = None
    if args.resale:
        secondary = SecondaryMarket(source="ručni unos", lowest=args.resale, currency=args.currency)
    event = Event(
        id="calc",
        name=args.name or "Kalkulacija",
        artist=args.name or "Kalkulacija",
        venue=args.venue or "",
        city="",
        country=args.country.upper(),
        date=add_days(now, args.days),
        source="kalkulator",
        face_min=args.face,
        face_max=args.face,
        currency=args.currency,
        status="onsale",
        capacity=args.capacity,
        ticket_limit=args.limit,
        personalized=True if args.personalized else (False if args.not_personalized else None),
        tags=[t.strip() for t in (args.tags or "").split(",") if t.strip()],
        secondary=secondary,
        artist_listeners=args.listeners,
        primary_vendor=args.vendor,
    )
    config = ModelConfig.load(args.model)
    if args.primary_fee is not None:
        config.data.setdefault("primary_fees", {})["default_pct"] = args.primary_fee
        config.data["primary_fees"]["default_fixed"] = 0.0
        event.primary_vendor = None
    evaluator = Evaluator(config, budget=args.budget if args.budget is not None else settings.budget, strict=args.strict, now=now)
    op = evaluator.evaluate(event)
    op.advice = build_advice(op, config)
    print(render_detail_text(1, op))
    if op.platforms:
        print("Platforme (po ulaznici):")
        for p in op.platforms:
            print(f"  {p.name:<34} oglas {fmt_eur(p.list_price):>8}  neto {fmt_eur(p.net_payout):>8}  "
                  f"P(prodaja) {p.p_sell * 100:3.0f} %  oček. vrijednost {fmt_eur(p.expected_value):>8}{'  (limit)' if p.capped else ''}")
    return 0


def cmd_platforms(args, settings: Settings) -> int:
    plats = available_platforms(args.country, args.vendor) if args.country else list(load_platforms().values())
    for p in plats:
        cap = {"none": "bez limita", "face": "do nominalne cijene", "percent": f"do +{p.cap_pct * 100:.0f} %"}.get(p.cap, p.cap)
        print(f"■ {p.display_name(args.country)}  —  naknada prodavatelja ~{p.seller_fee_pct * 100:.0f} %"
              f"{f' + {p.seller_fee_fixed:.2f} €' if p.seller_fee_fixed else ''} · cijena: {cap} · doseg {p.reach * 100:.0f}/100 · "
              f"rizik {p.trust_risk * 100:.0f}/100")
        if p.url:
            print(f"    {p.url}")
        print(f"    Isplata: {p.payout}")
        print(f"    {p.notes}")
        if p.requires_vendor:
            print(f"    (samo za ulaznice kupljene preko: {p.requires_vendor})")
        print()
    return 0


def cmd_laws(args, settings: Settings) -> int:
    items = [(args.country.upper(), legal.country_info(args.country))] if args.country else legal.all_countries()
    for code, info in items:
        rule = legal.RULE_LABELS.get(info.get("cap", "none"), info.get("cap"))
        planned = info.get("planned_cap")
        extra = f" · NAJAVLJENO: {legal.RULE_LABELS.get(planned, planned)}" if planned else ""
        print(f"■ {code} {info.get('name', '')} — {rule}{extra} (rizik {float(info.get('risk', 0)) * 100:.0f}/100)")
        print(f"    {info.get('summary', '')}")
        for src in info.get("sources", []):
            print(f"    izvor: {src}")
        print()
    print("Napomena: nije pravni savjet – provjeri aktualne propise.")
    return 0


def cmd_doctor(args, settings: Settings) -> int:
    print(f"karte {__version__} · Python {sys.version.split()[0]}")
    print(f"Države: {', '.join(settings.countries)} · budžet: {fmt_eur(settings.budget)} · cache: {settings.cache_dir}")
    http = HttpClient(cache=None, retries=0)
    checks = [
        ("TICKETMASTER_API_KEY", settings.ticketmaster_api_key, "https://app.ticketmaster.com/discovery/v2/events.json",
         {"apikey": settings.ticketmaster_api_key, "size": 1, "countryCode": "AT"}),
        ("LASTFM_API_KEY", settings.lastfm_api_key, "https://ws.audioscrobbler.com/2.0/",
         {"method": "artist.getinfo", "artist": "Radiohead", "api_key": settings.lastfm_api_key, "format": "json"}),
        ("SEATGEEK_CLIENT_ID", settings.seatgeek_client_id, "https://api.seatgeek.com/2/events",
         {"client_id": settings.seatgeek_client_id, "per_page": 1}),
    ]
    ok = True
    for name, value, url, params in checks:
        if not value:
            print(f"  – {name}: nije postavljen")
            continue
        if args.offline:
            print(f"  ✓ {name}: postavljen (bez provjere mreže)")
            continue
        try:
            http.get_json(url, params)
            print(f"  ✓ {name}: radi")
        except ProviderError as exc:
            ok = False
            print(f"  ✗ {name}: {exc}")
    if not any(v for _, v, _, _ in checks):
        print("\nNijedan ključ nije postavljen. Kopiraj .env.example u .env i upiši ključeve, ili probaj: karte scan --demo")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="karte",
        description="Radar za preprodaju ulaznica: traži koncerte, procjenjuje zaradu i savjetuje kako kupiti i preprodati.",
    )
    parser.add_argument("--version", action="version", version=f"karte {__version__}")
    parser.add_argument("--env", default=".env", help="putanja do .env datoteke (zadano: .env)")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="pretraži koncerte i rangiraj prilike")
    s.add_argument("--days", type=int, default=60, help="koncerti u idućih N dana (zadano 60)")
    s.add_argument("--onsale-days", type=int, default=30, help="+ koncerti kojima prodaja počinje u idućih N dana (zadano 30)")
    s.add_argument("--no-onsales", action="store_true", help="ne traži nadolazeće početke prodaje")
    s.add_argument("--countries", help="ISO kodovi država, npr. HR,SI,AT,HU,DE")
    s.add_argument("--budget", type=float, help="ukupni budžet u EUR (za preporuku količine)")
    s.add_argument("--category", choices=CATEGORIES, default="cheap", help="koju kategoriju ulaznica ciljaš (zadano: cheap)")
    s.add_argument("--strict", action="store_true", help="primijeni i najavljene (još nevažeće) zakonske limite, npr. DE, UK")
    s.add_argument("--demo", action="store_true", help="koristi ugrađene demo podatke (bez API ključeva)")
    s.add_argument("--csv", action="append", help="dodaj događaje iz CSV-a (može više puta)")
    s.add_argument("--no-lastfm", action="store_true")
    s.add_argument("--no-seatgeek", action="store_true")
    s.add_argument("--model", help="TOML datoteka s vlastitim parametrima modela")
    s.add_argument("--only", help="prikaži samo ove preporuke, npr. KUPI,RAZMOTRI")
    s.add_argument("--min-roi", type=float, help="minimalni ROI (npr. 0.2 = 20 %%)")
    s.add_argument("--top", type=int, default=25, help="broj redaka u tablici")
    s.add_argument("--details", type=int, default=5, help="broj detaljnih savjeta (terminal)")
    s.add_argument("--format", choices=sorted(RENDERERS), default="table")
    s.add_argument("--out", help="spremi izvještaj u datoteku")
    s.set_defaults(func=cmd_scan)

    c = sub.add_parser("calc", help="kalkulator isplativosti za jedan događaj")
    c.add_argument("--face", type=float, required=True, help="nominalna cijena ulaznice")
    c.add_argument("--resale", type=float, help="trenutna najniža cijena na sekundarnom tržištu (npr. viagogo)")
    c.add_argument("--currency", default="EUR")
    c.add_argument("--country", default="HR")
    c.add_argument("--days", type=int, default=45, help="za koliko dana je događaj")
    c.add_argument("--listeners", type=int, help="Last.fm slušatelji izvođača")
    c.add_argument("--capacity", type=int, help="kapacitet dvorane")
    c.add_argument("--limit", type=int, help="limit ulaznica po kupcu")
    c.add_argument("--tags", help="oznake: farewell,reunion,first_visit,added_date,anniversary,soldout...")
    c.add_argument("--vendor", help="primarni prodavač: ticketmaster, eventim, entrio, ulaznice_hr")
    c.add_argument("--primary-fee", type=float, help="naknada pri kupnji kao udio, npr. 0.1")
    c.add_argument("--personalized", action="store_true")
    c.add_argument("--not-personalized", action="store_true")
    c.add_argument("--name")
    c.add_argument("--venue")
    c.add_argument("--budget", type=float)
    c.add_argument("--strict", action="store_true")
    c.add_argument("--model")
    c.set_defaults(func=cmd_calc)

    p = sub.add_parser("platforms", help="popis platformi za preprodaju i naknada")
    p.add_argument("--country", help="samo platforme dostupne u državi")
    p.add_argument("--vendor", help="primarni prodavač (za službene preprodaje)")
    p.set_defaults(func=cmd_platforms)

    law = sub.add_parser("laws", help="pravila preprodaje po državama")
    law.add_argument("--country")
    law.set_defaults(func=cmd_laws)

    d = sub.add_parser("doctor", help="provjeri API ključeve i povezivost")
    d.add_argument("--offline", action="store_true", help="samo provjeri postoje li ključevi")
    d.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = Settings.from_env(args.env)
    try:
        return args.func(args, settings)
    except BrokenPipeError:  # npr. "karte scan | head"
        try:
            sys.stdout = open(os.devnull, "w")
        except OSError:
            pass
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
