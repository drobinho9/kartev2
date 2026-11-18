"""Globalno skeniranje: regije, savezne države, prebivalište prodavatelja, pristup tržištu, Ticketmaster dijeljenje prozora."""

from datetime import datetime

import pytest

from karte import legal
from karte.knowledge import ModelConfig, estimate_capacity, expand_countries, market_info, venue_capacity
from karte.platforms import available_platforms, blocked_for_seller
from karte.providers import ticketmaster
from karte.scoring import Evaluator
from karte.util import parse_datetime


def test_expand_countries_regions_and_codes():
    assert expand_countries("dach") == ["DE", "AT", "CH"]
    assert expand_countries(["sjeverna_amerika", "GB", "us"]) == ["US", "CA", "MX", "GB"]
    assert expand_countries("svijet") == ["ALL"]
    assert expand_countries("HR,svijet") == ["ALL"]
    assert "US" in expand_countries("otvoreno") and "IE" not in expand_countries("otvoreno")


def test_venue_capacity_world_and_keyword_estimate():
    assert venue_capacity("Madison Square Garden") == 19500
    assert venue_capacity("Hamsgate Pavilion") is None  # nema lažnog podudaranja s aliasom "msg"
    assert estimate_capacity("Wembley Stadium") == 40000
    assert estimate_capacity("Red Rocks Amphitheatre") == 8000
    assert estimate_capacity("Club Gugalnica") == 600
    assert estimate_capacity("Nešto Bez Ključne Riječi") is None


def test_us_and_canada_subdivision_laws():
    vt = legal.evaluate("US", 100, 110, region="VT")
    assert vt.country == "US-VT" and vt.cap_price == pytest.approx(110)
    assert "Vermont" in vt.summary and "SAD" in vt.summary
    ny = legal.evaluate("US", 100, 110, region="NY")
    assert ny.cap_price is None
    other_state = legal.evaluate("US", 100, 110, region="TX")
    assert other_state.country == "US" and other_state.cap_price is None
    on = legal.evaluate("CA", 100, 112, region="ON")
    assert on.profit_prohibited and on.cap_price == 112  # nominalna + naknade
    dc = legal.evaluate("US", 100, 110, region="DC", strict=True)
    assert dc.cap_price == pytest.approx(110)


def test_asia_and_brazil_prohibited():
    for code in ("JP", "KR", "BR", "NO"):
        assert legal.evaluate(code, 50, 55).profit_prohibited, code
    assert legal.evaluate("AU", 100, 110).cap_price == pytest.approx(110)
    assert legal.evaluate("SE", 100, 110).cap_price is None


def test_seller_residency_and_country_overrides():
    from_hr = {p.key: p for p in available_platforms("US", "ticketmaster", "HR")}
    assert "vivid_seats" not in from_hr and "seatgeek_market" not in from_hr
    assert from_hr["ticketmaster_resale"].cap == "none"  # u SAD-u slobodna cijena
    assert from_hr["viagogo"].reach == pytest.approx(0.7)
    from_us = {p.key for p in available_platforms("US", "ticketmaster", "US")}
    assert {"vivid_seats", "seatgeek_market"} <= from_us
    assert {p.key for p in blocked_for_seller("US", "ticketmaster", "HR")} >= {"vivid_seats", "seatgeek_market"}
    eu_tm = {p.key: p for p in available_platforms("AT", "ticketmaster", "HR")}
    assert eu_tm["ticketmaster_resale"].cap == "face"


def test_local_channels_weaker_abroad():
    home = {p.key: p for p in available_platforms("HR", None, "HR")}["lokalni_oglasnik"]
    abroad = {p.key: p for p in available_platforms("US", None, "HR")}["lokalni_oglasnik"]
    assert abroad.reach < home.reach and abroad.trust_risk > home.trust_risk


def test_access_risk_for_foreign_events(make_event, now):
    ev = Evaluator(ModelConfig.load(), now=now, seller_country="HR")
    home = ev.evaluate(make_event(country="HR"))
    us = ev.evaluate(make_event(country="US", region="NY", currency="EUR", primary_vendor="ticketmaster"))
    assert us.risk > home.risk
    assert any("inozemstva (US)" in f for f in us.risk_flags)
    assert any("Vivid Seats" in f for f in us.risk_flags)
    local = Evaluator(ModelConfig.load(), now=now, seller_country="US").evaluate(
        make_event(country="US", region="NY", primary_vendor="ticketmaster")
    )
    assert not any("inozemstva" in f for f in local.risk_flags)
    assert market_info("US")["size"] == 1.0


def test_vermont_event_is_capped(make_event, now):
    ev = Evaluator(ModelConfig.load(), now=now)
    op = ev.evaluate(make_event(country="US", region="VT", artist_listeners=4_500_000, tags=["farewell"], primary_vendor="ticketmaster"))
    assert all(o.list_price <= op.face_ref * 1.1 + 1e-6 for o in op.platforms)
    assert op.verdict != "KUPI"


class WindowHttp:
    """Lažni Ticketmaster: >1000 rezultata za prozore dulje od 4 dana, inače 3 događaja s jedinstvenim ID-jem."""

    def __init__(self):
        self.calls = []

    def get_json(self, url, params=None, cache_ttl=None):
        self.calls.append(dict(params))
        start = parse_datetime(params.get("startDateTime") or params.get("onsaleStartDateTime"))
        end = parse_datetime(params.get("endDateTime") if "startDateTime" in params else params.get("onsaleEndDateTime"))
        days = (end - start).total_seconds() / 86400
        if days > 4:
            return {"_embedded": {"events": []}, "page": {"totalElements": 5000, "totalPages": 25}}
        events = [
            {
                "id": f"{start.isoformat()}-{i}",
                "name": f"Artist {i}",
                "dates": {"start": {"dateTime": start.strftime("%Y-%m-%dT%H:%M:%SZ")}, "status": {"code": "onsale"}},
                "priceRanges": [{"min": 50, "max": 90, "currency": "USD"}],
                "_embedded": {"venues": [{"name": "Arena", "city": {"name": "X"}, "country": {"countryCode": "US"}, "state": {"stateCode": "NY"}}]},
            }
            for i in range(3)
        ]
        return {"_embedded": {"events": events}, "page": {"totalElements": 3, "totalPages": 1}}


def test_ticketmaster_splits_large_windows_and_world_has_no_country():
    http = WindowHttp()
    tm = ticketmaster.TicketmasterProvider("K", http)
    events = tm.events_between(["ALL"], datetime(2026, 11, 18), datetime(2026, 12, 18))
    assert "countryCode" not in http.calls[0]
    # 30 dana → dijeljenje dok prozor nije ≤ 4 dana: 8 listova × 3 događaja
    assert len(events) == 24
    assert all(e.region == "NY" and e.country == "US" for e in events)
    assert not tm.truncated


def test_ticketmaster_call_budget_marks_truncated():
    http = WindowHttp()
    tm = ticketmaster.TicketmasterProvider("K", http, max_calls=3)
    tm.events_between(["US"], datetime(2026, 11, 18), datetime(2027, 1, 18))
    assert tm.truncated and tm.calls <= 4
