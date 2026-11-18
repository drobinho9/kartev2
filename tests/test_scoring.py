import pytest

from karte.advisor import build_advice
from karte.knowledge import ModelConfig
from karte.models import Presale, SecondaryMarket
from karte.scoring import Evaluator, sort_key


@pytest.fixture
def evaluator(now):
    return Evaluator(ModelConfig.load(), budget=1000, now=now)


def test_more_listeners_means_more_demand(evaluator, make_event):
    small = evaluator.evaluate(make_event(artist_listeners=100_000))
    big = evaluator.evaluate(make_event(artist_listeners=4_000_000))
    assert big.demand.score > small.demand.score
    assert big.expected_resale > small.expected_resale


def test_more_shows_means_less_scarcity(evaluator, make_event):
    one = evaluator.evaluate(make_event(shows_in_region=1))
    three = evaluator.evaluate(make_event(shows_in_region=3))
    assert one.demand.components["scarcity"] > three.demand.components["scarcity"]


def test_buzz_tags_raise_demand(evaluator, make_event):
    plain = evaluator.evaluate(make_event())
    farewell = evaluator.evaluate(make_event(tags=["farewell"]))
    assert farewell.demand.score > plain.demand.score


def test_superstar_single_date_is_buy(evaluator, make_event):
    op = evaluator.evaluate(make_event(artist_listeners=4_500_000, tags=["first_visit"], artist_upcoming_events=30, face_min=60))
    assert op.verdict == "KUPI"
    assert op.suggested_qty >= 2 and op.suggested_qty % 2 == 0
    assert op.best is not None and op.profit > 0


def test_niche_artist_is_skip(evaluator, make_event):
    op = evaluator.evaluate(make_event(artist_listeners=30_000, capacity=1800))
    assert op.verdict == "PRESKOČI"
    assert op.suggested_qty == 0


def test_buy_cost_includes_primary_fees(evaluator, make_event):
    op = evaluator.evaluate(make_event(face_min=50, primary_vendor="ticketmaster"))
    assert op.buy_cost == pytest.approx(56.0)


def test_secondary_market_data_drives_multiplier(evaluator, make_event):
    sec = SecondaryMarket(source="ručno (viagogo)", lowest=150, currency="EUR")
    op = evaluator.evaluate(make_event(face_min=50, secondary=sec))
    # 150 × (1 − 0.20 kupčeve naknade) × 0.95 haircut = 114 → ×2.28
    assert op.multiplier == pytest.approx(2.28)
    assert "sekundarno" in op.multiplier_source
    assert op.demand.confidence == pytest.approx(1.0)


def test_local_listing_source_is_not_reduced_by_buyer_fees(evaluator, make_event):
    sec = SecondaryMarket(source="Njuškalo", lowest=100, currency="EUR")
    op = evaluator.evaluate(make_event(face_min=50, secondary=sec))
    assert op.multiplier == pytest.approx(1.9)


def test_personalized_tickets_raise_risk_and_lower_value(evaluator, make_event):
    normal = evaluator.evaluate(make_event(artist_listeners=3_000_000))
    named = evaluator.evaluate(make_event(artist_listeners=3_000_000, personalized=True))
    assert named.risk > normal.risk
    assert named.expected_value < normal.expected_value
    assert any("Personalizirane" in f for f in named.risk_flags)


def test_face_value_cap_country_is_legally_restricted(evaluator, make_event):
    op = evaluator.evaluate(make_event(country="IE", artist_listeners=4_000_000, primary_vendor="ticketmaster"))
    assert op.verdict == "ZAKONSKI OGRANIČENO"
    assert all(o.list_price <= op.face_ref + 1e-9 for o in op.platforms)


def test_soldout_and_cancelled_and_missing_price(evaluator, make_event):
    assert evaluator.evaluate(make_event(status="soldout")).verdict == "RASPRODANO"
    assert evaluator.evaluate(make_event(status="cancelled")).verdict == "OTKAZANO"
    assert evaluator.evaluate(make_event(face_min=None, face_max=None)).verdict == "NEMA CIJENE"


def test_announced_phase_and_days_to_onsale(evaluator, make_event, now):
    from datetime import timedelta

    ev = make_event(public_onsale=now + timedelta(days=5), presales=[Presale("Fan presale", now + timedelta(days=3))])
    op = evaluator.evaluate(ev)
    assert op.phase == "NAJAVA"
    assert op.days_to_onsale == 3


def test_quantity_respects_budget_and_ticket_limit(now, make_event):
    ev = make_event(artist_listeners=4_500_000, tags=["farewell"], face_min=60, ticket_limit=2)
    rich = Evaluator(ModelConfig.load(), budget=10_000, now=now).evaluate(ev)
    assert rich.suggested_qty == 2  # limit po kupcu
    poor = Evaluator(ModelConfig.load(), budget=100, now=now).evaluate(make_event(artist_listeners=4_500_000, tags=["farewell"], face_min=60))
    assert poor.suggested_qty == 0  # 25 % od 100 € ne pokriva ni jednu ulaznicu


def test_strict_mode_applies_planned_german_cap(now, make_event):
    ev = make_event(country="DE", artist_listeners=4_500_000, tags=["farewell"], face_min=80, primary_vendor="ticketmaster")
    loose = Evaluator(ModelConfig.load(), now=now).evaluate(ev)
    strict = Evaluator(ModelConfig.load(), now=now, strict=True).evaluate(ev)
    assert strict.expected_value < loose.expected_value
    assert strict.legal.cap_price is not None
    assert any("--strict" in f for f in loose.risk_flags)


def test_sort_key_puts_buys_first(evaluator, make_event):
    ops = [
        evaluator.evaluate(make_event(artist_listeners=20_000)),
        evaluator.evaluate(make_event(artist_listeners=4_500_000, tags=["farewell"])),
    ]
    ops.sort(key=sort_key)
    assert ops[0].verdict == "KUPI"


def test_advice_contains_actionable_sections(evaluator, make_event):
    op = evaluator.evaluate(make_event(artist_listeners=4_500_000, tags=["farewell"]))
    advice = build_advice(op, evaluator.cfg)
    assert advice["buy"] and advice["sell"] and advice["ladder"]
    assert any("botov" in x.lower() for x in advice["buy"])
    prices = [row["price"] for row in advice["ladder"]]
    assert prices == sorted(prices, reverse=True)  # cijena se samo spušta
    assert advice["ladder"][-1]["price"] >= op.best.break_even_price - 0.01 or op.demand.score < 0.7


def test_invalid_category_rejected(now):
    with pytest.raises(ValueError):
        Evaluator(category="vip", now=now)


def test_safety_checks_flag_dangerous_situations(evaluator, make_event):
    from karte.advisor import safety_checks

    bad = evaluator.evaluate(make_event(country="IE", personalized=True, ticket_limit=None, primary_vendor="ticketmaster"))
    levels = [c["level"] for c in safety_checks(bad)]
    assert levels.count("bad") >= 2
    good = evaluator.evaluate(make_event(personalized=False, ticket_limit=4))
    checks = safety_checks(good)
    assert not any(c["level"] == "bad" for c in checks)
    assert any("povuci oglase" in c["text"] for c in checks)
    assert "safety" in build_advice(good, evaluator.cfg)
