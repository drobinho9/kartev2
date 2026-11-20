"""Sport i nogomet: prepoznavanje, posebna pravila, službeni kanali, sučelje."""

from datetime import datetime

import pytest
from conftest import FakeHttp, load_fixture

from karte import sport
from karte.knowledge import ModelConfig
from karte.models import SecondaryMarket
from karte.pipeline import ScanOptions, run_scan
from karte.providers import ticketmaster
from karte.providers.manual import load_csv_text
from karte.scoring import Evaluator
from karte.service import build_event, market_rows
from karte.settings import Settings


@pytest.fixture
def ev(now):
    return Evaluator(ModelConfig.load(), budget=2000, now=now)


def football(make_event, **kw):
    base = dict(segment="sport", sport="football", artist="Demo FC", name="Demo FC – Example SC", artist_listeners=None,
                personalized=None, capacity=30000, face_min=40, face_max=90, tags=["derby"],
                secondary=SecondaryMarket(source="ručno (viagogo)", lowest=160))
    base.update(kw)
    return make_event(**base)


def test_detect_sport_from_genres():
    assert sport.detect_sport("Soccer", "DE") == "football"
    assert sport.detect_sport("Football", "GB") == "football"
    assert sport.detect_sport("Football", "US") == "american_football"
    assert sport.detect_sport("Basketball", "US") == "basketball"
    assert sport.detect_sport("Ice Hockey", "CA") == "hockey"
    assert sport.detect_sport("Motorsports/Racing", "AT") == "motorsport"
    assert sport.detect_sport("", "HR") == "other"


def test_uk_football_is_criminal(ev, make_event):
    op = ev.evaluate(football(make_event, country="GB", currency="GBP"))
    assert op.verdict == "ZAKONSKI OGRANIČENO"
    assert op.legal.sport_rule == "criminal" and op.suggested_qty == 0
    assert op.best.name.startswith("službena Ticket Exchange")
    from karte.advisor import build_advice

    safety = build_advice(op, ev.cfg)["safety"]
    assert any(c["level"] == "bad" and "kazneno" in c["text"] for c in safety)


def test_croatian_football_club_terms_and_official_channel(ev, make_event):
    from karte.advisor import build_advice

    op = ev.evaluate(football(make_event, country="HR"))
    assert op.verdict == "UVJETI ZABRANJUJU" and op.legal.contract_prohibited
    assert op.event.personalized is True  # pretpostavka za europski nogomet
    assert [o.name for o in op.platforms] == [op.legal.official_channel]
    assert all(o.list_price <= op.face_ref + 1e-9 for o in op.platforms)  # službeni kanal po nominalnoj
    advice = build_advice(op, ev.cfg)
    assert advice["ladder"] == []
    assert any("Dinamo" in x for x in advice["buy"])
    assert any("nije dopuštena" in x for x in advice["sell"])
    assert advice["safety"][0]["level"] == "bad"


def test_uefa_competition_overrides_open_country(ev, make_event):
    op = ev.evaluate(football(make_event, country="AT", name="UEFA Champions League: Demo FC – Example SC"))
    assert op.legal.sport_rule == "official_only" and op.verdict == "UVJETI ZABRANJUJU"
    assert "UEFA" in op.legal.official_channel


def test_uefa_in_uk_takes_stricter_criminal_rule(ev, make_event):
    op = ev.evaluate(football(make_event, country="GB", name="UEFA Europa League: Demo FC – Example SC"))
    assert op.legal.sport_rule == "criminal"


def test_us_sports_are_evaluated_normally(ev, make_event):
    nfl = make_event(segment="sport", sport="american_football", league="NFL", country="US", region="IL", currency="USD",
                     face_min=120, face_max=380, artist_listeners=None, primary_vendor="ticketmaster", personalized=False,
                     tags=["rivalry"], secondary=SecondaryMarket(source="seatgeek", lowest=300, currency="USD"))
    op = ev.evaluate(nfl)
    assert op.legal.sport_rule is None and op.verdict in ("KUPI", "RAZMOTRI")
    assert any(o.key == "ticketmaster_resale" for o in op.platforms)


def test_nfl_game_in_germany_is_official_only(ev, make_event):
    op = ev.evaluate(make_event(segment="sport", sport="american_football", league="NFL", country="DE",
                                name="NFL Munich Game", artist_listeners=None, primary_vendor="ticketmaster"))
    assert op.legal.sport_rule == "official_only" and op.verdict == "UVJETI ZABRANJUJU"
    assert "Ticketmaster Resale" in op.legal.official_channel


def test_fifa_uses_official_marketplace_with_fees(ev, make_event):
    op = ev.evaluate(football(make_event, country="US", region="NJ", currency="USD", name="FIFA World Cup – finale",
                              personalized=False, tags=["final"], secondary=SecondaryMarket(source="FIFA", lowest=900, currency="USD"),
                              face_min=250, face_max=250))
    assert op.legal.sport_rule == "official_marketplace"
    assert [o.name for o in op.platforms] == ["FIFA Resale/Exchange Marketplace"]
    assert op.platforms[0].fee_pct == pytest.approx(0.15)
    assert op.verdict in ("KUPI", "RAZMOTRI")


def test_concerts_unaffected_by_sport_rules(ev, make_event):
    op = ev.evaluate(make_event(country="GB", currency="GBP", artist_listeners=3_000_000))
    assert op.legal.sport_rule is None and op.verdict != "UVJETI ZABRANJUJU"


def test_ticketmaster_parses_sport_classification():
    raw = load_fixture("ticketmaster_events.json")["_embedded"]["events"][0]
    raw = {**raw, "classifications": [{"segment": {"name": "Sports"}, "genre": {"name": "Soccer"}, "subGenre": {"name": "Bundesliga"}}]}
    e = ticketmaster.parse_event(raw)
    assert e.segment == "sport" and e.sport == "football" and e.league == "Bundesliga"
    music = ticketmaster.parse_event(load_fixture("ticketmaster_events.json")["_embedded"]["events"][0])
    assert music.segment == "music" and music.sport is None


def test_pipeline_requests_sports_classification(tmp_path, now):
    http = FakeHttp({ticketmaster.BASE_URL: load_fixture("ticketmaster_events.json")})
    s = Settings(ticketmaster_api_key="K", seatgeek_client_id=None, lastfm_api_key=None, countries=["DE"], budget=1000.0, cache_dir=tmp_path)
    run_scan(ScanOptions(countries=["DE"], now=now, use_lastfm=False, onsale_days=0, segment="sport"), s, http=http)
    assert {c[1]["classificationName"] for c in http.calls} == {"sports"}
    http.calls.clear()
    run_scan(ScanOptions(countries=["DE"], now=now, use_lastfm=False, onsale_days=0, segment="all"), s, http=http)
    assert {c[1]["classificationName"] for c in http.calls} == {"music", "sports"}


def test_demo_segments(tmp_path, now):
    s = Settings(None, None, None, ["otvoreno"], 1000.0, tmp_path)
    music = run_scan(ScanOptions(demo=True, now=now), s)
    sports = run_scan(ScanOptions(demo=True, now=now, segment="sport"), s)
    assert all(o.event.segment == "music" for o in music.opportunities)
    verdicts = {o.verdict for o in sports.opportunities}
    assert {"ZAKONSKI OGRANIČENO", "UVJETI ZABRANJUJU"} <= verdicts and ("KUPI" in verdicts or "RAZMOTRI" in verdicts)


def test_csv_and_form_sport_fields():
    text = "izvodjac,naziv,drzava,datum,cijena_min,vrsta,sport,natjecanje\nDinamo,Dinamo – Hajduk,HR,2027-03-01,20,sport,nogomet,SuperSport HNL\n"
    e = load_csv_text(text)[0]
    assert e.segment == "sport" and e.sport == "football" and e.league == "SuperSport HNL"
    f = build_event({"artist": "X", "segment": "sport", "sport": "basketball", "league": "NBA"})
    assert f.segment == "sport" and f.sport == "basketball" and f.league == "NBA"


def test_markets_rows_include_football_rule_and_overview():
    rows = {r["code"]: r for r in market_rows(["GB", "US", "HR"])}
    assert rows["GB"]["football_rule"] == "criminal"
    assert rows["US"]["football_rule"] == "none"
    assert rows["HR"]["football_rule"] == "club_terms"
    overview = sport.rules_overview()
    assert any(r["code"] == "uefa" for r in overview) and any(r["code"] == "HR" for r in overview)
