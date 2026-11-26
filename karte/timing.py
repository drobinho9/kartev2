"""Kada prodati: stvarna krivulja kretanja najniže cijene na StubHubu (NeedATicket, karte/data/vrijeme_prodaje.json).

rel(dana) = najniža cijena X dana prije događaja / najniža cijena na dan događaja (medijan po segmentu).
Npr. velike dvorane: 30 dana prije ×1,20, 14 dana ×1,11, 7 dana ×1,05, 3 dana ×1,00 → cijene u pravilu PADAJU prema
datumu, pa preprodavač treba prodavati rano. Kazalište je obrnuto (cijene rastu).

Veličina dvorane nije definirana u izvoru; pretpostavka: velika ≥ 10.000, srednja 2.000–10.000, mala < 2.000 mjesta.
"""

from __future__ import annotations

from functools import lru_cache

from karte.knowledge import load_json_resource
from karte.models import Event

LARGE, SMALL = 10_000, 2_000


@lru_cache(maxsize=1)
def data() -> dict:
    try:
        return load_json_resource("vrijeme_prodaje.json")
    except (FileNotFoundError, OSError, ValueError):
        return {"krivulje": {}}


def segment_key(event: Event) -> tuple[str, str]:
    """(tržište, segment) – prvo veličina dvorane ako je poznata, inače vrsta događaja."""
    country = (event.country or "").upper()
    scope = "US" if country in ("US", "CA") else ("GB" if country == "GB" else "ALL")
    if event.capacity:
        size = "large" if event.capacity >= LARGE else ("mid" if event.capacity >= SMALL else "small")
    else:
        size = "sports" if event.segment == "sport" else "concerts"
    return scope, size


def curve(event: Event) -> tuple[str, dict] | None:
    curves = data().get("krivulje", {})
    scope, seg = segment_key(event)
    for key in (f"{scope}:{seg}", f"ALL:{seg}", f"ALL:{'sports' if event.segment == 'sport' else 'concerts'}", "ALL:all"):
        c = curves.get(key)
        if c and len(c.get("tocke", [])) >= 3:
            return key, c
    return None


def rel(event: Event, days: float) -> float:
    """Medijan najniže cijene X dana prije događaja u odnosu na dan događaja (linearna interpolacija, izvan raspona rub)."""
    found = curve(event)
    if not found:
        return 1.0
    pts = sorted(((p["dana_prije"], 1 + p["medijan_pct"] / 100) for p in found[1]["tocke"]))
    if days <= pts[0][0]:
        return pts[0][1] if days > 0 else 1.0
    if days >= pts[-1][0]:
        return pts[-1][1]
    for (d0, v0), (d1, v1) in zip(pts, pts[1:]):
        if d0 <= days <= d1:
            return v0 + (v1 - v0) * (days - d0) / (d1 - d0)
    return 1.0


def insight(event: Event) -> str | None:
    """Jedna rečenica za savjet prodaje: što stvarni podaci kažu o kretanju cijene za ovakav događaj."""
    found = curve(event)
    if not found:
        return None
    key, c = found
    p30 = next((p for p in c["tocke"] if p["dana_prije"] == 30), c["tocke"][-1])
    labels = {"large": "velike dvorane i stadioni", "mid": "srednje dvorane", "small": "mali klubovi", "sports": "sport",
              "concerts": "koncerti", "theater": "kazalište", "all": "svi događaji"}
    seg = labels.get(key.split(":")[1], key)
    change = p30["medijan_pct"]
    dearer = p30["udio_skuplje"] * 100
    if change >= 5 or dearer >= 50:
        tip = "cijene u pravilu padaju prema datumu – prodaj rano, ne čekaj zadnji tjedan"
    elif change <= -5:
        tip = "cijene u pravilu rastu prema datumu – nema žurbe s prodajom"
    else:
        tip = "cijena je u medijanu stabilna, ali kod mnogih događaja kasnije pada – ne čekaj zadnje dane"
    count = f"{c['dogadaja']:,}".replace(",", ".")
    return (f"Stvarni podaci sa StubHuba ({seg}, {count} događaja, NeedATicket): {p30['dana_prije']} dana prije najniža "
            f"cijena je u medijanu {change:+.0f} % u odnosu na dan događaja, a kod {dearer:.0f} % događaja je kasnije pala – {tip}.")
