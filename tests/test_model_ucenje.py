"""Kada prodati (NeedATicket krivulje) i naš model koji uči iz prikupljenih cijena."""

import json
import math
import random

import pytest

from karte import timing, ucenje
from karte.advisor import build_advice
from karte.knowledge import ModelConfig
from karte.models import SecondaryMarket
from karte.radar import load_state, scan_alerts
from karte.scoring import Evaluator


def test_timing_curve_from_real_data(make_event):
    big = make_event(capacity=60000)
    small = make_event(capacity=800)
    assert timing.segment_key(big) == ("ALL", "large") and timing.segment_key(small) == ("ALL", "small")
    assert timing.rel(big, 30) == pytest.approx(1.199) and timing.rel(big, 0) == 1.0
    assert timing.rel(big, 14) > timing.rel(big, 7) >= timing.rel(big, 3)
    assert 1.05 < timing.rel(big, 20) < 1.14  # interpolacija između 14 i 21 dan
    assert timing.rel(small, 30) == pytest.approx(1.0)
    assert "prodaj rano" in timing.insight(big)


def test_ladder_follows_curve_and_only_drops(make_event, now):
    ev = Evaluator(ModelConfig.load(), now=now)
    op = ev.evaluate(make_event(capacity=60000, artist_listeners=4_500_000, tags=["farewell"]))
    advice = build_advice(op, ev.cfg)
    prices = [r["price"] for r in advice["ladder"]]
    assert prices == sorted(prices, reverse=True) and len(prices) >= 4
    assert any("NeedATicket" in s for s in advice["sell"])


def test_observation_and_features(make_event, now):
    ev = Evaluator(ModelConfig.load(), now=now)
    op = ev.evaluate(make_event(tags=["first_visit"], secondary=SecondaryMarket(source="viagogo", lowest=150)))
    obs = ucenje.observation(op)
    assert obs and obs["znacajke"]["first_visit"] == 1.0 and obs["y"] == pytest.approx(math.log(150 / 50), rel=1e-3)
    spec = ev.evaluate(make_event(secondary=SecondaryMarket(source="viagogo (spekulativno)", lowest=150)))
    assert ucenje.observation(spec) is None  # spekulativni oglasi nisu primjer za učenje


def test_ridge_recovers_signal_and_beats_flat_heuristic():
    rng = random.Random(1)
    rows = []
    for _ in range(80):
        f = {k: rng.random() for k in ucenje.FEATURES}
        y = 0.2 + 1.2 * f["popularity"] + 0.6 * f["first_visit"] + rng.gauss(0, 0.05)
        rows.append({"znacajke": f, "y": y, "heuristika": 0.7})
    model = ucenje.fit(rows)
    assert model["coef"]["popularity"] == pytest.approx(1.2, abs=0.25)
    assert abs(model["coef"]["tour"]) < 0.25
    cv = ucenje.cross_validate(rows)
    assert cv["mae_model"] < cv["mae_heuristika"]


def test_train_activates_and_blends(tmp_path, make_event, now):
    ev = Evaluator(ModelConfig.load(), now=now)
    rng = random.Random(2)
    ops = []
    for i in range(30):
        listeners = int(10 ** rng.uniform(4.5, 6.8))
        resale = 50 * (1.0 + listeners / 2_000_000)
        ops.append(ev.evaluate(make_event(id=f"e{i}", artist=f"Izvođač {i}", artist_listeners=listeners,
                                          secondary=SecondaryMarket(source="viagogo", lowest=resale))))
    report = ucenje.train(tmp_path, ops)
    assert report["primjera"] == 30 and "mae_model" in report
    saved = json.loads((tmp_path / ucenje.MODEL_FILE).read_text(encoding="utf-8"))
    assert saved["primjera"] == 30
    model = {**saved, "aktivan": True}
    blended = Evaluator(ModelConfig.load(), now=now, learned=model).evaluate(make_event(artist_listeners=3_000_000))
    assert "naučen na 30" in blended.multiplier_source


def test_radar_history_records_features_for_training(tmp_path, make_event, now):
    ev = Evaluator(ModelConfig.load(), now=now)
    op = ev.evaluate(make_event(tags=["first_visit"], secondary=SecondaryMarket(source="viagogo", lowest=150)))
    state = load_state(tmp_path)
    scan_alerts([op], state, now)
    (tmp_path / "radar_stanje.json").write_text(json.dumps(state, default=str), encoding="utf-8")
    rows = ucenje.dataset(tmp_path)
    assert len(rows) == 1 and rows[0]["znacajke"]["first_visit"] == 1.0
