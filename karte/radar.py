"""Radar: rano upozorenje na nove događaje koji bi se mogli skupo preprodavati – s obavijestima na Telegram.

Svako pokretanje (npr. svaka 3 sata u GitHub Actions):
  1. skupi događaje (snimka/živi izvori, raspored utakmica, cijene s preprodaje) i najave iz RSS izvora,
  2. svakom da HYPE SCORE 0–100 (hoće li ulaznice poskupjeti) s objašnjenjem „zašto”,
  3. usporedi sa stanjem prošlog pokretanja (radar_stanje.json) i javi samo ono što je NOVO ili se PROMIJENILO:
     novi događaj iznad praga, skok ocjene, presale/prodaja za < 48 h, nova preporuka KUPI, skok cijene na preprodaji,
  4. zapiše povijest ocjena i cijena po događaju – iz toga se kasnije kalibrira model (ocjena pri najavi → stvarna cijena).

Hype score je namjerno objašnjiv: zbroj signala s težinama (potražnja iz modela, rijetkost – prvi dolazak, oproštaj,
dodatni datum –, rast interesa na Wikipediji, odnos cijene na preprodaji i nominalne, skora prodaja, presuda modela).
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from karte.models import Opportunity
from karte.util import clamp, fmt_datetime, fmt_eur, normalize, utcnow

STATE_FILE = "radar_stanje.json"
HISTORY_LIMIT = 30
FIRST_RUN_TOP = 5  # prvo pokretanje: ne zatrpavaj – pošalji samo najboljih N
SKIP_VERDICTS = {"ZAKONSKI OGRANIČENO", "UVJETI ZABRANJUJU", "OTKAZANO"}
TAG_REASONS = {
    "first_visit": ("prvi put u državi", 10),
    "farewell": ("oproštajna turneja", 10),
    "reunion": ("povratak benda", 10),
    "added_date": ("dodatni datum (prvi rasprodan)", 12),
    "derby": ("derbi", 8),
    "final": ("finale", 10),
    "big_match": ("velika utakmica", 5),
    "regional_star": ("regionalna zvijezda", 4),
}
HOT_WORDS = re.compile(
    r"rasprodan|sold.?out|dodatn\w* (koncert|datum)|extra (date|show)|second (date|show)|novi datum|"
    r"zbog velikog interesa|due to (huge|overwhelming) demand|reunion|oproštaj|farewell|prvi put",
    re.I,
)


@dataclass
class Alert:
    key: str
    kind: str  # NOVO | RASTE | PRODAJA USKORO | KUPI | CIJENA | NAJAVA
    score: int
    title: str
    lines: list[str] = field(default_factory=list)
    url: str | None = None

    def text(self) -> str:
        esc = lambda s: str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")  # noqa: E731
        head = f"★ {self.score}/100 · {self.kind}\n<b>{esc(self.title)}</b>"
        body = "\n".join(esc(x) for x in self.lines if x)
        link = f'\n<a href="{esc(self.url)}">Otvori ↗</a>' if self.url else ""
        return f"{head}\n{body}{link}"

    def as_dict(self) -> dict:
        return {"key": self.key, "kind": self.kind, "score": self.score, "title": self.title, "lines": self.lines, "url": self.url}


# ---------------------------------------------------------------------- hype score

def event_key(op: Opportunity) -> str:
    e = op.event
    return f"{normalize(e.artist)}|{e.date.date().isoformat()}|{normalize(e.city)}"


def _secondary_eur(op: Opportunity) -> float | None:
    sec = op.event.secondary
    if sec is None or not sec.lowest:
        return None
    from karte.knowledge import ModelConfig

    return ModelConfig.load().to_eur(sec.lowest, sec.currency)


def hype(op: Opportunity) -> tuple[int, list[str]]:
    """0–100: koliko je vjerojatno da će se ulaznice preprodavati iznad nominalne – i zašto."""
    if op.verdict in SKIP_VERDICTS:
        return 0, ["preprodaja nije dopuštena ili je događaj otkazan"]
    e = op.event
    reasons: list[str] = []
    score = op.demand.score * 55  # potražnja iz modela: popularnost, rijetkost, veličina dvorane, turneja
    reasons.append(f"potražnja {op.demand.score * 100:.0f}/100")
    for tag in e.tags:
        if tag in TAG_REASONS:
            label, pts = TAG_REASONS[tag]
            score += pts
            reasons.append(label)
    if e.artist_trend and e.artist_trend >= 1.4:
        score += min(12, (e.artist_trend - 1.0) * 6)
        reasons.append("interes na Wikipediji ×" + f"{e.artist_trend:.1f}".replace(".", ","))
    sec = _secondary_eur(op)
    base = op.face_ref or op.max_buy
    speculative = "spekulativ" in ((e.secondary.source if e.secondary else "") or "")
    if sec and speculative:
        score += 3
        reasons.append(f"spekulativni oglasi od {fmt_eur(sec)} (prodaja još nije počela)")
    elif sec and base:
        ratio = sec / base
        if ratio >= 1.5:
            score += min(15, (ratio - 1.0) * 8)
            mult = f"{ratio:.1f}".replace(".", ",")
            reasons.append(f"preprodaja od {fmt_eur(sec)} (×{mult} nominalne)" if op.face_ref else f"preprodaja od {fmt_eur(sec)}")
    elif sec:
        score += 4
        reasons.append(f"već se nudi na preprodaji od {fmt_eur(sec)}")
    if op.phase == "NAJAVA" and op.days_to_onsale is not None and op.days_to_onsale <= 14:
        score += 8
        reasons.append(f"prodaja počinje za {op.days_to_onsale} d")
    if e.status == "soldout":
        score += 6
        reasons.append("rasprodano na primarnom tržištu")
    score += {"KUPI": 15, "RAZMOTRI": 7, "PROVJERI CIJENU": 6, "RIZIČNO": 3}.get(op.verdict, 0)
    if op.verdict in ("PRESKOČI", "RASPRODANO"):
        score -= 10
    if op.days_to_event < 3:
        score -= 30  # premalo vremena
    return int(round(clamp(score, 0, 100))), reasons


def hype_announcement(a) -> tuple[int, list[str]]:
    """Ocjena za najavu iz RSS-a (prije nego što događaj stigne u bilo koji izvor s cijenama)."""
    reasons: list[str] = []
    score = 0.0
    if a.fans:
        pts = clamp((math.log10(a.fans) - 4.5) / 2.5) * 45  # ~30 tis. → 0, ~10 mil. → 45
        score += pts
        reasons.append(f"{a.artist}: {a.fans:,} fanova na Deezeru".replace(",", "."))
    score += {3: 22, 2: 15, 1: 6}.get(a.region_score, 0)
    if a.places:
        reasons.append(", ".join(a.places[:3]))
    if a.presale or a.onsale:
        score += 12
        when = a.presale or a.onsale
        reasons.append(f"{'presale' if a.presale else 'prodaja'} {fmt_datetime(when)}")
    if HOT_WORDS.search(f"{a.title} {a.summary}"):
        score += 15
        reasons.append("signal velike potražnje u tekstu (rasprodano / dodatni datum / prvi put / oproštaj)")
    if a.kind == "turneje":
        score += 4
    return int(round(clamp(score, 0, 100))), reasons


# ---------------------------------------------------------------------- stanje

def load_state(data_dir: Path) -> dict:
    try:
        state = json.loads((data_dir / STATE_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        state = {}
    state.setdefault("dogadaji", {})
    state.setdefault("najave", {})
    return state


def save_state(data_dir: Path, state: dict) -> Path:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / STATE_FILE
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return path


# ---------------------------------------------------------------------- glavna logika

def _event_lines(op: Opportunity, reasons: list[str], now: datetime) -> list[str]:
    from karte.report import location

    e = op.event
    lines = [f"{location(e)} · {fmt_datetime(e.date)} · {op.verdict}"]
    if op.verdict in ("KUPI", "RAZMOTRI", "RIZIČNO") and op.best:
        lines.append(f"Kupi {op.suggested_qty} kom, nominalno ~{fmt_eur(op.face_ref)} → prodaj ~{fmt_eur(op.best.list_price)} na {op.best.name} "
                     f"(oček. dobit {fmt_eur(op.expected_value)}/kom)")
    elif op.max_buy:
        lines.append(f"Kupi samo ako je nominalna ≤ {fmt_eur(op.max_buy)} (granica {fmt_eur(op.breakeven_buy)})")
    else:
        lines.append("Cijena još nije poznata – provjeri kod prodavača kad počne prodaja.")
    starts = [p.start for p in e.presales if p.start] + ([e.public_onsale] if e.public_onsale else [])
    upcoming = sorted(s for s in starts if s > now)
    if upcoming:
        lines.append(f"Prodaja: {fmt_datetime(upcoming[0])}")
    lines.append("Zašto: " + "; ".join(reasons[:5]))
    if op.verdict == "RIZIČNO":
        lines.append("⚠ Krši uvjete kluba – ulaznica se može poništiti.")
    return lines


def scan_alerts(ops: list[Opportunity], state: dict, now: datetime, threshold: int = 70) -> list[Alert]:
    seen: dict = state["dogadaji"]
    first_run = not seen
    alerts: list[Alert] = []
    today = now.date().isoformat()
    for op in ops:
        score, reasons = hype(op)
        key = event_key(op)
        prev = seen.get(key)
        sec = _secondary_eur(op)
        e = op.event
        title = e.name if len(e.name) <= 70 else e.artist
        lines = _event_lines(op, reasons, now)
        url = e.url
        if prev is None:
            if score >= threshold:
                alerts.append(Alert(key, "NOVO", score, title, lines, url))
        else:
            if score >= threshold and prev.get("score", 0) < threshold:
                alerts.append(Alert(key, "RASTE", score, title, [f"Ocjena {prev.get('score', 0)} → {score}"] + lines, url))
            elif op.verdict == "KUPI" and prev.get("verdict") != "KUPI":
                alerts.append(Alert(key, "KUPI", score, title, [f"Preporuka {prev.get('verdict')} → KUPI"] + lines, url))
            old_sec = prev.get("secondary")
            if sec and old_sec and sec >= old_sec * 1.25 and score >= threshold - 20:
                alerts.append(Alert(key, "CIJENA", score, title, [f"Preprodaja {fmt_eur(old_sec)} → {fmt_eur(sec)}"] + lines, url))
        # podsjetnik: prodaja počinje za < 48 h (jednom po terminu)
        starts = [p.start for p in e.presales if p.start] + ([e.public_onsale] if e.public_onsale else [])
        reminded = set((prev or {}).get("podsjetnici", []))
        for start in starts:
            if now <= start <= now + timedelta(hours=48) and start.isoformat() not in reminded and score >= threshold - 15:
                alerts.append(Alert(key, "PRODAJA USKORO", score, title, [f"Počinje {fmt_datetime(start)} – uđi u red 10–15 min ranije"] + lines, url))
                reminded.add(start.isoformat())
        history = list((prev or {}).get("povijest", []))
        if not history or history[-1].get("dan") != today:
            from karte.ucenje import features

            history.append({"dan": today, "ocjena": score, "presuda": op.verdict, "preprodaja": sec, "nominalna": op.face_ref,
                            "znacajke": features(op), "spekulativno": "spekulativ" in ((e.secondary.source if e.secondary else "") or ""),
                            "heuristika": round(math.log(op.multiplier), 5) if op.multiplier and op.multiplier_source.startswith("model") else None})
        seen[key] = {
            "naziv": e.name, "datum": e.date.isoformat(), "score": score, "verdict": op.verdict, "secondary": sec,
            "prvi_put": (prev or {}).get("prvi_put", today), "podsjetnici": sorted(reminded), "povijest": history[-HISTORY_LIMIT:],
        }
    # očisti prošle događaje
    for key in [k for k, v in seen.items() if v.get("datum", "9999") < (now - timedelta(days=2)).isoformat()]:
        seen.pop(key, None)
    if first_run:
        alerts = sorted((a for a in alerts if a.kind == "NOVO"), key=lambda a: -a.score)[:FIRST_RUN_TOP]
    return alerts


def announcement_alerts(items, state: dict, now: datetime, threshold: int = 70) -> list[Alert]:
    seen: dict = state["najave"]
    first_run = not seen
    alerts = []
    for a in items:
        if a.link in seen:
            continue
        score, reasons = hype_announcement(a)
        seen[a.link] = {"dan": now.date().isoformat(), "score": score, "naslov": a.title[:120]}
        if score >= threshold:
            lines = [f"{a.source}" + (f" · objavljeno {fmt_datetime(a.published)}" if a.published else "")] + ["Zašto: " + "; ".join(reasons)]
            lines.append("Prati prodaju i spremi događaj gumbom „karte: spremi” kad se pojave cijene.")
            alerts.append(Alert(f"najava|{a.link}", "NAJAVA", score, a.title, lines, a.link))
    cutoff = (now - timedelta(days=60)).date().isoformat()
    for link in [k for k, v in seen.items() if v.get("dan", "9999") < cutoff]:
        seen.pop(link, None)
    if first_run:
        alerts = sorted(alerts, key=lambda x: -x.score)[:FIRST_RUN_TOP]
    return alerts


def run_radar(opts, settings, data_dir: Path, threshold: int = 70, announcements: bool = True, http=None,
              now: datetime | None = None) -> dict:
    from karte.net import FileCache, HttpClient
    from karte.pipeline import run_scan

    now = now or utcnow()
    opts.now = now
    state = load_state(data_dir)
    result = run_scan(opts, settings, http=http)
    alerts = scan_alerts(result.opportunities, state, now, threshold)
    warnings = list(result.warnings)
    if announcements:
        from karte.announcements import fetch_announcements

        http = http or HttpClient(cache=FileCache(settings.cache_dir, ttl_seconds=3600), min_interval=0.3)
        items, ann_warnings = fetch_announcements(http, now=now, days=7, data_dir=data_dir)
        warnings.extend(ann_warnings)
        alerts.extend(announcement_alerts(items, state, now, threshold))
    state["zadnje_pokretanje"] = now.isoformat()
    path = save_state(data_dir, state)
    alerts.sort(key=lambda a: (a.kind != "PRODAJA USKORO", -a.score))
    top = sorted(((hype(op)[0], op) for op in result.opportunities), key=lambda t: -t[0])[:10]
    return {
        "alerts": alerts,
        "top": [{"score": s, "name": op.event.name, "date": op.event.date.isoformat(), "verdict": op.verdict} for s, op in top],
        "warnings": warnings,
        "sources": result.sources,
        "state_path": str(path),
        "tracked": len(state["dogadaji"]),
    }


def telegram_blocks(result: dict) -> list[str]:
    alerts: list[Alert] = result["alerts"]
    head = f"🎟️ <b>Radar ulaznica</b> – {len(alerts)} {'obavijest' if len(alerts) == 1 else 'obavijesti'}"
    return [head] + [a.text() for a in alerts]
