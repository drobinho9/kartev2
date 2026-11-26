"""Paketi: nekoliko gotovih prijedloga „kupi ovo, prodaj ovdje” s očekivanom zaradom i koracima.

Ulaz su procjene iz `run_scan` (svi događaji: koncerti, sport, ostalo). Paket je skup ulaznica koje bi kupio
odjednom, s ukupnim ulogom, očekivanom dobiti (uz vjerojatnost prodaje), rasponom ishoda iz simulacije i
jednostavnim koracima: kada i gdje kupiti, do koje cijene, gdje i po kojoj cijeni prodati.

Paketi su alternative (odaberi jedan) i mogu dijeliti iste događaje:
  - Siguran start      – mali ulog, niži rizik, ulaznice koje se lako prenose
  - Najveća zarada     – cijeli budžet na najbolji očekivani povrat (najviše 25 % po događaju)
  - Blizu kuće         – samo Hrvatska i susjedi (lakši prijenos, domaći oglasnici)
  - Sport              – sportski događaji na kojima je preprodaja dopuštena
Stavke bez javne nominalne cijene ulaze kao UVJETNE: „kupi samo ako je cijena ≤ X”.
"""

from __future__ import annotations

import dataclasses
import math
from collections import Counter
from datetime import datetime

from karte import knowledge
from karte.advisor import build_advice
from karte.knowledge import ModelConfig
from karte.models import Opportunity
from karte.portfolio import Position, simulate
from karte.scoring import Evaluator
from karte.util import fmt_date, fmt_datetime, fmt_eur, hr_plural

NEAR_HOME = {"HR": ["HR", "SI", "BA", "RS", "ME", "MK", "HU", "AT"]}
FORBIDDEN = ("ZAKONSKI OGRANIČENO", "UVJETI ZABRANJUJU")
MIN_DAYS_TO_EVENT = 7


@dataclasses.dataclass
class Candidate:
    op: Opportunity  # izvorna procjena (za prikaz i poveznice)
    calc: Opportunity  # procjena po kojoj računamo (za uvjetne: uz pretpostavljenu nominalnu = max_buy)
    conditional: bool

    @property
    def unit_cost(self) -> float:
        return float(self.calc.buy_cost or 0)

    @property
    def risk(self) -> float:
        return self.op.risk if not self.conditional else max(self.op.risk, self.calc.risk)


def _candidates(ops: list[Opportunity], evaluator: Evaluator | None, cfg: ModelConfig) -> list[Candidate]:
    out: list[Candidate] = []
    for op in ops:
        if op.days_to_event < MIN_DAYS_TO_EVENT:
            continue  # premalo vremena za kupnju i preprodaju
        if op.verdict in ("KUPI", "RAZMOTRI", "RIZIČNO") and op.best and op.buy_cost and (op.expected_value or 0) > 0:
            out.append(Candidate(op, op, False))
        elif op.verdict == "PROVJERI CIJENU" and op.max_buy and evaluator is not None:
            trial = evaluator.evaluate(dataclasses.replace(op.event, face_min=op.max_buy, face_max=op.max_buy, currency="EUR"))
            if trial.best and trial.buy_cost and (trial.expected_value or 0) > 0:
                trial.advice = build_advice(trial, cfg)
                out.append(Candidate(op, trial, True))
    return out


def _even(qty: int) -> int:
    return qty - 1 if qty >= 2 and qty % 2 else qty


def _allocate(cands: list[Candidate], budget: float, per_event: float, max_events: int, max_qty: int, cfg: ModelConfig):
    left = budget
    chosen: list[tuple[Candidate, Position]] = []
    for c in cands:
        if len(chosen) >= max_events or left <= 0:
            break
        if c.unit_cost <= 0:
            continue
        wanted = min(c.calc.suggested_qty or cfg.get("sizing", "default_qty", 2), max_qty)
        affordable = math.floor(min(per_event, left) / c.unit_cost)
        qty = _even(min(wanted, affordable, c.op.event.ticket_limit or wanted))
        if qty < 2:
            continue  # parovi se prodaju najbrže – pojedinačna ulaznica ne ide u paket
        best = c.calc.best
        salvage = 0.0 if c.calc.event.personalized else cfg.get("sell", "salvage_ratio", 0.6) * (c.calc.face_ref or 0)
        pos = Position(op=c.calc, qty=qty, unit_cost=c.unit_cost, net=best.net_payout, salvage=salvage, p_sell=best.p_sell,
                       platform=best.name, conditional=c.conditional, assumed_face=c.op.max_buy if c.conditional else None)
        chosen.append((c, pos))
        left -= pos.cost
    return chosen


# ---------------------------------------------------------------------- koraci

def _when(op: Opportunity) -> str:
    e = op.event
    if op.phase == "NAJAVA":
        parts = [f"presale „{p.name}” {fmt_datetime(p.start)}" for p in sorted(e.presales, key=lambda p: p.start or e.date) if p.start]
        if e.public_onsale:
            parts.append(f"javna prodaja {fmt_datetime(e.public_onsale)}")
        return "Kada: " + ", ".join(parts) + " – u virtualni red uđi 10–15 min ranije." if parts else "Kada: čim počne prodaja."
    if op.phase in ("RASPRODANO", "NIJE U PRODAJI"):
        return "Kada: primarna prodaja je zatvorena – prati dodatne ulaznice kod službenog prodavača."
    return "Kada: odmah – ulaznice su u prodaji, a najjeftinije kategorije nestaju prve."


def _where(op: Opportunity) -> str:
    e = op.event
    vendor = knowledge.vendor_info(e.primary_vendor)
    if vendor:
        domain = knowledge.vendor_domain(e.primary_vendor, e.country)
        return f"Gdje: {vendor.get('name')}" + (f" ({domain})" if domain else "") + " – službeni prodavač."
    names = [v.get("name", k) for k, v in knowledge.vendors_for_country(e.country)[:3]]
    tail = f" (u toj državi najčešće: {', '.join(names)})" if names else ""
    return f"Gdje: službeni prodavač za ovaj događaj{tail} – provjeri gumbom „Provjeri cijene”."


def buy_steps(c: Candidate, pos: Position) -> list[str]:
    op, e = c.op, c.op.event
    steps = [_when(op), _where(op), f"Što: {pos.qty} kom ({pos.qty // 2} {hr_plural(pos.qty // 2, 'par', 'para', 'parova')}) "
             "najjeftinije kategorije s dobrim pogledom (parter/stajanje)."]
    if c.conditional:
        steps.append(
            f"Cijena: kupi SAMO ako je nominalna cijena ≤ {fmt_eur(op.max_buy)} po ulaznici (s naknadama ~{fmt_eur(pos.unit_cost)}); "
            f"iznad ~{fmt_eur(op.breakeven_buy)} očekuješ gubitak."
        )
    else:
        steps.append(f"Cijena: nominalna ~{fmt_eur(op.face_ref)}, s naknadama ~{fmt_eur(pos.unit_cost)} po ulaznici.")
    checks = []
    if e.personalized is None:
        checks.append("da ulaznice nisu na ime")
    checks.append(f"limit po kupcu ({e.ticket_limit} kom)" if e.ticket_limit else "limit po kupcu")
    steps.append("Prije plaćanja provjeri " + " i ".join(checks) + "; kupuj ručno, s jednog računa.")
    return steps


def sell_steps(c: Candidate, pos: Position) -> list[str]:
    best = c.calc.best
    steps = [f"Gdje: {best.name} – oglasi ~{fmt_eur(best.list_price)} po ulaznici, tebi neto ~{fmt_eur(best.net_payout)}."]
    backups = [o.name for o in c.calc.platforms[1:3]]
    if backups:
        steps.append("Rezerva: " + ", ".join(backups) + ".")
    ladder = (c.calc.advice or {}).get("ladder", [])
    if ladder:
        steps.append("Cjenik: " + "; ".join(f"{row['label'].split(' (')[0].split(' – ')[0]} → {fmt_eur(row['price'])}" for row in ladder[:4]) + ".")
    steps.append(f"Ne spuštaj ispod {fmt_eur(best.break_even_price)} (break-even) prije zadnjeg tjedna.")
    if "nakon" in (best.payout or "").lower():
        steps.append(best.payout if best.payout.lower().startswith("isplata") else f"Isplata: {best.payout}")
    return steps


def _item_dict(c: Candidate, pos: Position) -> dict:
    from karte.report import location
    from karte.service import opportunity_dict

    op, e = c.op, c.op.event
    best = c.calc.best
    links = (op.advice or {}).get("links") or []
    return {
        "event_id": e.id,
        "name": e.name,
        "artist": e.artist,
        "date": e.date.isoformat(),
        "location": location(e),
        "country": e.country,
        "segment": e.segment,
        "verdict": op.verdict,
        "conditional": c.conditional,
        "qty": pos.qty,
        "face": op.face_ref if not c.conditional else None,
        "max_face": op.max_buy if c.conditional else op.face_ref,
        "breakeven_face": op.breakeven_buy if c.conditional else None,
        "unit_cost": round(pos.unit_cost, 2),
        "cost": round(pos.cost, 2),
        "platform": best.name,
        "list_price": round(best.list_price, 2),
        "net": round(best.net_payout, 2),
        "p_sell": round(best.p_sell, 3),
        "profit_if_sold": round((best.net_payout - pos.unit_cost) * pos.qty, 2),
        "expected_profit": round(pos.expected_profit, 2),
        "roi": round(pos.roi, 4),
        "risk": round(c.risk, 3),
        "demand": round(op.demand.score, 3),
        "buy": buy_steps(c, pos),
        "sell": sell_steps(c, pos),
        "risks": [f for f in op.risk_flags if not f.startswith("Malo ulaznih")][:3],
        "links": links[:8],
        "op": opportunity_dict(op),
    }


# ---------------------------------------------------------------------- paketi

PACKAGES = [
    {
        "key": "siguran",
        "title": "Mali ulog za početak",
        "icon": "🌱",
        "subtitle": "Za prvi put: samo događaji s poznatom cijenom, jakom potražnjom i nižim rizikom, ulaznice koje se lako prenose.",
        "budget_share": 0.4, "per_event_share": 0.2, "max_events": 3, "max_qty": 2,
    },
    {
        "key": "zarada",
        "title": "Najveća očekivana zarada",
        "icon": "📈",
        "subtitle": "Cijeli budžet na najbolji očekivani povrat, najviše 25 % po događaju.",
        "budget_share": 1.0, "per_event_share": 0.25, "max_events": 6, "max_qty": 4,
    },
    {
        "key": "blizu",
        "title": "Blizu kuće",
        "icon": "🏠",
        "subtitle": "Samo Hrvatska i susjedne države: lakši prijenos ulaznica, domaći kupci i oglasnici.",
        "budget_share": 0.7, "per_event_share": 0.25, "max_events": 4, "max_qty": 4,
    },
    {
        "key": "sport",
        "title": "Sport",
        "icon": "⚽",
        "subtitle": "Sportski događaji na kojima je preprodaja dopuštena (zakon i uvjeti organizatora).",
        "budget_share": 0.6, "per_event_share": 0.25, "max_events": 4, "max_qty": 4,
    },
    {
        "key": "rizik",
        "title": "Nogomet – visok rizik",
        "icon": "⚠️",
        "subtitle": "Utakmice na kojima preprodaju zabranjuju uvjeti kluba/UEFA-e (ne zakon). Zarada je računata uz šansu "
                    "poništenja ulaznice i kaznu platforme – mali ulog, samo novac koji možeš izgubiti.",
        "budget_share": 0.2, "per_event_share": 0.1, "max_events": 3, "max_qty": 2,
    },
]


def _pick(key: str, cands: list[Candidate], seller_country: str) -> list[Candidate]:
    # stavke s poznatom nominalnom cijenom uvijek ispred uvjetnih (manja nesigurnost), zatim po očekivanom povratu
    by_return = lambda c: (c.conditional, -(c.calc.roi or 0))  # noqa: E731
    if key == "rizik":
        return sorted((c for c in cands if c.op.verdict == "RIZIČNO"), key=by_return)
    cands = [c for c in cands if c.op.verdict != "RIZIČNO"]  # rizične stavke samo u svom paketu
    if key == "siguran":
        safe = [c for c in cands if not c.conditional and c.risk <= 0.45 and c.calc.best.p_sell >= 0.6
                and c.op.event.personalized is not True and c.op.demand.score >= 0.6]
        return sorted(safe, key=lambda c: (c.risk, -c.calc.best.p_sell))
    if key == "zarada":
        return sorted(cands, key=by_return)
    if key == "blizu":
        near = set(NEAR_HOME.get(seller_country, [seller_country]))
        return sorted((c for c in cands if (c.op.event.country or "").upper() in near), key=by_return)
    if key == "sport":
        return sorted((c for c in cands if c.op.event.segment == "sport"), key=by_return)
    return []


def _risk_label(positions: list[tuple[Candidate, Position]]) -> str:
    cost = sum(p.cost for _, p in positions) or 1.0
    avg = sum(c.risk * p.cost for c, p in positions) / cost
    return "nizak" if avg < 0.35 else ("srednji" if avg < 0.55 else "visok")


def _steps(chosen: list[tuple[Candidate, Position]]) -> list[str]:
    tickets = sum(p.qty for _, p in chosen)
    cost = sum(p.cost for _, p in chosen)
    platforms = [name for name, _ in Counter(p.platform for _, p in chosen).most_common(3)]
    conditional = any(c.conditional for c, _ in chosen)
    steps = [
        "Za svaku stavku otvori „Provjeri cijene” i potvrdi da su ulaznice još u prodaji"
        + (" i da je službena (nominalna) cijena ispod granice „kupi do”." if conditional else "."),
        f"Kupi ručno, svojim računom i unutar limita po kupcu – ukupno {tickets} {hr_plural(tickets, 'ulaznica', 'ulaznice', 'ulaznica')} za ~{fmt_eur(cost)}.",
        f"Odmah po kupnji oglasi ({', '.join(platforms)}) 1–3 % ispod najnižeg oglasa iste kategorije.",
        "Spuštaj cijenu po cjeniku stavke; prodane ulaznice prenesi samo službenim prijenosom i povuci ostale oglase.",
        "Upiši kupnju i prodaju u „Moje prodaje” – aplikacija tako uči i procjene postaju točnije.",
    ]
    return steps


def build_packages(ops: list[Opportunity], budget: float, evaluator: Evaluator | None = None,
                   seller_country: str = "HR", simulations: int = 2000) -> dict:
    cfg = evaluator.cfg if evaluator else ModelConfig.load()
    cands = _candidates(ops, evaluator, cfg)
    packages: list[dict] = []
    seen: set[tuple] = set()
    for spec in PACKAGES:
        picked = _pick(spec["key"], cands, seller_country)
        chosen = _allocate(picked, budget * spec["budget_share"], budget * spec["per_event_share"],
                           spec["max_events"], spec["max_qty"], cfg)
        if not chosen:
            continue
        signature = tuple(sorted((c.op.event.id, p.qty) for c, p in chosen))
        if signature in seen:
            continue  # isti sastav kao prethodni paket – ne ponavljaj
        seen.add(signature)
        positions = [p for _, p in chosen]
        sim = simulate(positions, simulations)
        packages.append({
            "key": spec["key"],
            "title": spec["title"],
            "icon": spec["icon"],
            "subtitle": spec["subtitle"],
            "risk_label": _risk_label(chosen),
            "events": len(chosen),
            "tickets": sum(p.qty for p in positions),
            "cost": round(sum(p.cost for p in positions), 2),
            "expected_profit": round(sum(p.expected_profit for p in positions), 2),
            "profit_if_sold": round(sum((p.net - p.unit_cost) * p.qty for p in positions), 2),
            "conditional": any(c.conditional for c, _ in chosen),
            "simulation": {k: sim.get(k) for k in ("runs", "mean", "p05", "p50", "p95", "prob_loss")},
            "items": [_item_dict(c, p) for c, p in chosen],
            "steps": _steps(chosen),
        })

    sport_ops = [op for op in ops if op.event.segment == "sport"]
    from karte import football as fb

    market_rows = []
    for op in sorted(sport_ops, key=lambda o: o.event.date):
        if op.event.secondary is None or op.event.sport != "football":
            continue
        status = "zabranjeno" if op.verdict in FORBIDDEN else "dopusteno"
        if op.legal.sport_rule in ("official_only",):
            status = "sluzbeno"
        info = fb.market_info(op.event, op, status)
        if info:
            market_rows.append({"match": op.event.name, "date": op.event.date.isoformat(), "location": _loc(op),
                                "competition": op.event.league or "", "verdict": op.verdict, "url": op.event.url, **info})
    football = {
        "total": len(sport_ops),
        "forbidden": sum(1 for op in sport_ops if op.verdict in FORBIDDEN),
        "allowed": sum(1 for op in sport_ops if op.verdict not in FORBIDDEN),
        "market": market_rows[:10],
    }
    watch = sorted(
        (op for op in ops if op.verdict in ("NEMA CIJENE", "RASPRODANO") and op.event.segment != "sport" and op.demand.score >= 0.6),
        key=lambda op: -op.demand.score,
    )[:8]
    notes: list[str] = []
    if not packages:
        notes.append(
            "Trenutno nema događaja s poznatom (ili procijenjenom) cijenom i pozitivnom očekivanom zaradom. "
            "Dodaj događaje s cijenama (Kalkulator, CSV, gumb „karte: spremi”) ili ključ za žive izvore (npr. SERPAPI_KEY)."
        )
    if any(p["conditional"] for p in packages):
        notes.append("Stavke označene UVJETNO nemaju javnu nominalnu cijenu: zarada vrijedi samo ako ulaznicu kupiš najviše po cijeni „kupi do”.")
    if football["forbidden"]:
        n = football["forbidden"]
        notes.append(
            f"Nogomet: {n} {hr_plural(n, 'utakmica', 'utakmice', 'utakmica')} nije u paketima – u Europi je preprodaja radi zarade "
            "zabranjena zakonom ili uvjetima kluba/UEFA-e (ulaznice na ime uz osobnu, poništavanje)"
            + (", iako se na viagogu i StubHubu nude (vidi „Nogomet na preprodaji”)." if football["market"] else ".")
            + " Kako kupiti za sebe: kartica Nogomet."
        )
    notes.append("Brojke su procjene modela (nisu jamstvo) – prije kupnje uvijek provjeri aktualne cijene i uvjete prodaje.")
    return {
        "budget": budget,
        "packages": packages,
        "football": football,
        "watch": [
            {"artist": op.event.artist, "location": _loc(op), "date": op.event.date.isoformat(), "verdict": op.verdict,
             "demand": round(op.demand.score, 3), "url": op.event.url}
            for op in watch
        ],
        "notes": notes,
    }


def _loc(op: Opportunity) -> str:
    from karte.report import location

    return location(op.event)


def describe(result: dict) -> list[str]:
    """Tekstualni prikaz paketa (za naredbeni redak)."""
    lines: list[str] = []
    for i, p in enumerate(result["packages"], 1):
        sim = p["simulation"]
        lines.append("=" * 100)
        lines.append(f"PAKET {i}: {p['title'].upper()} {p['icon']}  ·  rizik: {p['risk_label']}")
        lines.append(f"  {p['subtitle']}")
        lines.append(
            f"  Ulog {fmt_eur(p['cost'])} · {p['tickets']} {hr_plural(p['tickets'], 'ulaznica', 'ulaznice', 'ulaznica')} · očekivana dobit {fmt_eur(p['expected_profit'])} "
            f"(ako se sve proda {fmt_eur(p['profit_if_sold'])}) · 90 % ishoda {fmt_eur(sim.get('p05'))} do {fmt_eur(sim.get('p95'))} · "
            f"šansa gubitka {round((sim.get('prob_loss') or 0) * 100)} %"
        )
        for it in p["items"]:
            cond = f"  UVJETNO: kupi do {fmt_eur(it['max_face'])}" if it["conditional"] else ""
            lines.append(
                f"   • {fmt_date(datetime.fromisoformat(it['date']))} {it['artist'][:30]:<30} {it['location'][:34]:<34} "
                f"{it['qty']} kom · trošak {fmt_eur(it['cost'])} · prodaj na {it['platform']} ~{fmt_eur(it['list_price'])} · "
                f"oček. dobit {fmt_eur(it['expected_profit'])}{cond}"
            )
            for s in it["buy"]:
                lines.append(f"       kupnja  – {s}")
            for s in it["sell"]:
                lines.append(f"       prodaja – {s}")
        lines.append("  Koraci:")
        for n, s in enumerate(p["steps"], 1):
            lines.append(f"   {n}. {s}")
    market = (result.get("football") or {}).get("market") or []
    if market:
        lines.append("=" * 100)
        lines.append("NOGOMET NA PREPRODAJI (zabranjene nisu u paketima; RIZIČNO samo u paketu „Nogomet – visok rizik”):")
        for m in market:
            face = (f" · nominalno ~{fmt_eur(m['face_min'])}–{fmt_eur(m['face_max'])}" if m.get("face_min") else "")
            spec = " · spekulativni oglasi" if m.get("speculative") else ""
            lines.append(f"   {fmt_date(datetime.fromisoformat(m['date']))} {m['match'][:40]:<40} {m['source']}: od {fmt_eur(m['lowest'])}"
                         f" ({m.get('count') or '?'} oglasa, {m.get('observed') or '?'}){face}{spec}")
    if result.get("watch"):
        lines.append("=" * 100)
        lines.append("PRATI (jaka potražnja, cijena još nije poznata):")
        for w in result["watch"]:
            lines.append(f"   {fmt_date(datetime.fromisoformat(w['date']))} {w['artist'][:30]:<30} {w['location'][:40]}  {w['verdict']}")
    return lines
