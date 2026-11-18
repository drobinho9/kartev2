import json
from datetime import datetime
from pathlib import Path

from conftest import FIXTURES, FakeHttp, load_fixture

from karte.cli import main
from karte.net import redact
from karte.pipeline import ScanOptions, annotate_supply, merge_events, run_scan
from karte.providers import lastfm, seatgeek, ticketmaster
from karte.providers.demo import load_demo
from karte.providers.manual import load_csv
from karte.settings import Settings


def _settings(tmp_path, **kw) -> Settings:
    base = dict(ticketmaster_api_key=None, seatgeek_client_id=None, lastfm_api_key=None, countries=["AT"], budget=1000.0, cache_dir=tmp_path)
    base.update(kw)
    return Settings(**base)


def test_ticketmaster_parse_event():
    raws = load_fixture("ticketmaster_events.json")["_embedded"]["events"]
    ev = ticketmaster.parse_event(raws[0])
    assert ev.artist == "Test Band"
    assert ev.country == "AT" and ev.city == "Wien"
    assert ev.face_min == 69.9 and ev.face_max == 159.9
    assert ev.ticket_limit == 6
    assert ev.personalized is True
    assert ev.artist_upcoming_events == 32
    assert ev.presales[0].name == "Artist Presale"
    assert ev.public_onsale == datetime(2026, 11, 27, 9, 0)
    assert ev.date == datetime(2027, 3, 14, 19, 0)
    other = ticketmaster.parse_event(raws[1])
    assert other.status == "offsale" and other.face_min is None and other.date == datetime(2026, 12, 20)
    assert ticketmaster.parse_event(raws[2]) is None


def test_ticketmaster_provider_paginates_and_sends_params(now):
    http = FakeHttp({ticketmaster.BASE_URL: load_fixture("ticketmaster_events.json")})
    tm = ticketmaster.TicketmasterProvider("SECRET", http)
    events = tm.events_between(["AT", "DE"], now, datetime(2027, 1, 17))
    assert len(events) == 2  # isti događaji (isti ID) se ne dupliciraju
    assert len(http.calls) == 2  # jedan upit po državi
    url, params = http.calls[0]
    assert params["countryCode"] == "AT" and params["classificationName"] == "music"
    assert params["startDateTime"] == "2026-11-18T10:00:00Z"
    tm.onsales_between(["AT"], now, datetime(2026, 12, 18), datetime(2027, 11, 18))
    assert "onsaleStartDateTime" in http.calls[-1][1]


def test_seatgeek_parse_event():
    raw = load_fixture("seatgeek_events.json")["events"][0]
    ev = seatgeek.parse_event(raw)
    assert ev.secondary.lowest == 180 and ev.secondary.listing_count == 120
    assert ev.capacity == 16000 and ev.currency == "USD"


def test_lastfm_parse_and_enrich(make_event):
    assert lastfm.parse_listeners(load_fixture("lastfm_artist.json")) == 2_400_000
    assert lastfm.parse_listeners({"error": 6, "message": "not found"}) is None
    http = FakeHttp({lastfm.BASE_URL: load_fixture("lastfm_artist.json")})
    events = [make_event(artist_listeners=None), make_event(id="t2", artist_listeners=None)]
    lastfm.LastFmProvider("K", http).enrich(events)
    assert all(e.artist_listeners == 2_400_000 for e in events)
    assert len(http.calls) == 1  # isti izvođač → jedan poziv


def test_manual_csv_with_croatian_headers():
    events = load_csv(FIXTURES / "dogadaji.csv")
    assert len(events) == 2
    big, small = events
    assert big.artist == "Regionalna Zvijezda" and big.face_min == 35 and big.ticket_limit == 4
    assert big.personalized is False
    assert set(big.tags) == {"regional_star", "added_date"}
    assert big.secondary.lowest == 80 and big.secondary.source == "ručno (viagogo)"
    assert big.artist_listeners == 200000 and big.primary_vendor == "entrio"
    assert small.status == "announced" and small.face_min == 20.0
    assert small.date == datetime(2027, 1, 20)
    assert small.public_onsale == datetime(2026, 12, 1, 10, 0)


def test_merge_prefers_event_with_face_value_and_keeps_secondary():
    tm = ticketmaster.parse_event(load_fixture("ticketmaster_events.json")["_embedded"]["events"][0])
    sg = seatgeek.parse_event(load_fixture("seatgeek_events.json")["events"][0])
    sg.date = tm.date  # isti dan
    merged = merge_events([sg, tm])
    assert len(merged) == 1
    ev = merged[0]
    assert ev.source == "ticketmaster" and ev.secondary is not None and ev.capacity == 16000


def test_annotate_supply_counts_shows_and_fills_capacity(now):
    events = [e for e in load_demo(now) if e.artist == "Orbit Kids"]
    for e in events:
        e.capacity = None
    annotate_supply(events)
    assert all(e.shows_in_region == 3 for e in events)
    assert all(e.capacity == 16000 and e.capacity_estimated for e in events)


def test_run_scan_demo(tmp_path, now):
    result = run_scan(ScanOptions(demo=True, countries=["HR"], now=now), _settings(tmp_path))
    verdicts = {op.verdict for op in result.opportunities}
    assert {"KUPI", "PRESKOČI", "ZAKONSKI OGRANIČENO", "RASPRODANO"} <= verdicts
    assert result.is_demo
    assert all(op.advice.get("summary") for op in result.opportunities)


def test_run_scan_with_apis(tmp_path, now):
    http = FakeHttp({
        ticketmaster.BASE_URL: load_fixture("ticketmaster_events.json"),
        lastfm.BASE_URL: load_fixture("lastfm_artist.json"),
    })
    settings = _settings(tmp_path, ticketmaster_api_key="K", lastfm_api_key="L")
    result = run_scan(ScanOptions(days=60, onsale_days=30, countries=["AT"], now=now), settings, http=http)
    artists = {op.event.artist for op in result.opportunities}
    assert "Test Band" in artists  # izvan 60 dana, ali prodaja počinje za 7 dana
    assert any("Ticketmaster" in s for s in result.sources)
    assert all(op.event.artist_listeners == 2_400_000 for op in result.opportunities)


def test_run_scan_hides_events_without_price_unless_show_all(tmp_path, now):
    http = FakeHttp({ticketmaster.BASE_URL: load_fixture("ticketmaster_events.json")})
    settings = _settings(tmp_path, ticketmaster_api_key="K")
    hidden = run_scan(ScanOptions(countries=["DE"], now=now, use_lastfm=False), settings, http=http)
    assert "Another Artist" not in {op.event.artist for op in hidden.opportunities}
    assert any("bez nominalne cijene" in w for w in hidden.warnings)
    shown = run_scan(ScanOptions(countries=["DE"], now=now, use_lastfm=False, show_all=True), settings, http=http)
    assert "Another Artist" in {op.event.artist for op in shown.opportunities}


def test_run_scan_expands_regions(tmp_path, now):
    http = FakeHttp({ticketmaster.BASE_URL: load_fixture("ticketmaster_events.json")})
    opts = ScanOptions(countries=["dach"], now=now, use_lastfm=False, onsale_days=0)
    run_scan(opts, _settings(tmp_path, ticketmaster_api_key="K"), http=http)
    assert [c[1]["countryCode"] for c in http.calls] == ["DE", "AT", "CH"]


def test_run_scan_without_keys_warns(tmp_path, now):
    result = run_scan(ScanOptions(countries=["HR"], now=now), _settings(tmp_path))
    assert result.opportunities == []
    assert any("TICKETMASTER_API_KEY" in w for w in result.warnings)


def test_redact_hides_api_keys():
    assert redact("https://x/?apikey=abc&size=1") == "https://x/?apikey=***&size=1"
    assert "secret" not in redact("https://x/?client_id=secret&api_key=secret")


def test_cli_scan_formats(tmp_path, capsys):
    out = tmp_path / "r.json"
    assert main(["--env", str(tmp_path / "none.env"), "scan", "--demo", "--format", "json", "--out", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["is_demo"] and data["opportunities"]
    for fmt in ("html", "md", "csv"):
        path = tmp_path / f"r.{fmt}"
        assert main(["--env", str(tmp_path / "none.env"), "scan", "--demo", "--format", fmt, "--out", str(path)]) == 0
        assert path.stat().st_size > 1000
    assert "<!doctype html>" in (tmp_path / "r.html").read_text(encoding="utf-8")
    assert main(["--env", str(tmp_path / "none.env"), "scan", "--demo", "--only", "KUPI"]) == 0
    assert "KUPI" in capsys.readouterr().out


def test_cli_markets_and_us_state_law(tmp_path, capsys):
    env = str(tmp_path / "none.env")
    assert main(["--env", env, "markets", "--details"]) == 0
    out = capsys.readouterr().out
    assert "SAD" in out and "Japan" in out
    assert out.index("SAD") < out.index("Japan")  # SAD je bolje rangiran od Japana
    assert main(["--env", env, "laws", "--country", "US-VT"]) == 0
    assert "Vermont" in capsys.readouterr().out
    assert main(["--env", env, "platforms", "--country", "US", "--vendor", "ticketmaster"]) == 0
    assert "Ne primaju prodavatelje iz HR" in capsys.readouterr().out


def test_cli_calc_platforms_laws(tmp_path, capsys):
    env = str(tmp_path / "none.env")
    assert main(["--env", env, "calc", "--face", "50", "--resale", "130", "--listeners", "1500000", "--capacity", "16000"]) == 0
    out = capsys.readouterr().out
    assert "viagogo" in out and "CJENIK" in out
    assert main(["--env", env, "platforms", "--country", "HR"]) == 0
    assert "Njuškalo" in capsys.readouterr().out
    assert main(["--env", env, "laws", "--country", "IE"]) == 0
    assert "Irska" in capsys.readouterr().out
    assert main(["--env", env, "doctor", "--offline"]) == 0


def test_example_csv_in_repo_is_valid():
    path = Path(__file__).parent.parent / "primjeri" / "dogadaji.csv"
    events = load_csv(path)
    assert len(events) >= 3
