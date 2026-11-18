"""Dnevnik kupnji i prodaja: evidencija, statistika i kalibracija modela stvarnim rezultatima.

Podaci se spremaju lokalno u JSON (zadano ~/.karte/dnevnik.json, ili KARTE_DATA_DIR).
"""

from __future__ import annotations

import csv
import dataclasses
import io
import json
import statistics
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

from karte.knowledge import ModelConfig
from karte.util import parse_datetime, parse_float, parse_int

STATUSES = {
    "kupljeno": "Kupljeno",
    "oglaseno": "Oglašeno",
    "prodano": "Prodano",
    "djelomicno": "Djelomično prodano",
    "neprodano": "Neprodano (gubitak)",
    "iskoristeno": "Iskorišteno (išao sam)",
}


@dataclass
class Trade:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    artist: str = ""
    event_name: str = ""
    venue: str = ""
    city: str = ""
    country: str = "HR"
    event_date: str = ""
    category: str = ""
    qty: int = 2
    face_value: float | None = None
    buy_price: float = 0.0  # plaćeno po ulaznici, s naknadama (EUR)
    buy_date: str = ""
    platform: str = "viagogo"
    list_price: float | None = None  # oglasna cijena po ulaznici
    sold_qty: int = 0
    sell_net: float | None = None  # stvarno primljeno po ulaznici nakon naknada (EUR)
    sell_date: str = ""
    status: str = "kupljeno"
    predicted_multiplier: float | None = None  # što je model procijenio pri kupnji
    notes: str = ""
    created: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @classmethod
    def from_dict(cls, d: dict) -> "Trade":
        names = {f.name for f in dataclasses.fields(cls)}
        t = cls(**{k: v for k, v in d.items() if k in names and v not in (None, "")})
        for k in ("face_value", "list_price", "sell_net", "predicted_multiplier"):
            setattr(t, k, parse_float(getattr(t, k)))
        t.buy_price = parse_float(t.buy_price) or 0.0
        t.qty = parse_int(t.qty) or 0
        t.sold_qty = parse_int(t.sold_qty) or 0
        if t.status not in STATUSES:
            t.status = "kupljeno"
        if t.status == "prodano":
            t.sold_qty = t.sold_qty or t.qty
        t.sold_qty = min(t.sold_qty, t.qty)
        t.country = (t.country or "HR").upper()
        return t

    # ---------------------------------------------------------- izračuni
    @property
    def cost_total(self) -> float:
        return self.buy_price * self.qty

    @property
    def revenue(self) -> float:
        return (self.sell_net or 0.0) * self.sold_qty

    @property
    def closed_cost(self) -> float:
        """Trošak ulaznica čiji je ishod poznat (prodane; kod 'neprodano' i one koje su propale)."""
        if self.status in ("prodano", "djelomicno"):
            return self.buy_price * self.sold_qty
        if self.status == "neprodano":
            return self.buy_price * self.qty
        return 0.0

    @property
    def realized_profit(self) -> float | None:
        """Ostvarena dobit na zatvorenom dijelu; None ako ishod još nije poznat (kupljeno/oglašeno/iskorišteno)."""
        if self.status not in ("prodano", "djelomicno", "neprodano"):
            return None
        return self.revenue - self.closed_cost

    @property
    def open_capital(self) -> float:
        if self.status in ("kupljeno", "oglaseno"):
            return self.cost_total
        if self.status == "djelomicno":
            return self.buy_price * max(self.qty - self.sold_qty, 0)
        return 0.0

    @property
    def roi(self) -> float | None:
        p = self.realized_profit
        if p is None or not self.closed_cost:
            return None
        return p / self.closed_cost

    @property
    def realized_multiplier(self) -> float | None:
        """Ostvarena oglasna cijena / nominalna (ako nema oglasne, procjena iz neto isplate uz 15 % naknade)."""
        if not self.face_value or self.status not in ("prodano", "djelomicno"):
            return None
        gross = self.list_price or ((self.sell_net or 0) / 0.85 if self.sell_net else None)
        return gross / self.face_value if gross else None

    @property
    def days_before_event(self) -> int | None:
        ev, sold = parse_datetime(self.event_date), parse_datetime(self.sell_date)
        if not ev or not sold:
            return None
        return (ev.date() - sold.date()).days

    def to_row(self) -> dict:
        d = asdict(self)
        d.update(
            status_label=STATUSES.get(self.status, self.status),
            cost_total=round(self.cost_total, 2),
            revenue=round(self.revenue, 2),
            realized_profit=None if self.realized_profit is None else round(self.realized_profit, 2),
            roi=None if self.roi is None else round(self.roi, 4),
            open_capital=round(self.open_capital, 2),
            realized_multiplier=None if self.realized_multiplier is None else round(self.realized_multiplier, 3),
            days_before_event=self.days_before_event,
        )
        return d


class Journal:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> list[Trade]:
        if not self.path.is_file():
            return []
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        return [Trade.from_dict(d) for d in raw.get("trades", [])]

    def _save(self, trades: list[Trade]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "trades": [asdict(t) for t in trades]}, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def list(self) -> list[Trade]:
        return sorted(self._load(), key=lambda t: (t.event_date or "", t.created), reverse=True)

    def upsert(self, data: dict) -> Trade:
        trades = self._load()
        tid = data.get("id")
        for i, t in enumerate(trades):
            if tid and t.id == tid:
                merged = {**asdict(t), **data}
                trades[i] = Trade.from_dict(merged)
                self._save(trades)
                return trades[i]
        trade = Trade.from_dict({k: v for k, v in data.items() if k != "id"})
        trades.append(trade)
        self._save(trades)
        return trade

    def delete(self, trade_id: str) -> bool:
        trades = self._load()
        kept = [t for t in trades if t.id != trade_id]
        if len(kept) == len(trades):
            return False
        self._save(kept)
        return True

    # ------------------------------------------------------- CSV
    def export_csv(self) -> str:
        buf = io.StringIO()
        names = [f.name for f in dataclasses.fields(Trade)]
        writer = csv.DictWriter(buf, fieldnames=names)
        writer.writeheader()
        for t in self.list():
            writer.writerow(asdict(t))
        return buf.getvalue()

    def import_csv(self, text: str) -> int:
        reader = csv.DictReader(io.StringIO(text.lstrip("﻿")))
        count = 0
        for row in reader:
            if not (row.get("artist") or "").strip():
                continue
            row = {k: v for k, v in row.items() if k}
            row.pop("id", None)
            self.upsert(row)
            count += 1
        return count

    # ------------------------------------------------------- statistika
    def stats(self, config: ModelConfig | None = None) -> dict:
        trades = self.list()
        closed = [t for t in trades if t.realized_profit is not None]
        profit = sum(t.realized_profit for t in closed)
        closed_cost = sum(t.closed_cost for t in closed)
        by_platform: dict[str, dict] = {}
        for t in closed:
            b = by_platform.setdefault(t.platform or "—", {"platform": t.platform or "—", "count": 0, "profit": 0.0, "cost": 0.0, "days": []})
            b["count"] += 1
            b["profit"] += t.realized_profit
            b["cost"] += t.closed_cost
            if t.days_before_event is not None:
                b["days"].append(t.days_before_event)
        platforms = []
        for b in by_platform.values():
            platforms.append({
                "platform": b["platform"],
                "count": b["count"],
                "profit": round(b["profit"], 2),
                "roi": round(b["profit"] / b["cost"], 4) if b["cost"] else None,
                "avg_days_before_event": round(statistics.mean(b["days"]), 1) if b["days"] else None,
            })
        platforms.sort(key=lambda r: r["profit"], reverse=True)
        days = [t.days_before_event for t in closed if t.days_before_event is not None]
        wins = [t for t in closed if t.realized_profit > 0]
        return {
            "count": len(trades),
            "closed": len(closed),
            "invested_total": round(sum(t.cost_total for t in trades if t.status != "iskoristeno"), 2),
            "revenue": round(sum(t.revenue for t in trades), 2),
            "profit": round(profit, 2),
            "roi": round(profit / closed_cost, 4) if closed_cost else None,
            "open_capital": round(sum(t.open_capital for t in trades), 2),
            "win_rate": round(len(wins) / len(closed), 3) if closed else None,
            "avg_days_before_event": round(statistics.mean(days), 1) if days else None,
            "platforms": platforms,
            "calibration": calibration(trades, config),
        }


def calibration(trades: list[Trade], config: ModelConfig | None = None) -> dict:
    """Usporedi ostvarene multiplikatore s procjenom modela i predloži novi demand_slope."""
    pairs = [
        (t.realized_multiplier, t.predicted_multiplier)
        for t in trades
        if t.realized_multiplier and t.predicted_multiplier and t.predicted_multiplier > 0.9
    ]
    realized = [t.realized_multiplier for t in trades if t.realized_multiplier]
    out: dict = {
        "samples": len(pairs),
        "avg_realized_multiplier": round(statistics.mean(realized), 3) if realized else None,
    }
    if not pairs:
        out["message"] = (
            "Za kalibraciju upiši nominalnu cijenu, prodajnu cijenu i procjenu modela (dodaj transakciju iz rezultata pretrage "
            "ili kalkulatora). Nakon 5–10 prodaja dobit ćeš prijedlog podešavanja modela."
        )
        return out
    base = (config or ModelConfig.load()).get("resale", "base_multiplier", 0.8)
    slope = (config or ModelConfig.load()).get("resale", "demand_slope", 1.7)
    ratios = [(r - base) / (p - base) for r, p in pairs if p - base > 0.05]
    accuracy = statistics.mean(r / p for r, p in pairs)
    out["avg_ratio"] = round(accuracy, 3)
    if ratios:
        factor = max(0.3, min(2.5, statistics.median(ratios)))
        out["suggested_demand_slope"] = round(slope * factor, 2)
        out["current_demand_slope"] = slope
    direction = "precjenjuje" if accuracy < 0.97 else ("podcjenjuje" if accuracy > 1.03 else "pogađa")
    pct = abs(1 - accuracy) * 100
    msg = f"Uzorak od {len(pairs)} prodaj{'e' if len(pairs) == 1 else 'a'}: model {direction} ostvarenu cijenu"
    msg += f" za ~{pct:.0f} %." if direction != "pogađa" else " (odstupanje < 3 %)."
    if ratios and direction != "pogađa":
        msg += f" Prijedlog: u vlastitom model.toml postavi [resale] demand_slope = {out['suggested_demand_slope']} (sada {slope})."
    if len(pairs) < 5:
        msg += " Uzorak je još mali – oprezno."
    out["message"] = msg
    return out


def default_path(data_dir: str | Path | None = None) -> Path:
    return Path(data_dir or (Path.home() / ".karte")) / "dnevnik.json"


def today_iso() -> str:
    return date.today().isoformat()
