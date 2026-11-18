"""Analiza kategorija: koje ulaznice za isti koncert se najisplativije preprodaju.

Empirijska pravila (vidi karte/data/guides/koje_karte.md):
- jeftinije kategorije s dobrim pogledom imaju najveći POSTOTNI skok i najbrže se prodaju,
- parter/stajanje blizu bine i prednji sektori nose dodatnu premiju,
- VIP paketi i skupe kategorije imaju veći apsolutni iznos, ali manji postotak i sporiju prodaju,
- zaklonjena mjesta se teško prodaju.
Ako za kategoriju upišeš stvarnu najnižu cijenu s viagoga, ona ima prednost pred procjenom.
"""

from __future__ import annotations

import dataclasses
import statistics
from dataclasses import dataclass

from karte.advisor import build_advice
from karte.models import Event, SecondaryMarket
from karte.scoring import Evaluator
from karte.util import clamp

KINDS = {
    "front": ("Prednji sektor / Golden circle", 1.15, 1.03),
    "parter": ("Parter / stajanje", 1.10, 1.03),
    "standard": ("Sjedeće – standard", 1.00, 1.00),
    "tribina": ("Tribina / gornji prsten", 0.95, 0.98),
    "vip": ("VIP paket / hospitality", 0.85, 0.90),
    "zaklonjeno": ("Zaklonjeni pogled", 0.75, 0.85),
}
# Jeftinije kategorije (u odnosu na medijan) imaju veći postotni skok: (cijena/medijan)^-ELASTICITY
ELASTICITY = 0.35


@dataclass
class CategoryInput:
    name: str
    face: float
    kind: str = "standard"
    secondary_lowest: float | None = None
    secondary_source: str = "ručno (viagogo)"
    listing_count: int | None = None


def analyze(base: Event, categories: list[CategoryInput], evaluator: Evaluator) -> dict:
    cats = [c for c in categories if c.face and c.face > 0]
    if not cats:
        return {"rows": [], "summary": "Upiši barem jednu kategoriju s nominalnom cijenom."}
    median_face = statistics.median(c.face for c in cats)
    original_category = evaluator.category
    evaluator.category = "cheap"  # svaka kategorija ima jednu cijenu
    rows = []
    try:
        for c in cats:
            label, kind_mult, kind_p = KINDS.get(c.kind, KINDS["standard"])
            rel = c.face / median_face
            mult_adjust = clamp(rel ** -ELASTICITY, 0.75, 1.35) * kind_mult
            p_adjust = clamp(1 + 0.10 * (1 - rel), 0.85, 1.10) * kind_p
            secondary = None
            if c.secondary_lowest:
                secondary = SecondaryMarket(
                    source=c.secondary_source or "ručno", lowest=c.secondary_lowest, currency=base.currency, listing_count=c.listing_count
                )
            event = dataclasses.replace(base, face_min=c.face, face_max=c.face, secondary=secondary)
            op = evaluator.evaluate(event, multiplier_adjust=1.0 if secondary else mult_adjust, p_adjust=p_adjust)
            op.advice = build_advice(op, evaluator.cfg)
            rows.append(
                {
                    "name": c.name,
                    "kind": c.kind,
                    "kind_label": label,
                    "face": c.face,
                    "face_eur": op.face_ref,
                    "currency": base.currency,
                    "buy_cost": op.buy_cost,
                    "multiplier": op.multiplier,
                    "multiplier_source": op.multiplier_source,
                    "expected_resale": op.expected_resale,
                    "net": op.best.net_payout if op.best else None,
                    "profit": op.profit,
                    "p_sell": op.best.p_sell if op.best else None,
                    "expected_value": op.expected_value,
                    "roi": op.roi,
                    "verdict": op.verdict,
                    "platform": op.best.name if op.best else None,
                    "pair_capital": (op.buy_cost or 0) * 2,
                    "risk": op.risk,
                    "demand": op.demand.score,
                }
            )
    finally:
        evaluator.category = original_category

    valid = [r for r in rows if r["roi"] is not None]
    summary = "Nema izračuna (provjeri pravila države – možda je preprodaja ograničena)."
    if valid:
        best_roi = max(valid, key=lambda r: r["roi"])
        best_ev = max(valid, key=lambda r: r["expected_value"] or -1e9)
        parts = [f"Najbolji povrat: {best_roi['name']} (oček. ROI {best_roi['roi'] * 100:+.0f} %)"]
        if best_ev is not best_roi:
            parts.append(f"najveća očekivana zarada po ulaznici: {best_ev['name']} (~{best_ev['expected_value']:.0f} €)")
        losers = [r["name"] for r in valid if r["roi"] < 0]
        if losers:
            parts.append("izbjegavaj: " + ", ".join(losers))
        summary = "; ".join(parts) + "."
        for r in rows:
            r["best_roi"] = r is best_roi
            r["best_ev"] = r is best_ev
    rows.sort(key=lambda r: (r["roi"] is None, -(r["roi"] or 0)))
    return {"rows": rows, "summary": summary, "median_face": median_face}
