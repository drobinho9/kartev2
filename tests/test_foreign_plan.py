"""Strani prodavači, poveznice za provjeru cijena i plan zarade."""

import dataclasses
from datetime import datetime

import pytest

from karte import knowledge
from karte.cli import main
from karte.knowledge import ModelConfig
from karte.links import price_links
from karte.models import SecondaryMarket
from karte.pipeline import ScanOptions, run_scan
from karte.platforms import available_platforms
from karte.portfolio import Position, build_plan, simulate
from karte.scoring import Evaluator
from karte.settings import Settings

NOW = datetime(2026, 11, 22, 10, 0)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("KARTE_DATA_DIR", str(tmp_path / "data"))
    for key in ("TICKETMASTER_API_KEY", "SEATGEEK_CLIENT_ID", "SERPAPI_KEY", "PREDICTHQ_TOKEN", "LASTFM_API_KEY"):
        monkeypatch.delenv(key, raising=False)


def _settings(tmp_path) -> Settings:
    return Settings(ticketmaster_api_key=None, seatgeek_client_id=None, lastfm_api_key=None, countries=["otvoreno"],
                    budget=1000.0, cache_dir=tmp_path / "cache")


def test_vendor_catalogue_and_detection():
    hu = [k for k, _ in knowledge.vendors_for_country("HU")]
    assert {"jegy_hu", "livenation"} <= set(hu)
    assert knowledge.vendor_domain("ticketmaster", "GB") == "ticketmaster.co.uk"
    assert knowledge.vendor_domain("eventim", "AT") == "oeticket.com"
    for text, key in [("Eventim.hr", "eventim"), ("www.ticketmaster.co.uk", "ticketmaster"), ("See Tickets", "see_tickets"),
                      ("jegy.hu", "jegy_hu"), ("DICE", "dice"), ("Arena Zagreb", None), ("Ongoing", None)]:
        assert knowledge.vendor_key_for(text) == key
    cfg = ModelConfig.load()
    assert cfg.primary_fee("see_tickets") == (0.14, 2.9)  # iz vendors.toml
    assert cfg.primary_fee("eventim") == (0.10, 1.5)  # model.toml ima prednost
    assert cfg.primary_fee("nepoznat") == (0.10, 1.0)


def test_price_links_cover_foreign_sites(make_event):
    e = make_event(artist="Bryan Adams", venue="MVM Dome", city="Budapest", country="HU", primary_vendor="livenation", url="https://x.hu")
    links = price_links(e)
    groups = {l["group"] for l in links}
    assert {"Događaj", "Službena prodaja", "Preprodaja", "Usporedba cijena", "Oglasnik"} <= groups
    text = " ".join(l["url"] for l in links)
    assert "livenation.hu" in text and "jegy.hu" in text and "viagogo.com" in text and "jofogas.hu" in text
    assert all(l["url"].startswith("https://") for l in links)
    italy = price_links(make_event(country="IT", city="Milano", venue="Unipol Forum"), allow_profit=False)
    resale = [l["label"] for l in italy if l["group"] == "Preprodaja"]
    assert "viagogo" not in resale and "TicketSwap" in resale  # u Italiji samo kanali s limitom cijene


def test_ticketswap_caps_by_country_and_fansale_uk():
    ts_be = next(p for p in available_platforms("BE", None) if p.key == "ticketswap")
    ts_nl = next(p for p in available_platforms("NL", None) if p.key == "ticketswap")
    assert ts_be.cap == "face" and ts_nl.cap == "percent"
    fan_gb = next(p for p in available_platforms("GB", "eventim") if p.key == "fansale")
    assert fan_gb.cap == "percent" and fan_gb.cap_pct == 0.10
    assert any(p.key == "gigsberg" for p in available_platforms("HR", None))


def test_locked_vendor_is_treated_as_non_transferable(make_event):
    ev = Evaluator(ModelConfig.load(), now=NOW)
    op = ev.evaluate(make_event(primary_vendor="dice", personalized=None, country="GB", city="London", venue="O2 Academy Brixton"))
    assert op.event.personalized is True
    assert any("DICE" in f for f in op.risk_flags)
    from karte.advisor import build_advice
    advice = build_advice(op, ev.cfg)
    assert any(c["level"] == "bad" and "DICE" in c["text"] for c in advice["safety"])
    assert any("Službena prodaja: DICE" in b for b in advice["buy"])


def test_plan_allocates_budget_and_simulates(tmp_path):
    result = run_scan(ScanOptions(snapshot=True, countries=["otvoreno"], now=NOW, budget=1000), _settings(tmp_path))
    plan = build_plan(result.opportunities, 1000, result.evaluator, simulations=2000)
    assert plan.positions and plan.invested <= 1000
    assert all(p.cost <= 1000 * 0.25 + 1e-6 for p in plan.positions)
    assert all(p.qty % 2 == 0 for p in plan.positions)
    assert plan.conditional and all(p.conditional and p.assumed_face for p in plan.conditional)
    sim = plan.simulation
    assert 0 <= sim["prob_loss"] <= 1 and sim["p05"] <= sim["p50"] <= sim["p95"]
    assert sim["mean"] == pytest.approx(plan.expected_profit, abs=max(15, abs(plan.expected_profit) * 0.25))
    assert abs(sum(b["share"] for b in sim["histogram"]) - 1) < 1e-6
    dated = [c["date"] for c in plan.calendar if c["date"]]
    assert dated == sorted(dated)
    d = plan.as_dict()
    assert d["positions"][0]["artist"] and d["notes"]


def test_simulate_is_deterministic_and_respects_probabilities(make_event):
    ev = Evaluator(ModelConfig.load(), now=NOW)
    op = ev.evaluate(make_event(secondary=SecondaryMarket(source="viagogo", lowest=150)))
    pos = Position(op=op, qty=2, unit_cost=50, net=100, salvage=0, p_sell=1.0, platform="x")
    sure = simulate([pos], runs=500, seed=1, price_sigma=0.0)
    assert sure["prob_loss"] == 0 and sure["mean"] == pytest.approx(100)
    never = simulate([dataclasses.replace(pos, p_sell=0.0)], runs=500, seed=1)
    assert never["prob_loss"] == 1 and never["mean"] == pytest.approx(-100)
    assert simulate([pos], runs=300, seed=7) == simulate([pos], runs=300, seed=7)
    assert simulate([], runs=100) == {}


def test_cli_plan_and_gui_plan(tmp_path, capsys):
    assert main(["--env", str(tmp_path / "nema.env"), "plan", "--countries", "HR", "--budget", "800", "--calendar", "5"]) == 0
    out = capsys.readouterr().out
    assert "PLAN ZARADE" in out and "budžet 800 €" in out
    from karte.gui.server import App, vendor_options

    app = App(_settings(tmp_path), journal_path=tmp_path / "d.json")
    plan = app.plan({"source": "snapshot", "countries": "HR", "budget": 800})
    assert plan["is_snapshot"] and "simulation" in plan and plan["budget"] == 800
    options = vendor_options()
    assert list(options)[-1] == "" and "jegy_hu" in options and "eventim" in options
