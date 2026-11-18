import pytest

from datetime import datetime

from karte.knowledge import ModelConfig, deep_merge, venue_capacity
from karte.util import fmt_eur, normalize, parse_bool, parse_datetime, parse_float


def test_parse_float_handles_croatian_and_english_formats():
    assert parse_float("1.234,50") == 1234.5
    assert parse_float("20,00") == 20.0
    assert parse_float("49.9") == 49.9
    assert parse_float("45 €") == 45.0
    assert parse_float("") is None
    assert parse_float("abc") is None


def test_parse_datetime_formats():
    assert parse_datetime("2027-03-14T19:00:00Z") == datetime(2027, 3, 14, 19, 0)
    assert parse_datetime("2027-03-14 20:00") == datetime(2027, 3, 14, 20, 0)
    assert parse_datetime("20.01.2027.") == datetime(2027, 1, 20)
    assert parse_datetime("2027-03-14T20:00:00+01:00") == datetime(2027, 3, 14, 19, 0)
    assert parse_datetime(None) is None


def test_normalize_strips_diacritics():
    assert normalize("Štark Arena – Beograd") == "stark arena beograd"
    assert normalize("Đorđe Balašević") == "dorde balasevic"


def test_parse_bool():
    assert parse_bool("da") is True
    assert parse_bool("ne") is False
    assert parse_bool("") is None


def test_fmt_eur_no_negative_zero():
    assert fmt_eur(-0.2) == "0 €"
    assert fmt_eur(1234.5, 2) == "1.234,50 €"


def test_venue_capacity_exact_alias_and_partial():
    assert venue_capacity("Arena Zagreb") == 16000
    assert venue_capacity("Wiener Stadthalle - Halle D") == 16000
    assert venue_capacity("Stark Arena") == 20000
    assert venue_capacity("Nepoznata dvorana XYZ") is None


def test_model_override_deep_merge(tmp_path):
    override = tmp_path / "m.toml"
    override.write_text("[verdict]\nbuy_roi = 0.5\n", encoding="utf-8")
    cfg = ModelConfig.load(override)
    assert cfg.get("verdict", "buy_roi") == 0.5
    assert cfg.get("verdict", "consider_roi") == 0.10  # ostalo netaknuto
    assert deep_merge({"a": {"b": 1, "c": 2}}, {"a": {"b": 3}}) == {"a": {"b": 3, "c": 2}}


def test_fx_conversion():
    cfg = ModelConfig.load()
    assert cfg.to_eur(100, "EUR") == 100
    assert cfg.to_eur(12000, "HUF") == pytest.approx(30.0)
    assert cfg.primary_fee("ticketmaster") == (0.12, 0.0)
    assert cfg.primary_fee("nepoznat") == (0.10, 1.0)
