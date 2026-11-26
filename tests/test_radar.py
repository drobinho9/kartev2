"""Radar: hype score, obavijesti samo za novo/promijenjeno, Telegram poruke."""

from datetime import datetime, timedelta

import pytest

from karte.announcements import Announcement
from karte.cli import main
from karte.knowledge import ModelConfig
from karte.models import Presale, SecondaryMarket
from karte.notify import ProviderError, split_messages, telegram_send
from karte.pipeline import ScanOptions
from karte.radar import announcement_alerts, hype, hype_announcement, load_state, run_radar, scan_alerts, telegram_blocks
from karte.scoring import Evaluator
from karte.settings import Settings


@pytest.fixture
def ev(now):
    return Evaluator(ModelConfig.load(), now=now)


def test_hype_explains_and_ranks(ev, make_event):
    hot = ev.evaluate(make_event(id="hot", tags=["first_visit"], artist_listeners=3_000_000, artist_trend=2.2,
                                 secondary=SecondaryMarket(source="viagogo", lowest=160)))
    cold = ev.evaluate(make_event(id="cold", artist_listeners=20_000, face_min=80, face_max=90, artist_upcoming_events=120))
    s_hot, why_hot = hype(hot)
    s_cold, _ = hype(cold)
    assert s_hot > s_cold and s_hot >= 70
    assert any("prvi put" in r for r in why_hot) and any("Wikipediji" in r for r in why_hot)
    banned = ev.evaluate(make_event(segment="sport", sport="football", country="GB", currency="GBP", name="A – B", artist="A – B"))
    assert hype(banned)[0] == 0


def test_scan_alerts_only_new_or_changed(ev, make_event, now):
    ops = [ev.evaluate(make_event(id=f"e{i}", artist=f"Izvođač {i}", tags=["first_visit"], artist_listeners=3_000_000,
                                  secondary=SecondaryMarket(source="viagogo", lowest=170))) for i in range(8)]
    state = load_state(__import__("pathlib").Path("nema-mape"))
    first = scan_alerts(ops, state, now, threshold=60)
    assert 0 < len(first) <= 5 and all(a.kind == "NOVO" for a in first)  # prvo pokretanje: najviše 5
    assert scan_alerts(ops, state, now, threshold=60) == []  # ništa novo
    jump = ev.evaluate(make_event(id="e0", artist="Izvođač 0", tags=["first_visit"], artist_listeners=3_000_000,
                                  secondary=SecondaryMarket(source="viagogo", lowest=260)))
    alerts = scan_alerts([jump], state, now, threshold=60)
    assert any(a.kind == "CIJENA" for a in alerts)
    key = next(iter(state["dogadaji"]))
    assert state["dogadaji"][key]["povijest"][0]["ocjena"] > 0  # povijest za kalibraciju


def test_presale_reminder_once(ev, make_event, now):
    soon = now + timedelta(hours=20)
    op = ev.evaluate(make_event(id="p", tags=["first_visit"], artist_listeners=3_000_000, status="onsale",
                                presales=[Presale(name="Fan klub", start=soon)], public_onsale=soon + timedelta(days=1)))
    state = {"dogadaji": {"x|y|z": {"datum": "2030-01-01"}}, "najave": {}}  # nije prvo pokretanje
    kinds = [a.kind for a in scan_alerts([op], state, now, threshold=50)]
    assert "PRODAJA USKORO" in kinds
    assert "PRODAJA USKORO" not in [a.kind for a in scan_alerts([op], state, now, threshold=50)]


def test_announcement_alerts(now):
    hot = Announcement(source="muzika.hr", title="Zbog velikog interesa dodatni koncert u Areni Zagreb", link="https://x/1",
                       published=now, artist="Big Star", fans=5_000_000, region_score=3, places=["Zagreb"],
                       presale=now + timedelta(days=3))
    meh = Announcement(source="x", title="Lokalni bend u klubu", link="https://x/2", published=now, region_score=1)
    assert hype_announcement(hot)[0] >= 80 and hype_announcement(meh)[0] < 30
    state = {"dogadaji": {}, "najave": {"https://x/old": {"dan": now.date().isoformat()}}}
    alerts = announcement_alerts([hot, meh], state, now, threshold=70)
    assert [a.url for a in alerts] == ["https://x/1"] and alerts[0].kind == "NAJAVA"
    assert announcement_alerts([hot, meh], state, now) == []
    assert "<b>" in alerts[0].text() and "&lt;" not in alerts[0].text()


def test_split_messages_and_token_check():
    parts = split_messages(["a" * 3000, "b" * 3000, "c"], limit=4000)
    assert len(parts) == 2 and parts[1].endswith("c")
    with pytest.raises(ProviderError, match="TELEGRAM_BOT_TOKEN"):
        telegram_send("", "1", "x")


def test_run_radar_with_demo_and_cli(tmp_path, now, monkeypatch, capsys):
    s = Settings(None, None, None, ["svijet"], 1000.0, tmp_path / "cache")
    out = run_radar(ScanOptions(demo=True, segment="all", countries=["svijet"]), s, tmp_path / "stanje", threshold=50,
                    announcements=False, now=now)
    assert out["alerts"] and (tmp_path / "stanje" / "radar_stanje.json").is_file()
    assert telegram_blocks(out)[0].startswith("🎟️")
    again = run_radar(ScanOptions(demo=True, segment="all", countries=["svijet"]), s, tmp_path / "stanje", threshold=50,
                      announcements=False, now=now)
    assert again["alerts"] == []
    monkeypatch.setenv("KARTE_DATA_DIR", str(tmp_path / "cli"))
    env = str(tmp_path / "nema.env")
    assert main(["--env", env, "radar", "--demo", "--bez-najava", "--prag", "50"]) == 0
    assert "RADAR" in capsys.readouterr().out
    assert main(["--env", env, "radar", "--demo", "--bez-najava", "--prag", "0", "--posalji"]) in (0, 2)
    assert main(["--env", env, "telegram", "--test"]) == 1  # bez tokena: jasna poruka, bez mreže
