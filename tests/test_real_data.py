"""Stvarni izvori bez Ticketmastera: Deezer, Wikipedia/Wikimedia, snimka stvarnih događaja, SerpApi, PredictHQ."""

import dataclasses
import json
from datetime import date, datetime

import pytest

from conftest import FakeHttp, load_fixture
from karte.cli import main
from karte.knowledge import ModelConfig, expand_countries
from karte.models import Event, SecondaryMarket
from karte.net import ProviderError
from karte.pipeline import ScanOptions, run_scan
from karte.providers import deezer, predicthq, serpapi, wikipedia
from karte.providers.manual import load_csv_text
from karte.scoring import VERDICT_ORDER, Evaluator
from karte.settings import Settings
from karte.snapshot import CURATED_SOURCE, load_snapshot, refresh_snapshot
from karte.util import hr_plural

SNAP_NOW = datetime(2026, 11, 22, 10, 0)


def _settings(tmp_path, **kw) -> Settings:
    base = dict(ticketmaster_api_key=None, seatgeek_client_id=None, lastfm_api_key=None, countries=["HR"], budget=1000.0, cache_dir=tmp_path)
    base.update(kw)
    return Settings(**base)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Snimka se čita iz paketa, ne iz korisnikove ~/.karte mape."""
    monkeypatch.setenv("KARTE_DATA_DIR", str(tmp_path / "karte-data"))


# ----------------------------------------------------------------------------- Deezer
def test_deezer_picks_exact_name_with_most_fans():
    data = load_fixture("deezer_search_sting.json")
    assert data["data"][0]["nb_fan"] < 1000  # pretraga na prvom mjestu vraća krivog "Stinga"
    best = deezer.best_match(data, "Sting")
    assert best["nb_fan"] == 1796973
    assert deezer.best_match(data, "Nepostojeći Izvođač") is None


def test_deezer_enrich_fills_fans_and_skips_known(make_event):
    http = FakeHttp({deezer.BASE_URL: load_fixture("deezer_search_sting.json")})
    a = make_event(artist="Sting", artist_listeners=None)
    b = make_event(id="t2", artist="Sting", artist_listeners=None)
    c = make_event(id="t3", artist="Sting", artist_fans=5)
    warnings, found = deezer.DeezerProvider(http).enrich([a, b, c])
    assert warnings == [] and found == 1
    assert a.artist_fans == b.artist_fans == 1796973 and c.artist_fans == 5
    assert len(http.calls) == 1  # isti izvođač – jedan zahtjev


def test_deezer_error_payload_raises_and_is_not_cached():
    http = FakeHttp({deezer.BASE_URL: {"error": {"type": "Exception", "message": "Quota limit exceeded", "code": 4}}})
    with pytest.raises(ProviderError, match="Quota"):
        deezer.DeezerProvider(http).lookup("Sting")
    assert deezer._valid({"error": {}}) is False and deezer._valid({"data": []}) is True


# ----------------------------------------------------------------------------- Wikipedia
def test_tour_table_parser_on_real_wikipedia_html():
    html = load_fixture("wikipedia_tour_twilight.json")["parse"]["text"]
    shows = wikipedia.parse_tour_html(html)
    assert len(shows) == 36  # "36-date Twilight of the Punks World Tour"
    first = shows[0]
    assert first == {"date": date(2027, 5, 17), "city": "Prague", "country_name": "Czech Republic", "country": "CZ", "venue": "O2 Arena"}
    assert shows[1]["venue"] == "László Papp Budapest Sports Arena" and shows[1]["country"] == "HU"
    assert all(s["country"] for s in shows)
    assert sum(s["country"] == "US" for s in shows) == 20  # zemlja preko rowspan ćelije
    london = [s for s in shows if s["city"] == "London"]
    assert london and london[0]["country"] == "GB"  # "England" → GB


def test_tour_events_filter_future_and_region():
    html = load_fixture("wikipedia_tour_twilight.json")["parse"]["text"]
    events = wikipedia.WikipediaProvider(FakeHttp({})).tour_events(
        "Twilight of the Punks", "Fall Out Boy", countries=expand_countries(["europa"]), now=SNAP_NOW, html=html
    )
    assert len(events) == 15 and all(e.country != "US" for e in events)
    assert events[0].artist == "Fall Out Boy" and events[0].source == "Wikipedia (turneja)"
    assert events[0].artist_upcoming_events == 36
    assert events[0].url == "https://en.wikipedia.org/wiki/Twilight_of_the_Punks"
    later = wikipedia.events_from_shows(wikipedia.parse_tour_html(html), "T", "A", now=datetime(2027, 6, 1))
    assert all(e.date >= datetime(2027, 6, 1) for e in later)


def test_grid_handles_rowspan_colspan_separators_and_cancelled_tables():
    html = """
    <table class="wikitable"><caption>List of 2027 concerts</caption>
    <tr><th>Date (2027)</th><th>City</th><th>Country</th><th>Venue</th></tr>
    <tr><th colspan="4">Leg 1 – Europe</th></tr>
    <tr><th scope="row">March 3<sup>[a]</sup></th><td rowspan="2">Zagreb</td><td rowspan="3">Croatia</td><td rowspan="2">Arena Zagreb</td></tr>
    <tr><th scope="row">March 4</th></tr>
    <tr><th scope="row">6 March</th><td>Split</td><td>Spaladium Arena<span style="display:none">skriveno</span></td></tr>
    <tr><th colspan="3">Total</th><td>—</td></tr>
    </table>
    <table class="wikitable"><caption>List of cancelled concerts</caption>
    <tr><th>Date</th><th>City</th><th>Country</th><th>Venue</th></tr>
    <tr><td>March 9, 2027</td><td>Pula</td><td>Croatia</td><td>Arena Pula</td></tr>
    </table>"""
    shows = wikipedia.parse_tour_html(html)
    assert [(s["date"].day, s["city"], s["country"], s["venue"]) for s in shows] == [
        (3, "Zagreb", "HR", "Arena Zagreb"),
        (4, "Zagreb", "HR", "Arena Zagreb"),
        (6, "Split", "HR", "Spaladium Arena"),
    ]


def test_parse_tour_date_formats():
    assert wikipedia.parse_tour_date("May 17, 2027", None) == date(2027, 5, 17)
    assert wikipedia.parse_tour_date("17 May 2027", None) == date(2027, 5, 17)
    assert wikipedia.parse_tour_date("September 25", 2026) == date(2026, 9, 25)
    assert wikipedia.parse_tour_date("Sept. 3", 2027) == date(2027, 9, 3)
    assert wikipedia.parse_tour_date("Total", 2027) is None
    assert wikipedia.parse_tour_date("May 17", None) is None


def test_resolve_titles_skips_disambiguation_and_checks_description():
    def api(params):
        titles = params["titles"].split("|")
        pages = []
        for t in titles:
            if t == "Sting":
                pages.append({"title": "Sting", "pageprops": {"disambiguation": ""}})
            elif t == "Sting (musician)":
                pages.append({"title": "Sting (musician)", "pageprops": {"wikibase-shortdesc": "English musician (born 1951)"}})
            elif t == "Sabaton":
                pages.append({"title": "Sabaton", "pageprops": {"wikibase-shortdesc": "Type of armour for the foot"}})
            elif t == "Sabaton (band)":
                pages.append({"title": "Sabaton (band)", "pageprops": {"wikibase-shortdesc": "Swedish power metal band"}})
            elif t == "rod stewart":
                continue
            else:
                pages.append({"title": t, "missing": True})
        return {"query": {"normalized": [{"from": "rod stewart", "to": "Rod stewart"}], "redirects": [{"from": "Rod stewart", "to": "Rod Stewart"}],
                          "pages": pages + [{"title": "Rod Stewart", "pageprops": {"wikibase-shortdesc": "British rock singer"}}]}}

    http = FakeHttp({wikipedia.API_URL: api})
    titles = wikipedia.WikipediaProvider(http).resolve_titles(["Sting", "rod stewart", "Sabaton", "Nepoznato Ime"])
    assert titles == {"rod stewart": "Rod Stewart", "Sting": "Sting (musician)", "Sabaton": "Sabaton (band)", "Nepoznato Ime": None}


def test_pageview_trend_from_real_fixture():
    data = load_fixture("wikimedia_pageviews_rod_stewart.json")
    views = [i["views"] for i in data["items"]]
    avg, ratio = wikipedia.trend_from_views(views)
    expected = (sum(views[-14:]) / 14) / (sum(views[:-14]) / len(views[:-14]))
    assert avg == round(sum(views[-14:]) / 14) and ratio == pytest.approx(expected, abs=1e-3)
    assert 0.5 < ratio < 2.0
    assert wikipedia.trend_from_views([10] * 20) == (None, None)
    http = FakeHttp({"https://wikimedia.org/": data})
    assert wikipedia.WikipediaProvider(http).pageviews("Rod Stewart", date(2026, 11, 21)) == views
    assert "Rod_Stewart/daily/20260909/20261121" in http.calls[0][0]


# ----------------------------------------------------------------------------- model
def test_demand_uses_deezer_fans_and_trend(make_event):
    ev = Evaluator(ModelConfig.load(), now=SNAP_NOW)
    none = ev.demand(make_event(artist_listeners=None), 50)
    fans = ev.demand(make_event(artist_listeners=None, artist_fans=1_500_000), 50)
    trend = ev.demand(make_event(artist_listeners=None, artist_fans=1_500_000, artist_trend=3.0), 50)
    assert fans.score > none.score and fans.confidence > none.confidence
    assert any("Deezer" in n for n in fans.notes)
    assert trend.score > fans.score and any("Wikipedia" in n for n in trend.notes)
    lastfm = ev.demand(make_event(artist_listeners=1_500_000, artist_fans=10), 50)
    assert not any("Deezer" in n for n in lastfm.notes)  # Last.fm ima prednost


def test_price_ceiling_without_face_value(make_event):
    ev = Evaluator(ModelConfig.load(), now=SNAP_NOW)
    sec = SecondaryMarket(source="viagogo", lowest=195.0, currency="EUR", observed="2026-11-20")
    op = ev.evaluate(make_event(face_min=None, face_max=None, secondary=sec, artist_fans=1_400_000, artist_listeners=None))
    assert op.verdict == "PROVJERI CIJENU"
    assert op.max_buy and op.breakeven_buy and op.max_buy < op.breakeven_buy < op.expected_resale
    at_ceiling = ev.evaluate(dataclasses.replace(op.event, face_min=op.max_buy, face_max=op.max_buy))
    assert at_ceiling.roi == pytest.approx(ModelConfig.load().get("verdict", "buy_roi"), abs=0.02)
    assert not any("stara" in f for f in op.risk_flags)


def test_price_ceiling_respects_face_value_laws_and_soldout(make_event):
    ev = Evaluator(ModelConfig.load(), now=SNAP_NOW)
    sec = SecondaryMarket(source="viagogo", lowest=195.0, currency="EUR", observed="2026-09-01")
    italy = ev.evaluate(make_event(country="IT", venue="Unipol Forum", city="Milano", face_min=None, face_max=None, secondary=sec))
    assert italy.verdict == "NEMA CIJENE" and italy.max_buy is None  # u Italiji je preprodaja iznad nominalne zabranjena
    sold = ev.evaluate(make_event(face_min=None, face_max=None, secondary=sec, status="soldout"))
    assert sold.verdict == "RASPRODANO"
    stale = ev.evaluate(make_event(face_min=None, face_max=None, secondary=sec))
    assert any("stara 82 dana" in f for f in stale.risk_flags)


# ----------------------------------------------------------------------------- snimka
def test_snapshot_loads_curated_tours_and_popularity():
    events, info, warnings = load_snapshot(SNAP_NOW)
    assert warnings == []
    assert info.date == "2026-11-22" and info.curated >= 10 and info.tour_events > 40
    curated = [e for e in events if e.source == CURATED_SOURCE]
    rod = next(e for e in curated if e.artist == "Rod Stewart")
    assert rod.secondary.lowest == 195 and rod.secondary.observed == "2026-09-29" and "farewell" in rod.tags
    assert rod.artist_fans and rod.artist_fans > 1_000_000  # iz popularnost.json
    fontaines = next(e for e in curated if e.artist == "Fontaines D.C.")
    assert (fontaines.face_min, fontaines.face_max) == (49, 52)
    assert all(e.url for e in curated)  # svaki provjereni događaj ima izvor
    hr_only, info_hr, _ = load_snapshot(SNAP_NOW, ["HR"])
    assert hr_only and all(e.country == "HR" for e in hr_only) and info_hr.tour_events == 0


def test_snapshot_scan_runs_offline_with_real_events(tmp_path):
    http = FakeHttp({})  # svaki mrežni poziv bi pao – snimka radi bez mreže
    result = run_scan(ScanOptions(snapshot=True, countries=["otvoreno"], now=SNAP_NOW), _settings(tmp_path), http=http)
    assert http.calls == []
    assert result.is_snapshot and result.snapshot["date_hr"] == "22.11.2026."
    verdicts = [op.verdict for op in result.opportunities]
    assert verdicts.count("PROVJERI CIJENU") >= 5 and "NEMA CIJENE" in verdicts
    orders = [VERDICT_ORDER[v] for v in verdicts]
    assert orders == sorted(orders)  # KUPI/RAZMOTRI → PROVJERI CIJENU → … → NEMA CIJENE
    assert "KUPI" in verdicts or "RAZMOTRI" in verdicts  # Scorpions (Zagreb) ima javnu nominalnu cijenu
    joksimovic = next(op for op in result.opportunities if op.event.artist == "Željko Joksimović" and op.event.date.day == 4)
    assert joksimovic.verdict == "RASPRODANO"
    sport = run_scan(ScanOptions(snapshot=True, countries=["HR"], now=SNAP_NOW, segment="sport"), _settings(tmp_path), http=http)
    assert sport.opportunities == [] and any("sportskih" in w for w in sport.warnings)


def test_user_snapshot_adds_and_overrides_events(tmp_path, monkeypatch):
    data_dir = tmp_path / "moja"
    (data_dir / "snimka").mkdir(parents=True)
    (data_dir / "snimka" / "dogadaji.csv").write_text(
        "izvodjac,naziv,dvorana,grad,drzava,datum,cijena_min,valuta,sek_najniza,sek_valuta,sek_izvor,sek_datum,fanovi,url\n"
        "Moj Bend,Moj Bend – Tvornica,Tvornica kulture,Zagreb,HR,2027-02-01,20,EUR,45,EUR,Njuškalo,2026-11-21,30000,https://primjer.hr\n"
        "Rod Stewart,Rod Stewart – Pula,Arena Pula,Pula,HR,2027-06-22,79,EUR,210,EUR,viagogo,2026-11-21,,https://primjer.hr/rod\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("KARTE_DATA_DIR", str(data_dir))
    events, info, _ = load_snapshot(SNAP_NOW, ["HR"])
    by_artist = {e.artist: e for e in events}
    assert "Moj Bend" in by_artist and "Fontaines D.C." in by_artist  # dopuna, ugrađeni događaji ostaju
    assert by_artist["Moj Bend"].artist_fans == 30000 and by_artist["Moj Bend"].secondary.observed == "2026-11-21"
    rod = [e for e in events if e.artist == "Rod Stewart"]
    assert len(rod) == 1 and rod[0].face_min == 79 and rod[0].secondary.lowest == 210  # korisnički redak zamjenjuje ugrađeni
    assert rod[0].artist_fans and "dogadaji.csv (2)" in info.origin


def test_refresh_snapshot_writes_user_files(tmp_path, monkeypatch):
    monkeypatch.setenv("KARTE_DATA_DIR", str(tmp_path / "osvjezeno"))
    twilight = load_fixture("wikipedia_tour_twilight.json")
    views = load_fixture("wikimedia_pageviews_rod_stewart.json")

    def api(params):
        if params.get("action") == "parse":
            if params["page"] == "Otkrivena Turneja":  # otkrivena turneja mora imati izvođača u infookviru
                infobox = ('<table class="infobox"><tr><td class="infobox-subheader"><span class="attendee">'
                           '<a href="/wiki/X">Otkriveni Izvođač</a></span></td></tr></table>')
                return {"parse": {"text": infobox + twilight["parse"]["text"]}}
            if params["page"] == "Twilight of the Punks":
                return twilight
            return {"error": {"code": "missingtitle", "info": "The page you specified doesn't exist."}}
        if params.get("list") == "categorymembers":
            return {"query": {"categorymembers": [{"title": "Otkrivena Turneja"}, {"title": "Twilight of the Punks"}]}}
        if params.get("prop") == "info":
            return {"query": {"pages": [{"title": t, "lastrevid": 7} for t in params["titles"].split("|")]}}
        return {"query": {"pages": [{"title": t, "pageprops": {"wikibase-shortdesc": "band"}} for t in params["titles"].split("|")]}}

    http = FakeHttp({wikipedia.API_URL: api, deezer.BASE_URL: {"data": []}, "https://wikimedia.org/": views})
    summary = refresh_snapshot(http, now=SNAP_NOW, log=lambda *_: None)
    assert ("Twilight of the Punks", 36) in summary["tours"]
    assert any("Unraveled" in err for err in summary["errors"])  # greška → ostaje prethodna verzija
    folder = tmp_path / "osvjezeno" / "snimka"
    assert {p.name for p in folder.iterdir()} == {"turneje.json", "popularnost.json", "dogadaji.csv"}
    assert (folder / "dogadaji.csv").read_text(encoding="utf-8").startswith("izvodjac,")  # prazan predložak za vlastite događaje
    tours = json.loads((folder / "turneje.json").read_text(encoding="utf-8"))
    assert {t["naslov"] for t in tours["turneje"]} >= {"Twilight of the Punks", "The Unraveled Tour"}
    pop = json.loads((folder / "popularnost.json").read_text(encoding="utf-8"))
    assert pop["izvodjaci"]["Rod Stewart"]["trend"] is not None
    assert "Otkrivena Turneja" in summary["new"]
    found = next(t for t in tours["turneje"] if t["naslov"] == "Otkrivena Turneja")
    assert found["izvor"] == "kategorija" and found["revid"] == 7
    assert found["koncerti"] and all(r["country"] != "US" for r in found["koncerti"])  # samo regija otkrivanja (Europa)
    events, info, _ = load_snapshot(SNAP_NOW)
    assert info.tours_date == "2026-11-22" and any(e.artist == "Fall Out Boy" for e in events)
    discovered = [t for t in info.tours if t["title"] == "Otkrivena Turneja"]
    assert discovered and discovered[0]["discovered"] and discovered[0]["new"]


def test_manual_csv_new_columns():
    text = ("izvodjac,datum,valuta,sek_najniza,sek_valuta,sek_datum,fanovi,trend\n"
            "A,2027-01-10,EUR,80,GBP,2026-11-01,250000,1.8\n")
    e = load_csv_text(text)[0]
    assert e.secondary.currency == "GBP" and e.secondary.observed == "2026-11-01"
    assert e.artist_fans == 250000 and e.artist_trend == 1.8


# ----------------------------------------------------------------------------- SerpApi / PredictHQ
def test_serpapi_parse_google_events():
    events = serpapi.parse_events(load_fixture("serpapi_google_events.json"), SNAP_NOW, "HR", "concerts in Zagreb")
    by_artist = {e.artist: e for e in events}
    assert len(events) == 5  # događaj bez datuma se preskače
    jok = by_artist["Željko Joksimović"]
    assert jok.date == datetime(2026, 12, 5, 20, 0) and jok.venue == "Arena Zagreb" and jok.country == "HR"
    assert jok.primary_vendor == "eventim" and jok.url == "https://www.eventim.hr/primjer" and jok.segment == "music"
    assert by_artist["Seka Aleksić"].date == datetime(2027, 3, 20, 21, 0)
    assert by_artist["Indie Night"].date == datetime(2027, 1, 12, 20, 30)  # "Jan 12" u studenom → iduća godina
    assert by_artist["GNK Dinamo vs HNK Hajduk"].segment == "sport"
    fob = by_artist["Fall Out Boy"]
    assert (fob.country, fob.region, fob.city) == ("US", "CA", "Los Angeles")


def test_serpapi_provider_queries_cities_and_filters_window():
    http = FakeHttp({serpapi.BASE_URL: load_fixture("serpapi_google_events.json")})
    sp = serpapi.SerpApiProvider("KEY", http)
    found = sp.events([("Zagreb", "HR")], SNAP_NOW, datetime(2027, 1, 31), "music")
    assert {e.artist for e in found} == {"Željko Joksimović", "Indie Night"}  # utakmica nije koncert, Seka je izvan prozora
    assert http.calls[0][1]["engine"] == "google_events" and http.calls[0][1]["q"] == "concerts in Zagreb"
    assert http.calls[0][1]["gl"] == "hr" and sp.warnings
    assert serpapi.default_cities(["HR", "AT"]) == [("Zagreb", "HR"), ("Split", "HR"), ("Pula", "HR"), ("Vienna", "AT")]
    assert serpapi.parse_cities("Zagreb, Beč:AT") == [("Zagreb", None), ("Beč", "AT")]
    empty = FakeHttp({serpapi.BASE_URL: {"error": "Google hasn't returned any results for this query."}})
    assert serpapi.SerpApiProvider("KEY", empty).events([("Pula", "HR")], SNAP_NOW, datetime(2027, 1, 1)) == []
    bad = FakeHttp({serpapi.BASE_URL: {"error": "Invalid API key."}})
    with pytest.raises(ProviderError, match="Invalid"):
        serpapi.SerpApiProvider("KEY", bad).events([("Pula", "HR")], SNAP_NOW, datetime(2027, 1, 1))


def test_predicthq_parse_and_auth_header():
    http = FakeHttp({predicthq.BASE_URL: load_fixture("predicthq_events.json")})
    events = predicthq.PredictHQProvider("TOKEN", http).events(["HR"], SNAP_NOW, datetime(2027, 7, 1), "all")
    rod, derby = events
    assert rod.artist == "Rod Stewart" and rod.city == "Pula" and rod.capacity == 6500 and rod.capacity_estimated
    assert derby.segment == "sport" and derby.sport == "football" and derby.status == "announced" and derby.city == "Split"
    assert http.headers[0] == {"Authorization": "Bearer TOKEN"}
    assert http.calls[0][1]["country"] == "HR" and http.calls[0][1]["category"] == "concerts,sports"
    loc = FakeHttp({predicthq.BASE_URL: load_fixture("predicthq_events.json")})
    predicthq.PredictHQProvider("TOKEN", loc, ["L1", "L2"]).events(["HR"], SNAP_NOW, datetime(2027, 7, 1))
    assert [c[1]["saved_location.location_id"] for c in loc.calls] == ["L1", "L2"] and "country" not in loc.calls[0][1]


def test_live_scan_with_serpapi_shows_discovery_events_and_enriches(tmp_path):
    http = FakeHttp({
        serpapi.BASE_URL: load_fixture("serpapi_google_events.json"),
        deezer.BASE_URL: {"data": [{"name": "Željko Joksimović", "nb_fan": 106111, "id": 1}]},
        wikipedia.API_URL: {"query": {"pages": []}},
    })
    settings = _settings(tmp_path, serpapi_key="KEY")
    result = run_scan(ScanOptions(countries=["HR"], now=SNAP_NOW, days=60), settings, http=http)
    artists = {op.event.artist for op in result.opportunities}
    assert "Željko Joksimović" in artists  # bez cijene, ali izvor je "otkrivajući" pa se prikazuje
    jok = next(op for op in result.opportunities if op.event.artist == "Željko Joksimović")
    assert jok.event.artist_fans == 106111
    assert any("SerpApi" in s for s in result.sources) and any("Deezer" in s for s in result.sources)


# ----------------------------------------------------------------------------- CLI / ostalo
def test_cli_scan_without_keys_uses_snapshot(tmp_path, monkeypatch, capsys):
    for key in ("TICKETMASTER_API_KEY", "SEATGEEK_CLIENT_ID", "SERPAPI_KEY", "PREDICTHQ_TOKEN", "LASTFM_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("KARTE_CACHE_DIR", str(tmp_path / "cache"))
    assert main(["--env", str(tmp_path / "nema.env"), "scan", "--top", "3", "--details", "0", "--countries", "HR"]) == 0
    out = capsys.readouterr().out
    assert "STVARNI PODACI" in out and "Nema API ključeva" in out
    assert main(["--env", str(tmp_path / "nema.env"), "snimka", "--countries", "HR"]) == 0
    assert "Snimka stvarnih događaja – stanje 22.11.2026." in capsys.readouterr().out


def test_hr_plural():
    assert [hr_plural(n, "datum", "datuma") for n in (1, 2, 5, 11, 21, 43, 81)] == ["datum", "datuma", "datuma", "datuma", "datum", "datuma", "datum"]


def test_gui_app_snapshot_source_and_meta(tmp_path):
    from karte.gui.server import App

    app = App(_settings(tmp_path), journal_path=tmp_path / "dnevnik.json")
    meta = app.meta()
    assert meta["snapshot"]["date"] == "2026-11-22" and meta["settings"]["live_sources"] == []
    result = app.scan({"source": "snapshot", "countries": "HR"})
    assert result["is_snapshot"] and not result["is_demo"] and result["snapshot"]["date_hr"] == "22.11.2026."
    rod = next((o for o in result["opportunities"] if o["event"]["artist"] == "Rod Stewart"), None)
    if rod is not None:  # događaj je u budućnosti dok traje snimka
        assert rod["secondary_lowest_eur"] == 195.0
    demo = app.scan({"source": "demo", "countries": "HR"})
    assert demo["is_demo"] and not demo["is_snapshot"]
