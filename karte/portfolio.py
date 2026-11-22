"""Plan zarade: raspodjela budžeta na najbolje prilike, simulacija ishoda i kalendar radnji.

Ulaz su procjene iz `run_scan` (KUPI/RAZMOTRI), a za događaje bez nominalne cijene (PROVJERI CIJENU)
plan pokazuje *uvjetne* pozicije: što bi se očekivalo ako ulaznice kupiš po najvišoj isplativoj cijeni.

Simulacija (Monte Carlo) za svaki par ulaznica slučajno odlučuje proda li se (vjerojatnost iz modela)
i po kojoj cijeni (±20 % oko očekivane), pa daje raspon ishoda i vjerojatnost gubitka za cijeli plan.
Nije prognoza – pokazuje koliko je ishod osjetljiv na sreću i na točnost procjene.
"""

from __future__ import annotations

import dataclasses
import math
import random
from dataclasses import dataclass, field
from datetime import datetime

from karte.advisor import build_advice
from karte.knowledge import ModelConfig
from karte.models import Opportunity
from karte.scoring import Evaluator
from karte.util import add_days, clamp, fmt_date, hr_plural

BUY_VERDICTS = ("KUPI", "RAZMOTRI")


@dataclass
class Position:
    op: Opportunity
    qty: int
    unit_cost: float  # trošak po ulaznici s naknadama (EUR)
    net: float  # neto po ulaznici ako se proda na najboljoj platformi
    salvage: float  # po ulaznici ako se ne proda (prodaja u bescjenje; 0 za personalizirane)
    p_sell: float
    platform: str
    conditional: bool = False  # pretpostavka: kupljeno po max_buy (nominalna cijena nije poznata)
    assumed_face: float | None = None

    @property
    def cost(self) -> float:
        return self.unit_cost * self.qty

    @property
    def expected_profit(self) -> float:
        per_ticket = self.p_sell * self.net + (1 - self.p_sell) * self.salvage - self.unit_cost
        return per_ticket * self.qty

    @property
    def roi(self) -> float:
        return self.expected_profit / self.cost if self.cost else 0.0

    def as_dict(self) -> dict:
        e = self.op.event
        return {
            "event_id": e.id,
            "artist": e.artist,
            "name": e.name,
            "city": e.city,
            "country": e.country,
            "date": e.date.isoformat(),
            "verdict": self.op.verdict,
            "qty": self.qty,
            "unit_cost": round(self.unit_cost, 2),
            "cost": round(self.cost, 2),
            "net": round(self.net, 2),
            "p_sell": round(self.p_sell, 3),
            "expected_profit": round(self.expected_profit, 2),
            "roi": round(self.roi, 4),
            "platform": self.platform,
            "conditional": self.conditional,
            "assumed_face": self.assumed_face,
            "phase": self.op.phase,
            "url": e.url,
        }


@dataclass
class Plan:
    budget: float
    positions: list[Position] = field(default_factory=list)
    conditional: list[Position] = field(default_factory=list)
    watch: list[Opportunity] = field(default_factory=list)
    simulation: dict = field(default_factory=dict)
    conditional_simulation: dict = field(default_factory=dict)
    calendar: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def invested(self) -> float:
        return sum(p.cost for p in self.positions)

    @property
    def expected_profit(self) -> float:
        return sum(p.expected_profit for p in self.positions)

    def as_dict(self) -> dict:
        return {
            "budget": self.budget,
            "invested": round(self.invested, 2),
            "expected_profit": round(self.expected_profit, 2),
            "positions": [p.as_dict() for p in self.positions],
            "conditional": [p.as_dict() for p in self.conditional],
            "conditional_cost": round(sum(p.cost for p in self.conditional), 2),
            "conditional_profit": round(sum(p.expected_profit for p in self.conditional), 2),
            "watch": [
                {
                    "artist": op.event.artist,
                    "city": op.event.city,
                    "country": op.event.country,
                    "date": op.event.date.isoformat(),
                    "verdict": op.verdict,
                    "demand": round(op.demand.score, 3),
                    "max_buy": op.max_buy,
                    "url": op.event.url,
                    "reason": op.verdict_reason,
                }
                for op in self.watch
            ],
            "simulation": self.simulation,
            "conditional_simulation": self.conditional_simulation,
            "calendar": self.calendar,
            "notes": self.notes,
        }


def _position(op: Opportunity, qty: int, cfg: ModelConfig, conditional: bool = False, face: float | None = None) -> Position | None:
    best = op.best
    if best is None or not op.buy_cost or qty <= 0:
        return None
    salvage = 0.0 if op.event.personalized else cfg.get("sell", "salvage_ratio", 0.6) * (op.face_ref or 0)
    return Position(
        op=op, qty=qty, unit_cost=op.buy_cost, net=best.net_payout, salvage=salvage, p_sell=best.p_sell,
        platform=best.name, conditional=conditional, assumed_face=face,
    )


def _even(qty: int) -> int:
    return qty - 1 if qty >= 2 and qty % 2 else qty


def build_plan(
    ops: list[Opportunity],
    budget: float,
    evaluator: Evaluator | None = None,
    max_share: float | None = None,
    simulations: int = 4000,
    seed: int = 42,
) -> Plan:
    cfg = evaluator.cfg if evaluator else ModelConfig.load()
    share = max_share if max_share is not None else cfg.get("sizing", "max_budget_share", 0.25)
    plan = Plan(budget=budget)
    left = budget
    per_event = budget * share

    candidates = sorted(
        (op for op in ops if op.verdict in BUY_VERDICTS and op.best and op.buy_cost and (op.expected_value or 0) > 0),
        key=lambda op: (op.verdict != "KUPI", -(op.roi or 0), op.event.date),
    )
    for op in candidates:
        wanted = op.suggested_qty or cfg.get("sizing", "default_qty", 2)
        affordable = math.floor(min(per_event, left) / op.buy_cost) if op.buy_cost else 0
        qty = _even(min(wanted, affordable, op.event.ticket_limit or wanted))
        pos = _position(op, qty, cfg)
        if pos:
            plan.positions.append(pos)
            left -= pos.cost

    if evaluator is not None:
        for op in ops:
            if op.verdict != "PROVJERI CIJENU" or not op.max_buy:
                continue
            trial = evaluator.evaluate(dataclasses.replace(op.event, face_min=op.max_buy, face_max=op.max_buy, currency="EUR"))
            trial.advice = build_advice(trial, cfg)
            qty = _even(min(cfg.get("sizing", "default_qty", 2), math.floor(per_event / trial.buy_cost) if trial.buy_cost else 0))
            pos = _position(trial, qty, cfg, conditional=True, face=op.max_buy)
            if pos:
                plan.conditional.append(pos)
        plan.conditional.sort(key=lambda p: -p.expected_profit)

    chosen = {p.op.event.id for p in plan.positions}
    plan.watch = sorted(
        (op for op in ops if op.event.id not in chosen and op.verdict in ("NEMA CIJENE", "RASPRODANO") and op.demand.score >= 0.6),
        key=lambda op: -op.demand.score,
    )[:10]

    plan.simulation = simulate(plan.positions, simulations, seed)
    plan.conditional_simulation = simulate(plan.conditional, simulations, seed)
    plan.calendar = calendar(plan.positions + plan.conditional)
    plan.notes = _notes(plan, budget)
    return plan


def simulate(positions: list[Position], runs: int = 4000, seed: int = 42, price_sigma: float = 0.20) -> dict:
    """Raspon ishoda plana: po paru ulaznica prodaja s vjerojatnošću p_sell, cijena ±price_sigma oko očekivane."""
    if not positions or runs <= 0:
        return {}
    rng = random.Random(seed)
    totals: list[float] = []
    for _ in range(runs):
        total = 0.0
        for pos in positions:
            units = [2] * (pos.qty // 2) + ([1] if pos.qty % 2 else [])
            for n in units:
                if rng.random() < pos.p_sell:
                    factor = clamp(rng.gauss(1.0, price_sigma), 0.5, 1.6)
                    proceeds = pos.net * factor * n
                else:
                    proceeds = pos.salvage * n
                total += proceeds - pos.unit_cost * n
        totals.append(total)
    totals.sort()

    def pct(q: float) -> float:
        return round(totals[min(len(totals) - 1, int(q * len(totals)))], 2)

    lo, hi = totals[0], totals[-1]
    bins = 10
    width = (hi - lo) / bins or 1.0
    hist = [0] * bins
    for t in totals:
        hist[min(bins - 1, int((t - lo) / width))] += 1
    return {
        "runs": runs,
        "mean": round(sum(totals) / len(totals), 2),
        "p05": pct(0.05),
        "p50": pct(0.50),
        "p95": pct(0.95),
        "worst": round(lo, 2),
        "best": round(hi, 2),
        "prob_loss": round(sum(1 for t in totals if t < 0) / len(totals), 4),
        "histogram": [
            {"from": round(lo + i * width, 2), "to": round(lo + (i + 1) * width, 2), "share": round(c / len(totals), 4)}
            for i, c in enumerate(hist)
        ],
    }


def calendar(positions: list[Position]) -> list[dict]:
    """Radnje po datumima: kupnja (presale/javna prodaja), oglašavanje, spuštanje cijene, događaj, isplata."""
    items: list[dict] = []
    for pos in positions:
        op, e = pos.op, pos.op.event
        label = f"{e.artist} – {e.city}"
        cond = " (ako je nominalna ≤ " + f"{pos.assumed_face:.0f} €)" if pos.conditional and pos.assumed_face else ""
        for p in e.presales:
            if p.start:
                items.append({"date": p.start.isoformat(), "kind": "buy", "event": label, "text": f"Presale „{p.name}” – kupi {pos.qty} kom{cond}"})
        if e.public_onsale and (not e.presales):
            items.append({"date": e.public_onsale.isoformat(), "kind": "buy", "event": label, "text": f"Javna prodaja – kupi {pos.qty} kom{cond}"})
        if op.phase == "U PRODAJI":
            items.append({"date": None, "kind": "buy", "event": label, "text": f"Odmah: kupi {pos.qty} kom{cond} (u prodaji)"})
        for row in [] if pos.conditional else (op.advice or {}).get("ladder", []):
            items.append({"date": row.get("iso"), "kind": "sell", "event": label, "text": f"Oglas {row['price']:.0f} € – {row['label']}"})
        items.append({"date": e.date.isoformat(), "kind": "event", "event": label, "text": "Događaj"})
        if op.best and op.best.payout and "nakon" in op.best.payout.lower():
            items.append({"date": add_days(e.date, 7).isoformat(), "kind": "payout", "event": label, "text": f"Očekivana isplata ({op.best.name})"})
    items.sort(key=lambda x: (x["date"] or "0000", x["event"]))
    return items


def _notes(plan: Plan, budget: float) -> list[str]:
    notes: list[str] = []
    sim = plan.simulation
    if plan.positions:
        notes.append(
            f"Plan ulaže {plan.invested:.0f} € od {budget:.0f} € u {len(plan.positions)} "
            f"{hr_plural(len(plan.positions), 'događaj', 'događaja')}; "
            f"očekivana dobit ~{plan.expected_profit:.0f} € (raspon 90 % simulacija: {sim.get('p05', 0):.0f} do {sim.get('p95', 0):.0f} €, "
            f"vjerojatnost gubitka {sim.get('prob_loss', 0) * 100:.0f} %)."
        )
        notes.append("Najviše 25 % budžeta po događaju i ulaznice u parovima – tako jedan promašaj ne pojede cijeli kapital.")
    else:
        notes.append("Trenutno nema događaja s poznatom nominalnom cijenom i dovoljnim očekivanim povratom (KUPI/RAZMOTRI).")
    if plan.conditional:
        notes.append(
            f"Uvjetno: {len(plan.conditional)} događaja isplati se SAMO ako nominalnu cijenu dobiješ najviše do granice "
            "(npr. najjeftinija kategorija u presaleu) – prvo provjeri cijenu kod prodavača."
        )
    if budget - plan.invested > 0 and plan.positions:
        notes.append(f"Ostatak {budget - plan.invested:.0f} € drži kao rezervu za nove najave i presaleove.")
    notes.append("Procjene su heuristika (vidi docs/MODEL.md); nakon svake prodaje upiši rezultat u Moje prodaje radi kalibracije.")
    return notes


def describe_calendar(items: list[dict], limit: int = 20) -> list[str]:
    out = []
    for it in items[:limit]:
        when = fmt_date(datetime.fromisoformat(it["date"])) if it["date"] else "odmah"
        out.append(f"{when:>12}  {it['event']}: {it['text']}")
    return out
