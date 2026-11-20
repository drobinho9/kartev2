"""Naredbeni redak: karte gui | scan | calc | kategorije | dnevnik | markets | platforms | laws | doctor."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from karte import __version__, legal
from karte.journal import Journal, default_path
from karte.knowledge import ModelConfig, expand_countries, regions
from karte.net import HttpClient, ProviderError
from karte.pipeline import ScanOptions, run_scan
from karte.platforms import available_platforms, blocked_for_seller, load_platforms
from karte.report import RENDERERS, render_detail_text
from karte.scoring import CATEGORIES
from karte import sport
from karte.service import calculate, categories, market_rows

VRSTA = {"koncerti": "music", "sport": "sport", "sve": "all"}
from karte.settings import Settings
from karte.util import fmt_eur, fmt_pct


def _countries(value: str | None, settings: Settings) -> list[str]:
    """Države ili regije (npr. 'otvoreno', 'europa', 'sjeverna_amerika', 'svijet', 'US,GB,DE')."""
    return expand_countries(value or settings.countries)


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
        seller_country=(args.seller_country or settings.seller_country).upper(),
        max_artists=args.max_artists,
        show_all=args.show_all,
        segment=VRSTA[args.vrsta],
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


def _calc_fields(args, settings: Settings) -> dict:
    return {
        "artist": args.name or "Kalkulacija",
        "venue": args.venue or "",
        "country": args.country,
        "region": args.state or "",
        "date": args.date or "",
        "days": args.days,
        "face": args.face,
        "currency": args.currency,
        "resale_lowest": args.resale,
        "listing_count": getattr(args, "listings", None),
        "capacity": args.capacity,
        "ticket_limit": args.limit,
        "personalized": "da" if args.personalized else ("ne" if args.not_personalized else ""),
        "tags": args.tags or "",
        "listeners": args.listeners,
        "vendor": args.vendor or "",
        "primary_fee": args.primary_fee,
        "budget": args.budget,
        "strict": args.strict,
        "seller_country": args.seller_country or settings.seller_country,
        "segment": "sport" if getattr(args, "vrsta", "koncert") == "sport" else "music",
        "sport": getattr(args, "sport", None) or "football",
        "league": getattr(args, "liga", None) or "",
    }


def cmd_calc(args, settings: Settings) -> int:
    """Brzi kalkulator za jedan događaj (npr. iz oglasa na Entriju + najniže cijene na viagogu)."""
    op = calculate(_calc_fields(args, settings), settings, args.model)
    print(render_detail_text(1, op))
    if op.platforms:
        print("Platforme (po ulaznici):")
        for p in op.platforms:
            print(f"  {p.name:<34} oglas {fmt_eur(p.list_price):>8}  neto {fmt_eur(p.net_payout):>8}  "
                  f"P(prodaja) {p.p_sell * 100:3.0f} %  oček. vrijednost {fmt_eur(p.expected_value):>8}{'  (limit)' if p.capped else ''}")
    return 0


def _parse_cat(spec: str) -> dict:
    """'Naziv:cijena[:vrsta[:najniža_na_viagogu]]' → rječnik."""
    parts = [x.strip() for x in spec.split(":")]
    if len(parts) < 2:
        raise SystemExit(f"Neispravna kategorija '{spec}' – format: Naziv:cijena[:vrsta[:najniža_na_viagogu]]")
    return {"name": parts[0], "face": parts[1], "kind": parts[2] if len(parts) > 2 and parts[2] else "standard",
            "resale_lowest": parts[3] if len(parts) > 3 else None}


def cmd_categories(args, settings: Settings) -> int:
    fields = _calc_fields(args, settings)
    fields["face"] = None
    result = categories(fields, [_parse_cat(c) for c in args.cat], settings, args.model)
    print(result["summary"] + "\n")
    print(f"{'Kategorija':<28} {'Vrsta':<26} {'Nomin.':>7} {'Oček.':>7} {'×':>5} {'Dobit*':>7} {'Oček.ROI':>8}  Preporuka")
    for r in result["rows"]:
        star = "★ " if r.get("best_roi") else "  "
        print(f"{star}{r['name'][:26]:<26} {r['kind_label'][:26]:<26} {fmt_eur(r['face_eur']):>7} {fmt_eur(r['expected_resale']):>7} "
              f"{(r['multiplier'] or 0):>5.2f} {fmt_eur(r['profit']):>7} {fmt_pct(r['roi']):>8}  {r['verdict']}")
    print("\nDobit* = neto po ulaznici ako se proda. Vrste: front, parter, standard, tribina, vip, zaklonjeno.")
    return 0


def cmd_sport(args, settings: Settings) -> int:
    for r in sport.rules_overview(args.country):
        title = r.get("name", r["code"])
        print(f"■ [{r['scope']}] {title} — {r['rule_label']} (rizik {float(r.get('risk', 0)) * 100:.0f}/100)")
        print(f"    {r.get('summary', '')}")
        if r.get("official"):
            print(f"    Službeni kanal: {r['official']}")
        for line in r.get("how_to_buy", []):
            print(f"    • {line}")
        for src in r.get("sources", [])[:3]:
            print(f"    izvor: {src}")
        print()
    print("Vodič: karte gui → Vodiči → Nogomet i sport. Nije pravni savjet – provjeri uvjete konkretnog kluba/natjecanja.")
    return 0


def cmd_journal(args, settings: Settings) -> int:
    journal = Journal(args.file or default_path(os.environ.get("KARTE_DATA_DIR")))
    if args.import_csv:
        n = journal.import_csv(Path(args.import_csv).read_text(encoding="utf-8"))
        print(f"Uvezeno {n} transakcija u {journal.path}")
    if args.export:
        Path(args.export).write_text(journal.export_csv(), encoding="utf-8")
        print(f"Izvezeno u {args.export}")
    st = journal.stats(ModelConfig.load(args.model))
    print(f"Dnevnik: {journal.path} · transakcija: {st['count']} (zatvoreno {st['closed']})")
    print(f"Uloženo {fmt_eur(st['invested_total'])} · prihod {fmt_eur(st['revenue'])} · dobit {fmt_eur(st['profit'])} · "
          f"ROI {fmt_pct(st['roi'])} · kapital u igri {fmt_eur(st['open_capital'])}")
    for t in journal.list()[:20]:
        row = t.to_row()
        print(f"  {t.event_date or '—':<10} {t.artist[:28]:<28} {row['status_label']:<22} {t.qty} kom  "
              f"dobit {fmt_eur(row['realized_profit'])}  ROI {fmt_pct(row['roi'])}  {t.platform}")
    print("\n" + st["calibration"].get("message", ""))
    print("Unos i uređivanje: karte gui → Moje prodaje")
    return 0


def cmd_gui(args, settings: Settings) -> int:
    from karte.gui.server import serve

    journal = Path(args.journal) if args.journal else default_path(os.environ.get("KARTE_DATA_DIR"))
    serve(settings, port=args.port, open_browser=not args.no_browser, journal_path=journal, model_path=args.model, verbose=args.verbose)
    return 0


def cmd_platforms(args, settings: Settings) -> int:
    seller = (args.seller_country or settings.seller_country).upper()
    if args.country:
        plats = available_platforms(args.country, args.vendor, seller)
        blocked = blocked_for_seller(args.country, args.vendor, seller)
    else:
        plats, blocked = list(load_platforms().values()), []
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
        if p.seller_countries:
            print(f"    (prodavatelj mora imati prebivalište u: {', '.join(p.seller_countries)})")
        print()
    if blocked:
        print(f"Ne primaju prodavatelje iz {seller}: " + ", ".join(p.name for p in blocked))
    return 0


def cmd_laws(args, settings: Settings) -> int:
    if args.country:
        code = args.country.upper()
        country, _, region = code.partition("-")
        items = [(code, legal.country_info(country, region or None))]
    else:
        items = legal.all_countries()
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


def cmd_markets(args, settings: Settings) -> int:
    codes = expand_countries(args.countries) if args.countries else None
    rows = market_rows(codes)
    print(f"Tržišta rangirana za prodavača iz {settings.seller_country} (veličina × legalnost × dostupnost):\n")
    print(f"{'#':>3}  {'Država':<24} {'Ocjena':>6}  {'Veličina':>8}  {'Pristup':>7}  {'TM':<11} Pravilo")
    for i, m in enumerate(rows, 1):
        rule = m["rule_label"] + (" (+ najavljeno ograničenje)" if m["planned"] else "")
        name = f"{m['code']} {m['name']}"
        print(f"{i:>3}  {name[:24]:<24} {m['score'] * 100:>6.0f}  {m['size'] * 100:>8.0f}  {m['access'] * 100:>7.0f}  {m['tm']:<11} {rule}")
        if args.details and m["access_note"]:
            print(f"       {m['access_note']}")
    print("\nRegije za --countries: " + ", ".join(sorted(regions())))
    print("Napomena: procjena za orijentaciju, ne pravni savjet. Detalji: karte laws --country XX")
    return 0


def cmd_doctor(args, settings: Settings) -> int:
    print(f"karte {__version__} · Python {sys.version.split()[0]}")
    print(f"Države: {', '.join(expand_countries(settings.countries))} · prodavatelj iz: {settings.seller_country} · "
          f"budžet: {fmt_eur(settings.budget)} · cache: {settings.cache_dir}")
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
    s.add_argument(
        "--countries",
        help="države i/ili regije: npr. US,GB,DE ili otvoreno, europa, dach, sjeverna_amerika, oceanija, svijet (vidi: karte markets)",
    )
    s.add_argument("--seller-country", help="država tvog prebivališta (zadano HR) – za dostupnost platformi i rizik pristupa")
    s.add_argument("--max-artists", type=int, default=300, help="koliko najperspektivnijih izvođača obogatiti Last.fm-om (zadano 300)")
    s.add_argument("--show-all", action="store_true", help="prikaži i događaje bez nominalne cijene u izvoru")
    s.add_argument("--vrsta", choices=sorted(VRSTA), default="koncerti", help="koncerti (zadano), sport ili sve")
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
    c.add_argument("--state", help="savezna država/pokrajina, npr. NY, VT, ON, NSW")
    c.add_argument("--vrsta", choices=["koncert", "sport"], default="koncert")
    c.add_argument("--sport", choices=sorted(sport.SPORT_LABELS), help="za --vrsta sport (zadano football = nogomet)")
    c.add_argument("--liga", help="natjecanje/liga, npr. 'UEFA Champions League', 'Premier League', 'NFL'")
    c.add_argument("--seller-country")
    c.add_argument("--days", type=int, default=45, help="za koliko dana je događaj (ako nema --date)")
    c.add_argument("--date", help="datum događaja YYYY-MM-DD")
    c.add_argument("--listings", type=int, help="broj oglasa na viagogu")
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

    k = sub.add_parser("kategorije", help="koje kategorije ulaznica za koncert se najisplativije preprodaju")
    k.add_argument("--cat", action="append", required=True, help="Naziv:cijena[:vrsta[:najniža_na_viagogu]], npr. Parter:59:parter (više puta)")
    for a in ("--currency", "--country", "--state", "--vendor", "--name", "--venue", "--tags", "--seller-country", "--model", "--date"):
        k.add_argument(a, default={"--currency": "EUR", "--country": "HR"}.get(a))
    k.add_argument("--days", type=int, default=45)
    k.add_argument("--listeners", type=int)
    k.add_argument("--capacity", type=int)
    k.add_argument("--limit", type=int)
    k.add_argument("--budget", type=float)
    k.add_argument("--primary-fee", type=float)
    k.add_argument("--resale", type=float)
    k.add_argument("--personalized", action="store_true")
    k.add_argument("--not-personalized", action="store_true")
    k.add_argument("--strict", action="store_true")
    k.set_defaults(func=cmd_categories, face=None)

    sp = sub.add_parser("sport", help="pravila preprodaje za nogomet po državama i za natjecanja (UEFA, FIFA, NFL, F1…)")
    sp.add_argument("--country", help="samo jedna država, npr. HR, GB, DE")
    sp.set_defaults(func=cmd_sport)

    j = sub.add_parser("dnevnik", help="moje kupnje i prodaje: statistika, uvoz/izvoz CSV")
    j.add_argument("--file", help="putanja do dnevnika (zadano ~/.karte/dnevnik.json)")
    j.add_argument("--import-csv", help="uvezi transakcije iz CSV-a")
    j.add_argument("--export", help="izvezi transakcije u CSV")
    j.add_argument("--model")
    j.set_defaults(func=cmd_journal)

    g = sub.add_parser("gui", help="pokreni grafičko sučelje u pregledniku")
    g.add_argument("--port", type=int, default=8765)
    g.add_argument("--no-browser", action="store_true", help="ne otvaraj preglednik automatski")
    g.add_argument("--journal", help="putanja do dnevnika prodaja")
    g.add_argument("--model")
    g.add_argument("--verbose", action="store_true")
    g.set_defaults(func=cmd_gui)

    p = sub.add_parser("platforms", help="popis platformi za preprodaju i naknada")
    p.add_argument("--country", help="samo platforme dostupne u državi")
    p.add_argument("--vendor", help="primarni prodavač (za službene preprodaje)")
    p.add_argument("--seller-country", help="država tvog prebivališta (zadano HR)")
    p.set_defaults(func=cmd_platforms)

    law = sub.add_parser("laws", help="pravila preprodaje po državama")
    law.add_argument("--country", help="npr. DE, US, US-VT, CA-ON")
    law.set_defaults(func=cmd_laws)

    m = sub.add_parser("markets", help="rangiraj tržišta (države) po isplativosti za preprodaju iz HR")
    m.add_argument("--countries", help="države ili regije (zadano: sve u bazi)")
    m.add_argument("--details", action="store_true", help="prikaži napomene o kupnji/prodaji iz inozemstva")
    m.set_defaults(func=cmd_markets)

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
