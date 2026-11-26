"""Paketi (gotovi prijedlozi kupnje/prodaje) i nogomet (raspored bez ključa, derbiji, jasna pravila preprodaje)."""

from datetime import datetime

import pytest
from conftest import FakeHttp, load_fixture

from karte import football
from karte.cli import main
from karte.gui.server import App
from karte.knowledge import ModelConfig
from karte.models import SecondaryMarket
from karte.paketi import FORBIDDEN, build_packages, describe
from karte.pipeline import ScanOptions, run_scan
from karte.providers import fixtures
from karte.scoring import Evaluator
from karte.service import football_matches, packages
from karte.settings import Settings


def _settings(tmp_path, **kw) -> Settings:
    return Settings(ticketmaster_api_key=None, seatgeek_client_id=None, lastfm_api_key=None, countries=["otvoreno"],
                    budget=1000.0, cache_dir=tmp_path / "cache", **kw)


# ------------------------------------------------------------------ klubovi i derbiji
def test_find_club_handles_names_from_different_sources():
    assert football.find_club("GNK Dinamo").name == "Dinamo Zagreb"
    assert football.find_club("Dinamo Zagreb").country == "HR"
    assert football.find_club("Dynamo Kyiv") is None  # „Dinamo” samo za točno podudaranje
    assert football.find_club("Man Utd").name == "Manchester United"
    assert football.find_club("RCD Espanyol de Barcelona").name == "Espanyol"
    assert football.find_club("FC Barcelona").name == "Barcelona"
    assert football.find_club("Paris").name == "Paris Saint-Germain"
    assert football.find_club("Paris FC") is None
    assert football.find_club("Inter Escaldes") is None and football.find_club("Internazionale").name == "Inter"


def test_match_info_tags_derby_big_and_local():
    derby = football.match_info("Dinamo Zagreb", "Hajduk Split")
    assert derby.derby == "Vječni derbi" and "derby" in derby.tags and derby.involves("HR")
    big = football.match_info("GNK Dinamo", "Leverkusen")
    assert big.tags == ["big_match"] and "Leverkusen" in big.reason
    assert football.match_info("Arsenal", "Real Madrid").tags == ["big_match"]
    plain = football.match_info("Viking", "Feyenoord")
    assert not plain.tags and not football.is_notable(plain)
    assert football.is_notable(football.match_info("Hajduk Split", "Nordsjælland"))


# ------------------------------------------------------------------ raspored bez ključa
def test_parse_fixturedownload_skips_played_and_tba(now):
    rows = fixtures.parse_fixturedownload(load_fixture("fixturedownload_sample.json"), "europa-league", now, datetime(2027, 6, 1))
    names = [e.name for e, _ in rows]
    assert "Sunderland – GNK Dinamo" not in names  # odigrano
    assert not any("To be announced" in n for n in names)
    e, info = next(r for r in rows if r[0].name == "Rennes – GNK Dinamo")
    assert e.segment == "sport" and e.sport == "football" and e.league == "UEFA Europska liga"
    assert e.country == "FR" and e.city == "Rennes" and e.venue == "Roazhon Park"
    assert e.date == datetime(2026, 12, 10, 18, 45)  # 17:45 UTC → 18:45 CET
    assert e.url == "https://tickets.gnkdinamo.hr"  # gostujući sektor prodaje Dinamo


def test_to_cet_handles_summer_time():
    assert fixtures.to_cet(datetime(2027, 6, 1, 18, 0)) == datetime(2027, 6, 1, 20, 0)
    assert fixtures.to_cet(datetime(2027, 1, 20, 20, 0)) == datetime(2027, 1, 20, 21, 0)
    assert fixtures.season_start_year(datetime(2026, 11, 26)) == 2026 and fixtures.season_start_year(datetime(2027, 3, 1)) == 2026


def test_football_events_filters_notable_and_countries(now):
    http = FakeHttp({"https://fixturedownload.com/": load_fixture("fixturedownload_sample.json")})
    events, warnings, sources = fixtures.football_events(http, now, datetime(2027, 1, 17), ["HR", "GB"], feeds=["europa-league"])
    names = {e.name for e in events}
    assert names == {"Rennes – GNK Dinamo", "Hajduk Split – Nordsjælland", "Arsenal – Real Madrid"}  # Viking – Feyenoord nije zanimljiv
    assert http.calls[0][0] == "https://fixturedownload.com/feed/json/europa-league-2026"
    assert not warnings and "fixturedownload" in sources[0]
    only_hr, _, _ = fixtures.football_events(http, now, datetime(2027, 1, 17), ["HR"], feeds=["europa-league"])
    assert "Arsenal – Real Madrid" not in {e.name for e in only_hr}  # GB nije odabran, nema hrvatskog kluba


def test_api_football_parser_and_errors(now):
    rows = fixtures.parse_api_football(load_fixture("apifootball_primjer.json"), now, datetime(2027, 1, 17))
    assert [e.name for e, _ in rows] == ["Dinamo Zagreb – Hajduk Split", "NK Osijek – HNK Rijeka"]  # odigrana preskočena
    derby, info = rows[0]
    assert derby.league == "SuperSport HNL" and derby.country == "HR" and derby.city == "Zagreb" and info.derby == "Vječni derbi"
    assert rows[1][0].status == "postponed"
    with pytest.raises(fixtures.ProviderError, match="plan"):
        fixtures.parse_api_football({"errors": {"plan": "Free plans do not have access to this season"}}, now, now)


def test_football_events_uses_api_football_key(now):
    http = FakeHttp({"https://fixturedownload.com/": [], fixtures.API_FOOTBALL_URL: load_fixture("apifootball_primjer.json")})
    events, _, sources = fixtures.football_events(http, now, datetime(2027, 1, 17), ["HR"], api_football_key="K", feeds=[])
    assert {e.name for e in events} == {"Dinamo Zagreb – Hajduk Split", "NK Osijek – HNK Rijeka"}
    assert http.headers[-1] == {"x-apisports-key": "K"} and http.calls[-1][1]["league"] == 210
    assert any("API-Football" in s for s in sources)


# ------------------------------------------------------------------ presude za nogomet bez cijene
@pytest.mark.parametrize("country,verdict", [("HR", "UVJETI ZABRANJUJU"), ("GB", "ZAKONSKI OGRANIČENO"), ("DE", "UVJETI ZABRANJUJU"),
                                             ("US", "NEMA CIJENE")])
def test_football_without_price_gets_clear_verdict(make_event, now, country, verdict):
    ev = Evaluator(ModelConfig.load(), now=now)
    op = ev.evaluate(make_event(segment="sport", sport="football", name="A – B", artist="A – B", face_min=None, face_max=None,
                                country=country, artist_listeners=None, personalized=None))
    assert op.verdict == verdict and op.suggested_qty == 0


def test_pipeline_adds_fixtures_and_football_analysis(tmp_path, now, monkeypatch):
    monkeypatch.delenv("KARTE_BEZ_RASPOREDA")
    http = FakeHttp({"https://fixturedownload.com/": load_fixture("fixturedownload_sample.json")})
    opts = ScanOptions(snapshot=True, segment="sport", use_fixtures=True, countries=["europa"], now=now)
    result = run_scan(opts, _settings(tmp_path), http=http)
    matches = [op for op in result.opportunities if op.event.source == fixtures.SOURCE]
    assert matches and all(op.verdict in FORBIDDEN for op in matches)
    analysis = football.analyze(result.opportunities)
    row = next(r for r in analysis["rows"] if r["match"] == "Hajduk Split – Nordsjælland")
    assert row["local"] and row["resale"] == "sluzbeno" and "UEFA" in row["official"]
    assert any("hajduk.mojekarte.hr" in s for s in row["how_to_buy"])
    assert analysis["rules"] and analysis["total"] >= 3


# ------------------------------------------------------------------ nogomet uz rizik (uvjeti kluba, ne zakon)
def _derby(make_event, **kw):
    base = dict(segment="sport", sport="football", name="Dinamo – Hajduk", artist="Dinamo – Hajduk", face_min=25, face_max=30,
                country="HR", artist_listeners=None, personalized=None, tags=["derby"], capacity=24000,
                secondary=SecondaryMarket(source="viagogo", lowest=140, currency="EUR"))
    base.update(kw)
    return make_event(**base)


def test_contract_risk_mode_prices_in_cancellation(make_event, now):
    strict = Evaluator(ModelConfig.load(), now=now)
    risky = Evaluator(ModelConfig.load(), now=now, contract_risk=True)
    assert strict.evaluate(_derby(make_event)).verdict == "UVJETI ZABRANJUJU"
    op = risky.evaluate(_derby(make_event))
    assert op.verdict == "RIZIČNO" and op.suggested_qty >= 2
    assert op.best.name != op.legal.official_channel  # računa se i viagogo, ne samo službena razmjena
    assert any("poništenja" in f for f in op.risk_flags)
    plain = Evaluator(ModelConfig.load(), now=now).cancel_risk(op.event)
    assert 0.3 <= plain <= 0.9  # na ime + HR
    # mala razlika u cijeni → rizik pojede zaradu
    assert risky.evaluate(_derby(make_event, secondary=SecondaryMarket(source="viagogo", lowest=40))).verdict == "UVJETI ZABRANJUJU"
    # zakonska zabrana (UK – kazneno djelo) se nikad ne računa uz rizik
    uk = risky.evaluate(_derby(make_event, country="GB", currency="GBP"))
    assert uk.verdict == "ZAKONSKI OGRANIČENO"


def test_risky_football_goes_only_to_its_own_package(make_event, now):
    ev = Evaluator(ModelConfig.load(), now=now, contract_risk=True, budget=2000)
    from karte.advisor import build_advice

    ops = []
    for op in (ev.evaluate(_derby(make_event, id="d1")), ev.evaluate(make_event(id="c1", face_min=40, face_max=60,
                                                                                    secondary=SecondaryMarket(source="viagogo", lowest=150)))):
        op.advice = build_advice(op, ev.cfg)
        ops.append(op)
    out = build_packages(ops, 2000, ev)
    risky = [p for p in out["packages"] if p["key"] == "rizik"]
    assert risky and all(it["verdict"] == "RIZIČNO" for it in risky[0]["items"]) and risky[0]["cost"] <= 400 + 1e-6
    assert all(it["verdict"] != "RIZIČNO" for p in out["packages"] if p["key"] != "rizik" for it in p["items"])
    assert any("VISOK RIZIK" in s for s in ops[0].advice["buy"])


# ------------------------------------------------------------------ tržište (viagogo/StubHub)
def test_market_events_from_snapshot(now):
    events = fixtures.market_events(now)
    derby = next(e for e in events if e.date.date().isoformat() == "2026-12-19")
    assert derby.secondary.source == "viagogo (spekulativno)" and derby.secondary.lowest == 54  # 23 dana prije utakmice and derby.secondary.listing_count == 3
    assert derby.face_min == 25 and derby.country == "HR" and "Vječni derbi" in football.match_info(*football.split_match(derby)).reason
    assert derby.date.hour == 0  # vrijeme još nije objavljeno


def test_apply_market_merges_with_fixture_and_user_rows_override(now, tmp_path, monkeypatch):
    monkeypatch.setenv("KARTE_DATA_DIR", str(tmp_path))
    (tmp_path / "snimka").mkdir()
    (tmp_path / "snimka" / fixtures.MARKET_FILE).write_text(
        "domacin,gost,datum,sek_najniza,sek_izvor,sek_valuta,sek_datum\n"
        "Hajduk Split,Nordsjælland,2026-12-10,40,StubHub,EUR,2026-11-26\n"
        "GNK Dinamo,Hajduk,2026-12-19,60,viagogo,EUR,2026-12-01\n", encoding="utf-8")
    market = fixtures.market_events(now)
    derby = next(e for e in market if e.date.date().isoformat() == "2026-12-19")
    assert derby.secondary.lowest == 60 and derby.face_min == 25  # moj redak dopunjuje ugrađeni
    fx = [e for e, _ in fixtures.parse_fixturedownload(load_fixture("fixturedownload_sample.json"), "conference-league", now, datetime(2027, 1, 17))]
    merged = fixtures.apply_market(fx, market)
    hajduk = next(e for e in merged if e.name == "Hajduk Split – Nordsjælland")
    assert hajduk.secondary.source == "StubHub" and hajduk.secondary.lowest == 40
    assert len([e for e in merged if "Nordsj" in e.name]) == 1  # spojeno, ne dupli događaj


def test_market_info_in_football_analysis_and_packages(tmp_path, now):
    result = run_scan(ScanOptions(snapshot=True, segment="all", now=now, countries=["otvoreno"]), _settings(tmp_path))
    analysis = football.analyze(result.opportunities)
    row = next(r for r in analysis["rows"] if r["date"].startswith("2026-12-19"))
    m = row["market"]
    assert row["verdict"] == "UVJETI ZABRANJUJU" and m["lowest"] == 54 and m["multiple"] == pytest.approx(1.8)
    assert m["speculative"] and "odbijen na ulazu" in m["why"]
    assert analysis["with_market"] >= 3
    out = build_packages(result.opportunities, 1000, result.evaluator)
    assert any(x["match"].startswith("GNK Dinamo Zagreb") for x in out["football"]["market"])
    assert all(it["segment"] != "sport" for p in out["packages"] for it in p["items"])  # zabranjeni nogomet nikad u paketu
    assert any("viagogu i StubHubu" in n for n in out["notes"])
    assert "NOGOMET NA PREPRODAJI" in "\n".join(describe(out))


# ------------------------------------------------------------------ paketi
def test_packages_from_demo_respect_budget_law_and_pairs(tmp_path, now):
    result = run_scan(ScanOptions(demo=True, segment="all", now=now, countries=["svijet"]), _settings(tmp_path))
    out = build_packages(result.opportunities, 1000, result.evaluator)
    assert out["packages"], out["notes"]
    keys = [p["key"] for p in out["packages"]]
    assert len(keys) == len(set(keys))
    for p in out["packages"]:
        assert p["cost"] <= 1000 + 1e-6 and p["items"]
        assert len(p["steps"]) == 5 and p["simulation"]["runs"] == 2000
        for it in p["items"]:
            assert it["qty"] >= 2 and it["qty"] % 2 == 0
            assert it["verdict"] not in FORBIDDEN  # nikad zabranjena preprodaja
            assert it["buy"] and it["sell"] and it["op"]["event"]["id"] == it["event_id"]
            if it["conditional"]:
                assert it["max_face"] and any("SAMO ako" in s for s in it["buy"])
    first = out["packages"][0]
    if first["key"] == "siguran":
        assert not first["conditional"] and first["cost"] <= 400 + 1e-6
    sport = next((p for p in out["packages"] if p["key"] == "sport"), None)
    if sport:
        assert all(it["segment"] == "sport" for it in sport["items"])
    text = "\n".join(describe(out))
    assert "PAKET 1" in text and "kupnja" in text and "prodaja" in text


def test_packages_without_candidates_explain_why(now):
    out = build_packages([], 500)
    assert out["packages"] == [] and "Trenutno nema" in out["notes"][0]


def test_conditional_items_from_snapshot(tmp_path, now):
    """Snimka stvarnih događaja: bez javne nominalne cijene paket sadrži UVJETNE stavke s granicom „kupi do”."""
    result = run_scan(ScanOptions(snapshot=True, segment="all", now=now, countries=["otvoreno"]), _settings(tmp_path))
    out = build_packages(result.opportunities, 1000, result.evaluator)
    items = [it for p in out["packages"] for it in p["items"]]
    assert any(it["conditional"] for it in items)
    assert all(it["unit_cost"] > 0 and it["net"] > it["unit_cost"] for it in items)


def test_service_app_and_cli(tmp_path, now, capsys):
    s = _settings(tmp_path)
    res = packages(ScanOptions(demo=True, segment="all", countries=["svijet"], budget=800), s)
    assert res["is_demo"] and res["packages"] and res["sources"]
    app = App(s)
    gui = app.packages({"source": "demo", "countries": "svijet", "budget": 800})
    assert gui["packages"] and gui["budget"] == 800
    fb = app.football({"source": "demo"})
    assert fb["rows"] and all(r["resale"] in ("zabranjeno", "sluzbeno", "sluzbeno_trziste", "dopusteno", "rizicno") for r in fb["rows"])
    assert football_matches(ScanOptions(demo=True, countries=["svijet"]), s)["total"] == fb["total"]
    env = str(tmp_path / "nema.env")
    assert main(["--env", env, "paketi", "--demo", "--countries", "svijet", "--budget", "600"]) == 0
    assert "PAKET 1" in capsys.readouterr().out
    assert main(["--env", env, "nogomet", "--demo", "--detalji"]) == 0
    assert "Smije li" not in capsys.readouterr().err
