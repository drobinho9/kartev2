"""Grafičko sučelje (API), dnevnik prodaja, analiza kategorija, Markdown vodiči."""

import json
import threading
import urllib.error
import urllib.request

import pytest

from karte.gui.server import App, guide_list, make_server
from karte.journal import Journal
from karte.knowledge import ModelConfig
from karte.markdown import render
from karte.service import build_event, categories
from karte.settings import Settings


def _settings(tmp_path) -> Settings:
    return Settings(ticketmaster_api_key=None, seatgeek_client_id=None, lastfm_api_key=None,
                    countries=["otvoreno"], budget=1000.0, cache_dir=tmp_path / "cache")


# ------------------------------------------------------------------ markdown
def test_markdown_renders_and_escapes():
    html = render("# Naslov\n\nTekst **jako** i *kurziv* [link](https://x.hr) `kod`\n\n- a\n- b\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n<script>alert(1)</script>")
    assert '<h1 id="naslov">Naslov</h1>' in html
    assert "<strong>jako</strong>" in html and "<em>kurziv</em>" in html and "<code>kod</code>" in html
    assert '<a href="https://x.hr" target="_blank" rel="noopener">link</a>' in html
    assert "<ul><li>a</li><li>b</li></ul>" in html and "<td>1</td>" in html
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert "javascript" not in render("[x](javascript:alert(1))")


def test_guides_are_packaged_and_cover_topics():
    guides = guide_list()
    titles = " ".join(g["title"] for g in guides).lower()
    assert len(guides) >= 4
    assert "red" in titles and "viagogo" in titles and "kada" in titles


# ------------------------------------------------------------------ dnevnik
def test_journal_crud_stats_and_calibration(tmp_path):
    j = Journal(tmp_path / "d.json")
    t = j.upsert({"artist": "A$AP Rocky", "event_date": "2026-10-06", "qty": "2", "face_value": "69", "buy_price": "78",
                  "platform": "viagogo", "status": "prodano", "list_price": "150", "sell_net": "127", "sell_date": "2026-09-25",
                  "predicted_multiplier": "1.8"})
    assert t.sold_qty == 2 and t.realized_profit == pytest.approx(98) and t.days_before_event == 11
    j.upsert({"artist": "Otvoreno", "qty": 2, "buy_price": 50, "status": "oglaseno"})
    j.upsert({"artist": "Gubitak", "qty": 2, "buy_price": 40, "status": "neprodano", "sold_qty": 1, "sell_net": 20})
    st = j.stats(ModelConfig.load())
    assert st["count"] == 3 and st["closed"] == 2
    assert st["profit"] == pytest.approx(98 + (20 - 80))
    assert st["open_capital"] == pytest.approx(100)
    assert st["platforms"][0]["platform"] == "viagogo"
    cal = st["calibration"]
    assert cal["samples"] == 1 and cal["suggested_demand_slope"] > 1.7 and "podcjenjuje" in cal["message"]
    # uređivanje i brisanje
    j.upsert({"id": t.id, "sell_net": 100})
    assert [x for x in j.list() if x.id == t.id][0].sell_net == 100
    assert j.delete(t.id) and not j.delete("nema")
    # CSV izvoz/uvoz
    text = j.export_csv()
    j2 = Journal(tmp_path / "d2.json")
    assert j2.import_csv(text) == 2 and len(j2.list()) == 2


# ------------------------------------------------------------------ kategorije
def test_category_analysis_prefers_good_cheap_seats(tmp_path):
    ev = {"artist": "X", "venue": "Arena Zagreb", "date": "2027-03-01", "listeners": 3000000, "vendor": "eventim"}
    cats = [{"name": "Parter", "face": 59, "kind": "parter"}, {"name": "VIP", "face": 189, "kind": "vip"},
            {"name": "Zaklonjeno", "face": 39, "kind": "zaklonjeno"}]
    r = categories(ev, cats, _settings(tmp_path))
    by = {x["name"]: x for x in r["rows"]}
    assert by["Parter"]["roi"] > by["Zaklonjeno"]["roi"] > by["VIP"]["roi"]
    assert by["Parter"]["best_roi"] and "Parter" in r["summary"]
    # stvarna cijena s viagoga za kategoriju ima prednost
    r2 = categories(ev, [{"name": "VIP", "face": 189, "kind": "vip", "resale_lowest": 600}], _settings(tmp_path))
    assert "sekundarno" in r2["rows"][0]["multiplier_source"] and r2["rows"][0]["multiplier"] > 2


def test_build_event_from_form():
    e = build_event({"artist": "Y", "venue": "Arena Zagreb", "date": "2027-01-20", "time": "21:00", "face": "45,5",
                     "tags": "farewell, first_visit", "personalized": "da", "resale_lowest": "120", "listing_count": "80"})
    assert e.date.hour == 21 and e.face_min == 45.5 and e.capacity == 16000 and e.capacity_estimated
    assert e.tags == ["farewell", "first_visit"] and e.personalized is True
    assert e.secondary.lowest == 120 and e.secondary.listing_count == 80
    assert build_event({"artist": "Z", "personalized": "nepoznato"}).personalized is None


# ------------------------------------------------------------------ server
@pytest.fixture
def server(tmp_path):
    app = App(_settings(tmp_path), journal_path=tmp_path / "dnevnik.json")
    srv = make_server(app, port=0)
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()
    srv.server_close()


def call(base, path, body=None, method=None, headers=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if "json" in r.headers.get("Content-Type", "") else raw), r.headers
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode()), e.headers


def test_gui_server_endpoints(server):
    status, html, headers = call(server, "/")
    assert status == 200 and "Radar ulaznica" in html and "default-src 'self'" in headers["Content-Security-Policy"]
    assert call(server, "/static/app.js")[0] == 200
    assert call(server, "/static/..%2Fserver.py")[0] == 404
    _, meta, _ = call(server, "/api/meta")
    assert "otvoreno" in meta["regions"] and meta["settings"]["ticketmaster"] is False
    _, scan, _ = call(server, "/api/scan", {"demo": True, "countries": "otvoreno"})
    assert scan["is_demo"] and any(o["verdict"] == "KUPI" for o in scan["opportunities"])
    assert "location" in scan["opportunities"][0]
    _, calc, _ = call(server, "/api/calc", {"artist": "T", "face": 50, "resale_lowest": 140, "listeners": 2000000, "capacity": 16000})
    assert calc["opportunity"]["verdict"] in ("KUPI", "RAZMOTRI") and calc["opportunity"]["advice"]["ladder"][0]["iso"] is None
    _, cats, _ = call(server, "/api/categories", {"event": {"artist": "T", "listeners": 2000000},
                                                   "categories": [{"name": "A", "face": 50, "kind": "parter"}]})
    assert cats["rows"][0]["name"] == "A"
    _, j, _ = call(server, "/api/journal", {"artist": "A$AP Rocky", "qty": 2, "buy_price": 78, "status": "kupljeno"})
    tid = j["trade"]["id"]
    assert j["stats"]["open_capital"] == pytest.approx(156)
    status, j, _ = call(server, f"/api/journal/{tid}", method="DELETE")
    assert status == 200 and j["deleted"] and j["trades"] == []
    assert call(server, "/api/markets")[1]["rows"][0]["code"]
    assert "Vermont" in call(server, "/api/laws?code=US-VT")[1]["name"]
    assert len(call(server, "/api/guides")[1]["guides"]) >= 4
    _, rep, headers = call(server, "/api/report", {"demo": True, "format": "csv"})
    assert rep.startswith("verdict,") and "attachment" in headers["Content-Disposition"]


def test_gui_rejects_foreign_origin(server):
    status, body, _ = call(server, "/api/journal", {"artist": "X"}, headers={"Origin": "https://evil.example"})
    assert status == 403
    status, _, _ = call(server, "/api/journal", {"artist": "X"}, headers={"Origin": server})
    assert status == 200
