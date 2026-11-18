import pytest

from karte import legal
from karte.platforms import available_platforms, load_platforms


def test_croatia_has_no_price_cap():
    r = legal.evaluate("HR", 50, 55)
    assert r.cap_price is None
    assert r.profit_prohibited is False
    assert "botov" in r.summary.lower()


def test_ireland_caps_at_face_value():
    r = legal.evaluate("IE", 60, 66)
    assert r.cap_price == 60
    assert r.profit_prohibited is True


def test_germany_planned_cap_only_with_strict():
    loose = legal.evaluate("DE", 100, 110)
    assert loose.cap_price is None and loose.planned_rule == "percent_or_abs"
    strict = legal.evaluate("DE", 100, 110, strict=True)
    # 20 % od plaćenog (22 €) je više od 20 € → vrijedi +20 €
    assert strict.planned_applied is True
    assert strict.cap_price == pytest.approx(130.0)
    cheap = legal.evaluate("DE", 40, 44, strict=True)
    assert cheap.cap_price == pytest.approx(44 * 1.2)


def test_uk_planned_face_value_cap():
    strict = legal.evaluate("GB", 80, 90, strict=True)
    assert strict.cap_price == 90  # nominalna + neizbježne naknade
    assert strict.profit_prohibited is True


def test_unknown_country_falls_back_to_default():
    r = legal.evaluate("ZZ", 50, 55)
    assert r.cap_price is None
    assert "nisu u bazi" in r.summary


def test_platform_fee_math():
    viagogo = load_platforms()["viagogo"]
    assert viagogo.net(100) == pytest.approx(85)
    assert viagogo.net(viagogo.break_even(68)) == pytest.approx(68)
    assert viagogo.pays_after_event


def test_platform_caps():
    plats = load_platforms()
    assert plats["ticketswap"].cap_price(face_ref=50, buy_cost=55) == pytest.approx(66)
    assert plats["twickets"].cap_price(face_ref=50, buy_cost=55) == 50
    assert plats["viagogo"].cap_price(50, 55) is None


def test_vendor_specific_platforms_and_local_names():
    hr = {p.key for p in available_platforms("HR", "entrio")}
    assert {"viagogo", "lokalni_oglasnik", "facebook_grupe"} <= hr
    assert "ticketmaster_resale" not in hr
    at_tm = {p.key for p in available_platforms("AT", "ticketmaster")}
    assert "ticketmaster_resale" in at_tm
    assert "fansale" not in at_tm  # samo za Eventim ulaznice
    local = load_platforms()["lokalni_oglasnik"]
    assert local.display_name("HR").startswith("Njuškalo")
