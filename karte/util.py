"""Pomoćne funkcije."""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date, datetime, timedelta, timezone


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def log_scale(value: float | None, low: float, high: float) -> float | None:
    """Vrijednost na log skali između low (0) i high (1); None ako nema podatka."""
    if value is None or value <= 0:
        return None
    return clamp((math.log10(value) - math.log10(low)) / (math.log10(high) - math.log10(low)))


_DIACRITICS = str.maketrans({"đ": "d", "Đ": "D", "ø": "o", "Ø": "O", "ß": "ss", "æ": "ae"})


def normalize(text: str | None) -> str:
    """Mala slova, bez dijakritika i interpunkcije – za usporedbu naziva."""
    if not text:
        return ""
    text = text.translate(_DIACRITICS)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-zA-Z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def parse_datetime(value: str | None) -> datetime | None:
    """Parsira ISO datume ('2026-12-01', '2026-12-01 20:00', '2026-12-01T19:00:00Z')."""
    if not value:
        return None
    value = str(value).strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    for fmt in (None, "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M", "%d.%m.%Y.", "%d.%m.%Y"):
        try:
            dt = datetime.fromisoformat(value) if fmt is None else datetime.strptime(value, fmt)
        except ValueError:
            continue
        return to_naive_utc(dt)
    return None


def to_naive_utc(dt: datetime) -> datetime:
    """Sve datume držimo kao 'naivne' (bez zone) radi jednostavne usporedbe."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def days_between(a: datetime, b: datetime) -> int:
    """Broj kalendarskih dana od a do b (može biti negativan)."""
    return (b.date() - a.date()).days


def iso_z(dt: datetime) -> str:
    """Format koji traži Ticketmaster: 2026-11-18T00:00:00Z."""
    return dt.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def fmt_date(dt: datetime | date | None) -> str:
    if dt is None:
        return "—"
    return dt.strftime("%d.%m.%Y.")


def fmt_datetime(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    if dt.hour == 0 and dt.minute == 0:
        return fmt_date(dt)
    return dt.strftime("%d.%m.%Y. %H:%M")


def fmt_eur(value: float | None, decimals: int = 0) -> str:
    if value is None:
        return "—"
    if abs(value) < 0.5 * 10 ** (-decimals):
        value = 0.0
    s = f"{value:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def fmt_pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:+.0f} %"


def parse_bool(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    v = str(value).strip().lower()
    if v in {"1", "true", "da", "yes", "y", "d", "x"}:
        return True
    if v in {"0", "false", "ne", "no", "n"}:
        return False
    return None


def parse_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    v = str(value).strip().replace("€", "").replace(" ", "")
    if not v:
        return None
    # Podrži i "1.234,50" i "1234.50"
    if "," in v and "." in v:
        v = v.replace(".", "").replace(",", ".")
    elif "," in v:
        v = v.replace(",", ".")
    try:
        return float(v)
    except ValueError:
        return None


def parse_int(value) -> int | None:
    f = parse_float(value)
    return int(f) if f is not None else None


def add_days(dt: datetime, days: float) -> datetime:
    return dt + timedelta(days=days)
