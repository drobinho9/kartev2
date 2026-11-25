"""Alternativa za Ticketmaster API: RSS najave, uvoz sa stranica (JSON-LD), otkrivanje turneja na Wikipediji."""

import base64
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime

import pytest

from conftest import FakeHttp, load_fixture
from karte import announcements as ann
from karte import capture
from karte.cli import main
from karte.net import ProviderError
from karte.pipeline import ScanOptions, run_scan
from karte.providers import deezer, wikipedia
from karte.settings import Settings
from karte.snapshot import delete_user_event, list_user_events, load_snapshot, refresh_snapshot, save_user_events

NOW = datetime(2026, 11, 25, 12, 0)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("KARTE_DATA_DIR", str(tmp_path / "karte-data"))


def _settings(tmp_path) -> Settings:
    return Settings(ticketmaster_api_key=None, seatgeek_client_id=None, lastfm_api_key=None,
                    countries=["HR"], budget=1000.0, cache_dir=tmp_path / "cache")


RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Glazba</title>
<item><title>Foo Fighters stižu u Zagreb</title><link>https://primjer.hr/foo</link>
<pubDate>Mon, 23 Nov 2026 09:00:00 +0000</pubDate><category>Koncerti</category>
<description><![CDATA[<p>Koncert će se održati 27. lipnja 2027. na Hipodromu. Ulaznice u prodaji od petka, 27. studenoga u 10 sati,
a presale za članove fan kluba počinje 25. studenoga u 10:00.</p>]]></description></item>
<item><title>Novi festival stiže u Split</title><link>https://primjer.hr/festival</link>
<pubDate>Sun, 22 Nov 2026 09:00:00 +0000</pubDate><description>Festival 3. srpnja 2027. u Splitu.</description></item>
<item><title>Stara vijest o koncertu</title><link>https://primjer.hr/staro</link>
<pubDate>Mon, 01 Jun 2026 09:00:00 +0000</pubDate><description>Koncert</description></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Tours</title>
<entry><title>Fall Out Boy announce European tour</title><link href="https://primjer.com/fob"/>
<published>2026-11-24T15:00:00Z</published><category term="Music"/>
<summary>The band plays London's O2 Arena on June 12, 2027. Tickets go on general sale Friday, December 4 at 10am,
with an artist presale on Wednesday, December 2.</summary></entry>
<entry><title>Chef opens new restaurant</title><link href="https://primjer.com/food"/>
<published>2026-11-24T15:00:00Z</published><category term="Food"/><summary>Menu and prices.</summary></entry>
</feed>"""


def _deezer(params):
    found = {"Foo Fighters": 4_600_000, "Fall Out Boy": 3_100_000}
    name = (params or {}).get("q", "").strip('"').replace('artist:"', "")
    if name in found:
        return {"data": [{"id": 1, "name": name, "nb_fan": found[name], "link": "https://www.deezer.com/artist/1"}]}
    return {"data": []}


# ----------------------------------------------------------------------------- RSS i analiza teksta
def test_parse_feed_reads_rss_and_atom():
    items = ann.parse_feed(RSS)
    assert [i["title"] for i in items][:2] == ["Foo Fighters stižu u Zagreb", "Novi festival stiže u Split"]
    assert items[0]["published"] == datetime(2026, 11, 23, 9, 0) and items[0]["categories"] == ["Koncerti"]
    assert "<p>" not in items[0]["summary"] and "Hipodromu" in items[0]["summary"]
    atom = ann.parse_feed(ATOM)
    assert atom[0]["link"] == "https://primjer.com/fob" and atom[0]["published"] == datetime(2026, 11, 24, 15, 0)
    assert ann.parse_feed("<html>nije feed") == []


def test_sale_dates_croatian_and_english():
    ref = datetime(2026, 11, 23, 9, 0)
    hr = ("Koncert će se održati 27. lipnja 2027. na Hipodromu. Ulaznice u prodaji od petka, 27. studenoga u 10 sati, "
          "a presale za članove fan kluba počinje 25. studenoga u 10:00.")
    onsale, presale, event = ann.sale_dates(hr, ref)
    assert onsale == datetime(2026, 11, 27, 10, 0) and presale == datetime(2026, 11, 25, 10, 0) and event == date(2027, 6, 27)
    en = ("The band plays London's O2 Arena on June 12, 2027. Tickets go on general sale Friday, December 4 at 10am, "
          "with an artist presale on Wednesday, December 2.")
    onsale, presale, event = ann.sale_dates(en, datetime(2026, 11, 24))
    assert onsale == datetime(2026, 12, 4, 10, 0) and presale == datetime(2026, 12, 2) and event == date(2027, 6, 12)
    # dijakritici u mjesecu i godina iz konteksta (siječanj iza studenoga → iduća godina)
    _, _, event = ann.sale_dates("Koncert 5. veljače u Areni", ref)
    assert event == date(2027, 2, 5)


def test_artist_candidates_and_places():
    assert ann.artist_candidates("Foo Fighters stižu u Zagreb")[0] == "Foo Fighters"
    assert ann.artist_candidates("As I Lay Dying announce European tour")[0] == "As I Lay Dying"
    assert ann.artist_candidates("Legendarni Scorpions dolaze u Arenu Zagreb")[0] == "Scorpions"
    assert ann.artist_candidates("Stray Kids 2027 announce stadium tour")[0] == "Stray Kids"
    assert ann.artist_candidates("Koncert godine") == []  # nema glagola najave
    places, countries, score = ann.detect_places("Nastup u Stožicama i Areni Zagreb")
    assert "Zagreb" in places and countries == ["HR", "SI"] and score == 3
    assert ann.detect_places("London, O2 Arena")[1:] == (["GB"], 1)


def test_fetch_announcements_filters_enriches_and_tracks_new(tmp_path):
    sources = [{"naziv": "HR", "url": "https://primjer.hr/feed/", "vrsta": "opcenito"},
               {"naziv": "EN", "url": "https://primjer.com/atom", "vrsta": "turneje"},
               {"naziv": "Pokvaren", "url": "https://pokvaren.example/feed", "vrsta": "turneje"}]
    http = FakeHttp({"https://primjer.hr/feed/": RSS, "https://primjer.com/atom": ATOM,
                     "https://pokvaren.example/": ProviderError("HTTP 404"), deezer.BASE_URL: _deezer})
    data_dir = tmp_path / "podaci"
    items, warnings = ann.fetch_announcements(http, now=NOW, days=21, sources=sources, data_dir=data_dir)
    titles = [a.title for a in items]
    assert "Stara vijest o koncertu" not in titles  # starije od 21 dan
    assert "Chef opens new restaurant" in titles  # izvor "turneje" – sve stavke ostaju…
    assert any("Pokvaren" in w for w in warnings)
    foo = next(a for a in items if a.artist == "Foo Fighters")
    assert foo.fans == 4_600_000 and foo.countries == ["HR"] and foo.region_score == 3 and foo.new
    assert foo.onsale == datetime(2026, 11, 27, 10, 0) and foo.event_date == date(2027, 6, 27)
    assert items[0] is foo  # Hrvatska + datum prodaje + puno fanova → na vrhu
    festival = next(a for a in items if a.link.endswith("/festival"))
    assert festival.artist is None  # "Novi festival" nije izvođač na Deezeru
    fob = next(a for a in items if a.link.endswith("/fob"))
    assert fob.artist == "Fall Out Boy" and fob.countries == ["GB"] and fob.presale == datetime(2026, 12, 2)
    d = foo.as_dict()
    assert d["onsale"] == "2026-11-27T10:00:00" and d["new"] and d["score"] > fob.score
    ann.mark_seen(data_dir, [a.link for a in items])
    again, _ = ann.fetch_announcements(http, now=NOW, sources=sources, data_dir=data_dir, enrich=False)
    assert not any(a.new for a in again)


def test_general_sources_keep_only_concert_news():
    source = {"naziv": "Portal", "vrsta": "opcenito"}
    keep = ann.analyse({"title": "Dubioza kolektiv najavila koncert u Areni", "summary": "", "link": "x"}, source, NOW)
    drop = ann.analyse({"title": "Vlada donijela odluku", "summary": "Porezi.", "link": "y"}, source, NOW)
    film = ann.analyse({"title": "Film stiže u kina", "summary": "concert film", "link": "z", "categories": ["Film"]}, source, NOW)
    assert keep is not None and drop is None and film is None


def test_sources_file_and_user_extension(tmp_path):
    sources = ann.load_sources()
    assert len(sources) >= 8 and all(s["url"].startswith("https://") for s in sources)
    assert {s["vrsta"] for s in sources} <= {"turneje", "opcenito"}
    extra = tmp_path / "najave.toml"
    extra.write_text('[[izvor]]\nnaziv = "Moj"\nurl = "https://moj.example/feed"\nvrsta = "turneje"\n', encoding="utf-8")
    assert ann.load_sources(extra)[-1]["naziv"] == "Moj"


def test_add_own_source_google_alerts(tmp_path, capsys):
    data = tmp_path / "podaci"
    url = "https://www.google.com/alerts/feeds/123/456"
    added, src = ann.add_source(data, url, 'Google Alerts: "Arena Zagreb" ulaznice')
    assert added and src["vrsta"] == "opcenito"
    assert ann.add_source(data, url)[0] is False  # već postoji
    with pytest.raises(ValueError):
        ann.add_source(data, "nije adresa")
    sources = ann.load_sources(data / "najave.toml")
    assert sources[-1] == {"naziv": 'Google Alerts: "Arena Zagreb" ulaznice', "url": url, "jezik": "hr", "vrsta": "opcenito"}
    # Google Alerts šalje Atom s <b> oznakama u naslovu
    feed = ('<feed xmlns="http://www.w3.org/2005/Atom"><entry><title type="html">Koncert u &lt;b&gt;Areni Zagreb&lt;/b&gt;</title>'
            '<link href="https://www.google.com/url?q=https://primjer.hr/a"/><published>2026-11-24T08:00:00Z</published>'
            '<content type="html">Ulaznice u prodaji od 1. prosinca u 10 sati.</content></entry></feed>')
    item = ann.parse_feed(feed)[0]
    assert item["title"] == "Koncert u Areni Zagreb"
    a = ann.analyse(item, sources[-1], NOW)
    assert a.onsale == datetime(2026, 12, 1, 10, 0) and a.region_score == 3


def test_cli_najave_sources(tmp_path, capsys):
    env = ["--env", str(tmp_path / "nema.env")]
    assert main(env + ["najave", "--dodaj-izvor", "https://dvorana.example/feed", "--naziv", "Moja dvorana", "--samo-koncerti"]) == 0
    assert "Dodan izvor „Moja dvorana”" in capsys.readouterr().out
    assert main(env + ["najave", "--dodaj-izvor", "https://dvorana.example/feed"]) == 0
    assert "Već postoji" in capsys.readouterr().out
    assert main(env + ["najave", "--dodaj-izvor", "ftp://x"]) == 2
    capsys.readouterr()
    assert main(env + ["najave", "--izvori"]) == 0
    out = capsys.readouterr().out
    assert "Moja dvorana: https://dvorana.example/feed (turneje)" in out and "muzika.hr" in out


# ----------------------------------------------------------------------------- uvoz sa stranice (JSON-LD)
TM_PAGE = """<html><head><title>Foo Fighters | Ticketmaster</title>
<meta property="og:title" content="Foo Fighters – Hipodrom Zagreb">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"MusicEvent","name":"Foo Fighters",
"startDate":"2027-06-27T20:00:00+02:00","eventStatus":"https://schema.org/EventScheduled",
"location":{"@type":"Place","name":"Hipodrom Zagreb","address":{"@type":"PostalAddress","addressLocality":"Zagreb","addressCountry":"HR"}},
"performer":[{"@type":"MusicGroup","name":"Foo Fighters"}],
"offers":{"@type":"AggregateOffer","lowPrice":"69","highPrice":"129.5","priceCurrency":"EUR","validFrom":"2026-11-27T10:00:00+01:00",
"availability":"https://schema.org/InStock","url":"https://www.eventim.hr/event/foo"}}]}</script>
<script type="application/ld+json">{"@type":"BreadcrumbList","itemListElement":[]}</script>
</head><body>…</body></html>"""

VIAGOGO_PAGE = """<html><head><title>Foo Fighters Tickets</title>
<script type="application/ld+json">[{"@type":"MusicEvent","name":"Foo Fighters - Zagreb","startDate":"2027-06-27T20:00",
"location":{"@type":"Place","name":"Hipodrom","address":"Zagreb, Croatia"},
"offers":[{"@type":"Offer","price":"180","priceCurrency":"EUR"},{"@type":"Offer","price":"145.00","priceCurrency":"EUR"}]},
{"@type":"MusicEvent","name":"Foo Fighters - Beograd","startDate":"2027-06-29T20:00","eventStatus":"EventCancelled",
"location":{"@type":"Place","name":"Ušće","address":{"addressLocality":"Beograd","addressCountry":"Serbia"}},
"offers":{"@type":"Offer","price":"90","priceCurrency":"EUR","availability":"SoldOut"}}]</script></head></html>"""


def test_capture_primary_vendor_page_reads_face_value():
    payload = capture.payload_from_html(TM_PAGE, "https://www.eventim.hr/event/foo-fighters-hipodrom-zagreb-123/")
    assert payload["ogTitle"] == "Foo Fighters – Hipodrom Zagreb" and len(payload["ld"]) == 2
    rows = capture.event_rows(payload, today=date(2026, 11, 25))
    assert len(rows) == 1
    r = rows[0]
    assert (r["izvodjac"], r["dvorana"], r["grad"], r["drzava"], r["datum"], r["vrijeme"]) == \
        ("Foo Fighters", "Hipodrom Zagreb", "Zagreb", "HR", "2027-06-27", "20:00")  # lokalno vrijeme sa stranice, ne UTC
    assert (r["cijena_min"], r["cijena_max"], r["valuta"], r["prodavac"]) == ("69", "129.5", "EUR", "eventim")
    assert r["status"] == "najava" and r["prodaja_od"] == "2026-11-27 10:00" and r["sek_najniza"] == ""


def test_capture_resale_page_reads_secondary_price_and_status():
    rows = capture.event_rows({"url": "https://www.viagogo.com/Concert-Tickets/Rock/Foo-Fighters-Tickets/E-1", "ld": [VIAGOGO_PAGE.split(
        '<script type="application/ld+json">')[1].split("</script>")[0]]}, today=date(2026, 11, 25))
    zg, bg = rows
    assert zg["izvodjac"] == "Foo Fighters" and zg["grad"] == "Zagreb" and zg["drzava"] == "HR"
    assert (zg["sek_najniza"], zg["sek_izvor"], zg["sek_datum"], zg["cijena_min"]) == ("145", "viagogo", "2026-11-25", "")
    assert bg["drzava"] == "RS" and bg["status"] == "otkazano"
    empty = capture.event_rows({"url": "https://www.stubhub.com/x", "title": "Neki događaj", "ld": []})
    assert empty[0]["naziv"] == "Neki događaj" and empty[0]["sek_izvor"] == "StubHub" and not empty[0]["datum"]


def test_decode_payload_and_bookmarklet():
    payload = {"v": 1, "url": "https://primjer.hr", "ld": ['{"@type":"Event"}'], "title": "Ćevapi & šljivovica"}
    raw = json.dumps(payload).encode()
    assert capture.decode_payload(base64.b64encode(raw).decode()) == payload
    assert capture.decode_payload(base64.urlsafe_b64encode(raw).decode().rstrip("=")) == payload
    assert capture.decode_payload(json.dumps(payload)) == payload
    with pytest.raises(ValueError):
        capture.decode_payload("ovo nije base64!")
    code = capture.bookmarklet(8899)
    assert code.startswith("javascript:") and " " not in code and "#" not in code  # "#" kodiran (%23) – sigurno u svim preglednicima
    decoded = urllib.parse.unquote(code)  # preglednik dekodira javascript: adresu prije izvršavanja
    assert "http://127.0.0.1:8899/#uvoz=" in decoded and "application/ld+json" in decoded


def test_user_events_save_merge_and_delete():
    rows = capture.event_rows(capture.payload_from_html(TM_PAGE, "https://www.eventim.hr/event/x/"), today=date(2026, 11, 25))
    assert save_user_events(rows) == (1, 0)
    # isti događaj s viagoga dopunjuje redak (cijena preprodaje), datum u hrvatskom obliku
    assert save_user_events([{"izvodjac": "Foo Fighters", "grad": "Zagreb", "datum": "27.06.2027.", "sek_najniza": "145",
                              "sek_valuta": "EUR", "sek_izvor": "viagogo", "sek_datum": "2026-11-25"}]) == (0, 1)
    assert save_user_events([{"izvodjac": "Bez datuma"}, {"naziv": "", "datum": "2027-01-01"}]) == (0, 0)
    saved = list_user_events()
    assert len(saved) == 1 and saved[0]["cijena_min"] == "69" and saved[0]["sek_najniza"] == "145"
    events, info, _ = load_snapshot(NOW, ["HR"])
    foo = next(e for e in events if e.artist == "Foo Fighters" and e.source != "Wikipedia")
    assert foo.face_min == 69 and foo.secondary.lowest == 145 and foo.primary_vendor == "eventim"
    assert "dogadaji.csv (1)" in info.origin
    assert delete_user_event("foo fighters|2027-06-27|zagreb") and list_user_events() == []
    assert not delete_user_event("nema|2027-01-01|nigdje")


def test_cli_import_saved_page_and_announcements(tmp_path, monkeypatch, capsys):
    page = tmp_path / "stranica.html"
    page.write_text(TM_PAGE, encoding="utf-8")
    env = ["--env", str(tmp_path / "nema.env")]
    assert main(env + ["uvoz", str(page), "--url", "https://www.eventim.hr/event/x/", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "2027-06-27  Foo Fighters  Hipodrom Zagreb, Zagreb (HR)  nominalna 69–129.5 EUR" in out and "probno" in out
    assert list_user_events() == []
    assert main(env + ["uvoz", str(page)]) == 0
    assert "1 novih" in capsys.readouterr().out and len(list_user_events()) == 1
    empty = tmp_path / "prazno.html"
    empty.write_text("<html><title>Ništa</title></html>", encoding="utf-8")
    assert main(env + ["uvoz", str(empty)]) == 1

    def fake_fetch(http, days=21, enrich=True, data_dir=None, **kw):
        a = ann.analyse(ann.parse_feed(RSS)[0], {"naziv": "Test", "vrsta": "turneje"}, NOW)
        a.fans, a.new = 4_600_000, True
        b = ann.analyse(ann.parse_feed(ATOM)[0], {"naziv": "Test", "vrsta": "turneje"}, NOW)
        return [a, b], ["Najave – X: HTTP 403"]

    monkeypatch.setattr(ann, "fetch_announcements", fake_fetch)
    assert main(env + ["najave", "--regija", "hr", "--ne-oznaci"]) == 0
    out = capsys.readouterr().out
    assert "NOVO" in out and "Foo Fighters (4.600.000 fanova)" in out and "prodaja 27.11.2026. 10:00" in out
    assert "Fall Out Boy" not in out and "! Najave – X: HTTP 403" in out


# ----------------------------------------------------------------------------- GUI rute
@pytest.fixture
def server(tmp_path):
    from karte.gui.server import App, make_server

    app = App(_settings(tmp_path), journal_path=tmp_path / "dnevnik.json")
    srv = make_server(app, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}", srv.server_port
    srv.shutdown()
    srv.server_close()


def _call(base, path, body=None, method=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def test_gui_import_and_my_events_routes(server):
    base, port = server
    status, mine = _call(base, "/api/moji")
    assert status == 200 and mine["rows"] == [] and f"127.0.0.1:{port}" in mine["bookmarklet"]
    payload = capture.payload_from_html(TM_PAGE, "https://www.eventim.hr/event/x/")
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    status, parsed = _call(base, "/api/uvoz/parse", {"payload": encoded})
    assert status == 200 and parsed["rows"][0]["izvodjac"] == "Foo Fighters" and parsed["url"].startswith("https://www.eventim.hr")
    assert _call(base, "/api/uvoz/parse", {"payload": "%%%"})[0] == 400
    status, saved = _call(base, "/api/moji", {"rows": parsed["rows"]})
    assert status == 200 and saved["added"] == 1 and saved["rows"][0]["key"] == "foo fighters|2027-06-27|zagreb"
    assert _call(base, "/api/moji", {"rows": parsed["rows"]}, headers={"Origin": "https://zla.example"})[0] == 403
    assert _call(base, "/api/najave/procitano", {"links": ["https://primjer.hr/foo"]})[1] == {"marked": 1}
    status, src = _call(base, "/api/najave/izvor", {"url": "https://www.google.com/alerts/feeds/1/2", "naziv": "Alert"})
    assert status == 200 and src["added"] and src["count"] >= 9
    assert _call(base, "/api/najave/izvor", {"url": "javascript:alert(1)"})[0] == 400
    status, after = _call(base, "/api/moji?kljuc=foo%20fighters%7C2027-06-27%7Czagreb", method="DELETE")
    assert status == 200 and after["deleted"] and after["rows"] == []


def test_gui_announcements_route_filters_region(tmp_path, monkeypatch):
    from karte.gui.server import App

    def fake_fetch(http, days=21, data_dir=None, **kw):
        a = ann.analyse(ann.parse_feed(RSS)[0], {"naziv": "Test", "vrsta": "turneje"}, NOW)
        b = ann.analyse(ann.parse_feed(ATOM)[0], {"naziv": "Test", "vrsta": "turneje"}, NOW)
        return [a, b], []

    monkeypatch.setattr(ann, "fetch_announcements", fake_fetch)
    app = App(_settings(tmp_path), journal_path=tmp_path / "dnevnik.json")
    hr = app.announcements(21, "hr")
    assert hr["total"] == 2 and [i["title"] for i in hr["items"]] == ["Foo Fighters stižu u Zagreb"]
    assert len(app.announcements(21, "europa")["items"]) == 2


# ----------------------------------------------------------------------------- otkrivanje turneja (Wikipedia kategorije)
INFOBOX = ('<table class="infobox"><tr><td class="infobox-subheader"><span class="attendee">'
           '<a href="/wiki/Otkriveni_Izvodjac">Otkriveni Izvođač</a></span></td></tr></table>')
US_ONLY = {"parse": {"title": "Samo Amerika", "text": (
    '<table class="wikitable"><tr><th>Date</th><th>City</th><th>Country</th><th>Venue</th></tr>'
    "<tr><td>March 3, 2027</td><td>Chicago</td><td>United States</td><td>United Center</td></tr></table>")}}


def test_refresh_remembers_tours_without_regional_dates(tmp_path, monkeypatch):
    monkeypatch.setenv("KARTE_DATA_DIR", str(tmp_path / "otkrivanje"))
    twilight = load_fixture("wikipedia_tour_twilight.json")
    parsed: list[str] = []

    def api(params):
        if params.get("action") == "parse":
            parsed.append(params["page"])
            if params["page"] == "Samo Amerika":
                return US_ONLY
            if params["page"] == "Bez Izvodjaca":  # europski datumi, ali bez izvođača u infookviru (npr. tribute show)
                return twilight
            if params["page"] == "Ista Turneja":  # "Tour by Ista Turneja" – show bez izvođača (npr. Disneyjeva franšiza)
                return {"parse": {"text": INFOBOX.replace("Otkriveni Izvođač", "Ista Turneja") + twilight["parse"]["text"]}}
            if params["page"] == "Otkrivena Turneja":
                return {"parse": {"text": INFOBOX + twilight["parse"]["text"]}}
            if params["page"] == "Twilight of the Punks":
                return twilight
            return {"error": {"code": "missingtitle", "info": "nema"}}
        if params.get("list") == "categorymembers":
            return {"query": {"categorymembers": [{"title": "Samo Amerika"}, {"title": "Otkrivena Turneja"}, {"title": "Bez Izvodjaca"},
                                                  {"title": "Ista Turneja"}]}}
        if params.get("prop") == "info":
            return {"query": {"pages": [{"title": t, "lastrevid": 7} for t in params["titles"].split("|")]}}
        return {"query": {"pages": []}}

    rest = wikipedia.REST_HTML_URL
    http = FakeHttp({
        rest + "Otkrivena_Turneja": INFOBOX + twilight["parse"]["text"],  # REST vraća gotov HTML članka
        rest + "Samo_Amerika": US_ONLY["parse"]["text"],
        rest: ProviderError("HTTP 404"),  # ostali → povratak na action=parse
        wikipedia.API_URL: api, deezer.BASE_URL: {"data": []}, "https://wikimedia.org/": {"items": []}})
    refresh_snapshot(http, now=datetime(2026, 11, 26, 10, 0), log=lambda *_: None, years=[2027])  # novije od ugrađene snimke
    tours = json.loads((tmp_path / "otkrivanje" / "snimka" / "turneje.json").read_text(encoding="utf-8"))
    assert tours["preskoceno"] == {"Samo Amerika": 7, "Bez Izvodjaca": 7, "Ista Turneja": 7}
    assert "Bez Izvodjaca" in parsed and "Otkrivena Turneja" not in parsed and "Samo Amerika" not in parsed  # REST
    parsed.clear()
    summary = refresh_snapshot(http, now=datetime(2026, 11, 27, 10, 0), log=lambda *_: None, years=[2027])
    # ista revizija → spremljeni članci (otkriveni, preskočeni i s popisa) se ne dohvaćaju ponovno
    assert not {"Samo Amerika", "Otkrivena Turneja", "Bez Izvodjaca", "Ista Turneja", "Twilight of the Punks"} & set(parsed)
    assert summary["new"] == [] or "Otkrivena Turneja" not in summary["new"]
    again = json.loads((tmp_path / "otkrivanje" / "snimka" / "turneje.json").read_text(encoding="utf-8"))
    assert again["preskoceno"] == {"Samo Amerika": 7, "Bez Izvodjaca": 7, "Ista Turneja": 7}
    found = next(t for t in again["turneje"] if t["naslov"] == "Otkrivena Turneja")
    assert found["izvodjac"] == "Otkriveni Izvođač" and found["koncerti"]


def test_tour_artist_from_infobox():
    html = ('<table class="infobox"><tr><td class="infobox-subheader"><span class="attendee">'
            '<a href="/wiki/Olivia_Rodrigo">Olivia Rodrigo</a></span></td></tr></table>')
    assert wikipedia.tour_artist(html) == "Olivia Rodrigo"
    assert wikipedia.tour_artist("<p>nema infoboxa</p>") is None
    # bez infookvira: kratki opis pa uvod (stvarni primjer: The Last King World Tour)
    short = '<div class="shortdescription nomobile noexcerpt">Upcoming concert tour by Don Omar</div><p>Tekst.</p>'
    assert wikipedia.tour_artist(short) == "Don Omar"
    lead = ('<p><b>The Last King World Tour</b> is an ongoing concert tour by Puerto Rican rapper and singer '
            '<a href="/wiki/Don_Omar" title="Don Omar">Don Omar</a>, commemorating…</p>')
    assert wikipedia.tour_artist(lead) == "Don Omar"
    tribute = ('<div class="shortdescription">Tribute act show featuring K-pop music</div>'
               '<p><b>K-Pop Forever!</b> is a touring tribute show.</p><p>A tour by <a href="/wiki/X">X</a></p>')
    assert wikipedia.tour_artist(tribute) is None  # "tour by" tek u drugom odlomku → ne računa se


def test_snapshot_hides_low_demand_tour_dates_without_price(tmp_path, monkeypatch):
    data = tmp_path / "radar"
    (data / "snimka").mkdir(parents=True)
    tour = {"azurirano": "2099-01-01", "turneje": [{
        "izvodjac": "Nepoznati Bend", "naslov": "Mala Turneja", "url": "https://en.wikipedia.org/wiki/X", "revid": 1,
        "izvor": "kategorija", "otkriveno": "", "koncerti": [
            {"date": "2027-03-01", "city": "Graz", "country": "AT", "country_name": "Austria", "venue": "Orpheum"}]}, {
        "izvodjac": "Slavni Bend", "naslov": "Velika Turneja", "url": "https://en.wikipedia.org/wiki/Y", "revid": 2,
        "izvor": "kategorija", "otkriveno": "", "koncerti": [
            {"date": "2027-04-01", "city": "Vienna", "country": "AT", "country_name": "Austria", "venue": "Stadthalle"}]}]}
    (data / "snimka" / "turneje.json").write_text(json.dumps(tour), encoding="utf-8")
    pop = {"azurirano": "2099-01-01", "izvodjaci": {"Slavni Bend": {"deezer_fanovi": 9_000_000, "trend": 2.5}}}
    (data / "snimka" / "popularnost.json").write_text(json.dumps(pop), encoding="utf-8")
    monkeypatch.setenv("KARTE_DATA_DIR", str(data))
    http = FakeHttp({})
    result = run_scan(ScanOptions(snapshot=True, countries=["AT"], now=NOW), _settings(tmp_path), http=http)
    assert not any(op.event.artist == "Nepoznati Bend" for op in result.opportunities)
    famous = [op for op in result.opportunities if op.event.artist == "Slavni Bend"]
    assert famous and famous[0].verdict == "NEMA CIJENE" and famous[0].demand.score >= 0.65  # jaka potražnja ostaje vidljiva
    assert any("Skriveno 1 datuma turneja" in w for w in result.warnings)
    shown = run_scan(ScanOptions(snapshot=True, countries=["AT"], now=NOW, show_all=True), _settings(tmp_path), http=http)
    unknown = [op for op in shown.opportunities if op.event.artist == "Nepoznati Bend"]
    assert unknown and unknown[0].verdict == "NEMA CIJENE"
    events, info, _ = load_snapshot(NOW, ["AT"])
    assert not any(t["new"] for t in info.tours if t["title"] == "Mala Turneja")  # "" = početna snimka, nije "nova"
