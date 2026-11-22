"""Izvještaji: terminal, Markdown, HTML, CSV, JSON."""

from __future__ import annotations

import csv
import html
import io
import json
from dataclasses import asdict

from karte import __version__
from karte.models import Opportunity
from karte.pipeline import ScanResult
from karte.util import fmt_date, fmt_datetime, fmt_eur, fmt_pct, hr_plural

DISCLAIMER = (
    "Procjene su informativne i temelje se na heurističkom modelu i javnim podacima – nisu financijski ni pravni savjet. "
    "Naknade platformi i zakoni se mijenjaju: provjeri ih prije svake kupnje. Kupuj isključivo legalno (bez botova, unutar limita)."
)

DEMO_BANNER = "DEMO PODACI – izvođači, cijene i brojke su izmišljeni (služe samo za prikaz rada aplikacije)."


def snapshot_banner(result: ScanResult) -> str | None:
    """Napomena za snimku stvarnih događaja (stanje, porijeklo cijena)."""
    if not result.is_snapshot:
        return None
    info = result.snapshot or {}
    return (
        f"STVARNI PODACI – snimka od {info.get('date_hr', '?')} ({info.get('curated', 0)} provjerenih "
        f"{hr_plural(info.get('curated', 0), 'događaj', 'događaja')} + {info.get('tour_events', 0)} "
        f"{hr_plural(info.get('tour_events', 0), 'datum', 'datuma')} turneja s Wikipedije). Cijene s preprodaje su 'od' cijene s agregatora "
        "(uz datum) – prije kupnje provjeri aktualne; gdje nominalna cijena nije javna, prikazano je do koje se cijene isplati kupiti."
    )


def _face_text(op: Opportunity) -> str:
    if op.face_ref is None and op.max_buy:
        return f"≤{fmt_eur(op.max_buy)}"
    return fmt_eur(op.face_ref)


def _ceiling_text(op: Opportunity) -> str | None:
    if op.max_buy is None and op.breakeven_buy is None:
        return None
    sec = op.event.secondary
    seen = f", {sec.observed}" if sec and sec.observed else ""
    market = f" · najniža na preprodaji {sec.lowest:g} {sec.currency} ({sec.source}{seen})" if sec and sec.lowest else ""
    return (
        f"Kupi najviše do: {fmt_eur(op.max_buy)} po ulaznici (cilj ROI) · granica isplativosti: {fmt_eur(op.breakeven_buy)}"
        f" · realna prodajna ~{fmt_eur(op.expected_resale)}{market}"
    )


def _phase_text(op: Opportunity) -> str:
    if op.phase == "NAJAVA" and op.days_to_onsale is not None:
        return f"prodaja za {op.days_to_onsale} d"
    return op.phase.lower()


def _cut(text: str, width: int) -> str:
    text = text or ""
    return text if len(text) <= width else text[: width - 1] + "…"


def _row_values(i: int, op: Opportunity) -> list[str]:
    e = op.event
    return [
        str(i),
        op.verdict,
        fmt_date(e.date),
        e.artist,
        f"{e.city} ({e.country}{'-' + e.region if e.region else ''})",
        _phase_text(op),
        _face_text(op),
        fmt_eur(op.expected_resale),
        fmt_eur(op.profit),
        fmt_pct(op.roi),
        f"{op.demand.score * 100:.0f}",
        f"{op.risk * 100:.0f}",
        str(op.suggested_qty or "–"),
        op.best.name if op.best else "—",
    ]


HEADERS = ["#", "Preporuka", "Datum", "Izvođač", "Mjesto", "Faza", "Nomin.", "Oček.prod.", "Dobit*", "Oček.ROI", "Potr.", "Rizik", "Kom", "Platforma"]
WIDTHS = [3, 19, 11, 22, 18, 16, 8, 10, 7, 8, 5, 5, 3, 22]
LEGEND = (
    "Nomin. = nominalna cijena odabrane kategorije (≤X = nije poznata, isplati se kupiti do X) · Oček.prod. = očekivana oglasna cijena · "
    "Dobit* = neto dobit po ulaznici AKO se proda "
    "(nakon svih naknada) · Oček.ROI = očekivani povrat uz vjerojatnost prodaje i rizik · Potr./Rizik = 0–100 · Kom = preporučena količina"
)


def render_terminal(result: ScanResult, top: int = 25, details: int = 5) -> str:
    out = io.StringIO()
    w = out.write
    w(f"karte {__version__} · radar za preprodaju ulaznica · {fmt_datetime(result.generated_at)} UTC\n")
    if result.is_demo:
        w(f"\n*** {DEMO_BANNER} ***\n")
    if snapshot_banner(result):
        w(f"\n*** {snapshot_banner(result)} ***\n")
    o = result.options
    w(f"Države: {', '.join(o.countries) or '—'} · prozor: {o.days} d · prodaje koje počinju u {o.onsale_days} d · "
      f"budžet {fmt_eur(o.budget)} · kategorija: {o.category}{' · STROGO (najavljeni zakoni)' if o.strict else ''}\n")
    if result.sources:
        w("Izvori: " + "; ".join(result.sources) + "\n")
    for warning in result.warnings:
        w(f"! {warning}\n")
    ops = result.opportunities[:top]
    if not ops:
        w("\nNema rezultata.\n")
        return out.getvalue()

    w("\n" + " ".join(h.ljust(wd) for h, wd in zip(HEADERS, WIDTHS)) + "\n")
    w(" ".join("-" * wd for wd in WIDTHS) + "\n")
    for i, op in enumerate(ops, 1):
        w(" ".join(_cut(v, wd).ljust(wd) for v, wd in zip(_row_values(i, op), WIDTHS)) + "\n")
    w(LEGEND + "\n")

    buys = [op for op in result.opportunities if op.verdict in ("KUPI", "RAZMOTRI")]
    if buys:
        total_cost = sum((op.buy_cost or 0) * op.suggested_qty for op in buys)
        total_ev = sum(op.total_expected_value for op in buys)
        w(f"\nUkupno preporučeno (KUPI+RAZMOTRI): ulaganje ~{fmt_eur(total_cost)}, očekivana vrijednost dobiti ~{fmt_eur(total_ev)}\n")

    for i, op in enumerate(ops[:details], 1):
        w("\n" + "=" * 100 + "\n")
        w(render_detail_text(i, op))
    w("\n" + DISCLAIMER + "\n")
    return out.getvalue()


def location(e) -> str:
    place = ", ".join(x for x in (e.venue, e.city) if x)
    code = f"{e.country}-{e.region}" if e.region else e.country
    return f"{place} ({code})" if place else code


def render_detail_text(i: int, op: Opportunity) -> str:
    e = op.event
    a = op.advice
    lines = [
        f"#{i} {e.name} — {location(e)} · {fmt_datetime(e.date)}",
        f"   {a.get('summary', '')}",
        f"   Nominalna (ref.): {fmt_eur(op.face_ref)} · trošak s naknadama: {fmt_eur(op.buy_cost, 2)} · "
        f"očekivana prodajna: {fmt_eur(op.expected_resale)} (×{op.multiplier:.2f}, {op.multiplier_source})" if op.multiplier else
        (f"   Nominalna (ref.): {fmt_eur(op.face_ref)}" if op.face_ref is not None or not _ceiling_text(op) else ""),
        f"   Potražnja {op.demand.score * 100:.0f}/100 (pouzdanost {op.demand.confidence * 100:.0f} %) · rizik {op.risk * 100:.0f}/100 · faza: {op.phase}",
    ]
    if _ceiling_text(op):
        lines.insert(3, "   " + _ceiling_text(op))
    lines = [line for line in lines if line]
    for title, key in (("KAKO KUPITI", "buy"), ("KAKO I GDJE PRODATI", "sell")):
        items = a.get(key) or []
        if items:
            lines.append(f"   {title}:")
            lines.extend(f"     • {item}" for item in items)
    ladder = a.get("ladder") or []
    if ladder:
        lines.append("   CJENIK (plan spuštanja cijene):")
        lines.extend(f"     {row['date']:>12}  {fmt_eur(row['price']):>8}  {row['label']}" for row in ladder)
    safety = a.get("safety") or []
    if safety:
        lines.append("   SIGURNOSNA PROVJERA:")
        icon = {"ok": "✓", "warn": "!", "bad": "✕"}
        lines.extend(f"     {icon.get(c['level'], '·')} {c['text']}" for c in safety)
    risks = a.get("risks") or []
    if risks:
        lines.append("   RIZICI:")
        lines.extend(f"     ! {r}" for r in risks)
    legal_notes = a.get("legal") or []
    if legal_notes:
        lines.append("   PRAVNO:")
        lines.extend(f"     § {n}" for n in legal_notes)
    if e.url:
        lines.append(f"   Link: {e.url}")
    return "\n".join(lines) + "\n"


# ------------------------------------------------------------------ Markdown
def render_markdown(result: ScanResult, top: int = 50, details: int = 10) -> str:
    o = result.options
    md = [f"# Radar preprodaje ulaznica — {fmt_datetime(result.generated_at)} UTC", ""]
    if result.is_demo:
        md += [f"> **{DEMO_BANNER}**", ""]
    if snapshot_banner(result):
        md += [f"> **{snapshot_banner(result)}**", ""]
    md += [
        f"- **Države:** {', '.join(o.countries) or '—'}",
        f"- **Prozor:** koncerti u idućih {o.days} dana + prodaje koje počinju u idućih {o.onsale_days} dana",
        f"- **Budžet:** {fmt_eur(o.budget)} · **kategorija:** {o.category}{' · **strogo (najavljeni zakoni)**' if o.strict else ''}",
        f"- **Izvori:** {'; '.join(result.sources) or '—'}",
        "",
    ]
    for warning in result.warnings:
        md.append(f"> ⚠️ {warning}")
    md += ["", "| " + " | ".join(HEADERS) + " |", "|" + "---|" * len(HEADERS)]
    for i, op in enumerate(result.opportunities[:top], 1):
        vals = _row_values(i, op)
        vals[1] = f"**{vals[1]}**"
        md.append("| " + " | ".join(v.replace("|", "/") for v in vals) + " |")
    md += ["", f"_{LEGEND}_", ""]
    for i, op in enumerate(result.opportunities[:details], 1):
        e = op.event
        a = op.advice
        md += [f"## {i}. {e.name}", "", f"**{location(e)} · {fmt_datetime(e.date)} · {op.phase}**", "", f"> {a.get('summary', '')}", ""]
        if op.multiplier:
            md.append(
                f"Nominalna (ref.) {fmt_eur(op.face_ref)} · trošak s naknadama {fmt_eur(op.buy_cost, 2)} · očekivana prodajna "
                f"{fmt_eur(op.expected_resale)} (×{op.multiplier:.2f}, {op.multiplier_source}) · potražnja {op.demand.score * 100:.0f}/100 · "
                f"rizik {op.risk * 100:.0f}/100"
            )
            md.append("")
        if _ceiling_text(op):
            md += [_ceiling_text(op), ""]
        for title, key in (("Kako kupiti", "buy"), ("Kako i gdje prodati", "sell")):
            if a.get(key):
                md += [f"**{title}**", ""] + [f"- {x}" for x in a[key]] + [""]
        if a.get("platforms"):
            md += ["| Platforma | Oglasna cijena | Neto | P(prodaja) | Očekivana vrijednost |", "|---|---|---|---|---|"]
            md += [
                f"| {p['name']} | {fmt_eur(p['list_price'])}{' (limit)' if p['capped'] else ''} | {fmt_eur(p['net'])} | {p['p_sell'] * 100:.0f} % | {fmt_eur(p['ev'])} |"
                for p in a["platforms"]
            ]
            md.append("")
        if a.get("ladder"):
            md += ["**Cjenik**", "", "| Kada | Cijena | |", "|---|---|---|"]
            md += [f"| {r['date']} | {fmt_eur(r['price'])} | {r['label']} |" for r in a["ladder"]]
            md.append("")
        if a.get("safety"):
            icon = {"ok": "✅", "warn": "⚠️", "bad": "⛔"}
            md += ["**Sigurnosna provjera**", ""] + [f"- {icon.get(c['level'], '')} {c['text']}" for c in a["safety"]] + [""]
        if a.get("links"):
            md += ["**Provjeri cijene i dostupnost**", ""] + [f"- {link['group']}: [{link['label']}]({link['url']})" for link in a["links"]] + [""]
        if a.get("risks"):
            md += ["**Rizici**", ""] + [f"- {x}" for x in a["risks"]] + [""]
        if a.get("legal"):
            md += ["**Pravno**", ""] + [f"- {x}" for x in a["legal"]] + [""]
    md += ["---", f"_{DISCLAIMER}_", ""]
    return "\n".join(md)


# ------------------------------------------------------------------ CSV / JSON
CSV_FIELDS = [
    "verdict", "date", "artist", "event", "venue", "city", "country", "region", "phase", "days_to_event", "days_to_onsale",
    "face_ref_eur", "buy_cost_eur", "expected_resale_eur", "profit_eur", "expected_value_eur", "roi", "demand", "confidence",
    "risk", "qty", "best_platform", "legal_rule", "max_buy_eur", "breakeven_buy_eur", "secondary_lowest", "secondary_currency",
    "secondary_source", "secondary_observed", "deezer_fans", "wiki_trend", "source", "url",
]


def render_csv(result: ScanResult) -> str:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_FIELDS)
    writer.writeheader()
    for op in result.opportunities:
        e = op.event
        writer.writerow({
            "verdict": op.verdict,
            "date": e.date.isoformat(),
            "artist": e.artist,
            "event": e.name,
            "venue": e.venue,
            "city": e.city,
            "country": e.country,
            "region": e.region or "",
            "phase": op.phase,
            "days_to_event": op.days_to_event,
            "days_to_onsale": op.days_to_onsale if op.days_to_onsale is not None else "",
            "face_ref_eur": _r(op.face_ref),
            "buy_cost_eur": _r(op.buy_cost),
            "expected_resale_eur": _r(op.expected_resale),
            "profit_eur": _r(op.profit),
            "expected_value_eur": _r(op.expected_value),
            "roi": _r(op.roi, 3),
            "demand": _r(op.demand.score, 3),
            "confidence": _r(op.demand.confidence, 3),
            "risk": _r(op.risk, 3),
            "qty": op.suggested_qty,
            "best_platform": op.best.name if op.best else "",
            "legal_rule": op.legal.rule,
            "max_buy_eur": _r(op.max_buy),
            "breakeven_buy_eur": _r(op.breakeven_buy),
            "secondary_lowest": _r(e.secondary.lowest) if e.secondary else "",
            "secondary_currency": e.secondary.currency if e.secondary else "",
            "secondary_source": e.secondary.source if e.secondary else "",
            "secondary_observed": (e.secondary.observed or "") if e.secondary else "",
            "deezer_fans": e.artist_fans or "",
            "wiki_trend": _r(e.artist_trend, 3),
            "source": e.source,
            "url": e.url or "",
        })
    return buf.getvalue()


def _r(value, digits: int = 2):
    return "" if value is None else round(value, digits)


def to_dict(result: ScanResult) -> dict:
    ops = []
    for op in result.opportunities:
        d = asdict(op)
        d["total_expected_value"] = op.total_expected_value
        ops.append(d)
    return {
        "generated_at": result.generated_at.isoformat(),
        "is_demo": result.is_demo,
        "is_snapshot": result.is_snapshot,
        "snapshot": result.snapshot,
        "options": asdict(result.options),
        "sources": result.sources,
        "warnings": result.warnings,
        "opportunities": ops,
    }


def render_json(result: ScanResult) -> str:
    return json.dumps(to_dict(result), ensure_ascii=False, indent=2, default=str)


# ------------------------------------------------------------------ HTML
VERDICT_CLASS = {
    "KUPI": "v-buy",
    "RAZMOTRI": "v-maybe",
    "PROVJERI CIJENU": "v-check",
    "RASPRODANO": "v-sold",
    "PRESKOČI": "v-skip",
    "ZAKONSKI OGRANIČENO": "v-legal",
    "UVJETI ZABRANJUJU": "v-legal",
    "NEMA CIJENE": "v-skip",
    "OTKAZANO": "v-skip",
}

HTML_CSS = """
:root{--bg:#f7f7f5;--surface:#fff;--text:#1d1d1b;--muted:#6b6b66;--border:#e3e3de;--accent:#2f5bea;
--buy:#1f8a4c;--buy-bg:#e5f4ea;--maybe:#a86a00;--maybe-bg:#fbf0d9;--sold:#2f5bea;--sold-bg:#e6ecfd;
--legal:#b42318;--legal-bg:#fde8e6;--skip:#6b6b66;--skip-bg:#efefeb}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141413;--surface:#1e1e1c;--text:#ecebe6;--muted:#a2a19a;
--border:#33332f;--accent:#7c9bff;--buy:#5cc98a;--buy-bg:#16301f;--maybe:#e6b44c;--maybe-bg:#33270f;--sold:#8ea8ff;--sold-bg:#1b2445;
--legal:#ff8a80;--legal-bg:#3a1714;--skip:#a2a19a;--skip-bg:#262624}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.5 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1200px;margin:0 auto;padding:24px 16px 64px}h1{font-size:1.6rem;margin:0 0 4px}h2{font-size:1.15rem;margin:0}
.muted{color:var(--muted)}.banner{background:var(--maybe-bg);color:var(--maybe);border:1px solid var(--border);border-radius:10px;padding:10px 14px;margin:16px 0;font-weight:600}
.warn{color:var(--maybe);margin:4px 0}.meta{display:flex;flex-wrap:wrap;gap:8px 20px;margin:12px 0 20px;color:var(--muted);font-size:.9rem}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(150px,100%),1fr));gap:12px;margin:16px 0 24px}
.kpi{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:12px 14px}.kpi b{display:block;font-size:1.35rem}
.tablewrap{overflow-x:auto;background:var(--surface);border:1px solid var(--border);border-radius:12px}
table{border-collapse:collapse;width:100%;font-size:.88rem}th,td{padding:8px 10px;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap}
th{cursor:pointer;user-select:none;position:sticky;top:0;background:var(--surface);font-weight:600}th:hover{color:var(--accent)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}tr:last-child td{border-bottom:0}
.pill{display:inline-block;padding:2px 8px;border-radius:999px;font-weight:600;font-size:.78rem}
.v-buy{color:var(--buy);background:var(--buy-bg)}.v-maybe{color:var(--maybe);background:var(--maybe-bg)}.v-sold{color:var(--sold);background:var(--sold-bg)}
.v-legal{color:var(--legal);background:var(--legal-bg)}.v-skip{color:var(--skip);background:var(--skip-bg)}
.v-check{color:var(--sold);background:transparent;box-shadow:inset 0 0 0 1px currentColor}.banner.info{background:var(--sold-bg);color:var(--sold)}
.bar{display:inline-block;width:48px;height:6px;border-radius:3px;background:var(--border);vertical-align:middle;margin-right:6px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--accent)}
.cards{display:grid;grid-template-columns:minmax(0,1fr);gap:14px;margin-top:28px}.card{min-width:0;background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.card summary{cursor:pointer;list-style:none;display:flex;flex-wrap:wrap;gap:8px 12px;align-items:center}.card summary::-webkit-details-marker{display:none}
.card h3{font-size:.95rem;margin:14px 0 6px}.card ul{margin:0;padding-left:20px}.card li{margin:3px 0}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(280px,100%),1fr));gap:4px 24px}.grid2>*{min-width:0}
.small{font-size:.85rem}a{color:var(--accent)}footer{margin-top:32px;font-size:.85rem;color:var(--muted)}
"""

HTML_JS = """
document.querySelectorAll('th[data-k]').forEach((th,idx)=>{th.addEventListener('click',()=>{
const tb=th.closest('table').tBodies[0];const rows=[...tb.rows];const dir=th.dataset.dir==='asc'?'desc':'asc';th.dataset.dir=dir;
const k=th.cellIndex;rows.sort((a,b)=>{const x=a.cells[k].dataset.v??a.cells[k].textContent,y=b.cells[k].dataset.v??b.cells[k].textContent;
const nx=parseFloat(x),ny=parseFloat(y);const c=(!isNaN(nx)&&!isNaN(ny))?nx-ny:x.localeCompare(y,'hr');return dir==='asc'?c:-c});
rows.forEach(r=>tb.appendChild(r));});});
"""


def _e(text) -> str:
    return html.escape(str(text if text is not None else ""))


def _num(value) -> str:
    return "" if value is None else f"{value:.4f}"


def render_html(result: ScanResult, top: int = 200) -> str:
    o = result.options
    ops = result.opportunities[:top]
    buys = [op for op in result.opportunities if op.verdict in ("KUPI", "RAZMOTRI")]
    total_cost = sum((op.buy_cost or 0) * op.suggested_qty for op in buys)
    total_ev = sum(op.total_expected_value for op in buys)

    rows = []
    for i, op in enumerate(ops, 1):
        e = op.event
        rows.append(
            "<tr>"
            f"<td class='num' data-v='{i}'>{i}</td>"
            f"<td data-v='{_e(op.verdict)}'><span class='pill {VERDICT_CLASS.get(op.verdict, 'v-skip')}'>{_e(op.verdict)}</span></td>"
            f"<td data-v='{e.date.isoformat()}'>{_e(fmt_date(e.date))}</td>"
            f"<td><a href='#ev{i}'>{_e(e.artist)}</a></td>"
            f"<td>{_e(location(e))}</td>"
            f"<td>{_e(_phase_text(op))}</td>"
            f"<td class='num' data-v='{_num(op.face_ref if op.face_ref is not None else op.max_buy)}'>{_e(_face_text(op))}</td>"
            f"<td class='num' data-v='{_num(op.expected_resale)}'>{_e(fmt_eur(op.expected_resale))}</td>"
            f"<td class='num' data-v='{_num(op.profit)}'>{_e(fmt_eur(op.profit))}</td>"
            f"<td class='num' data-v='{_num(op.roi)}'>{_e(fmt_pct(op.roi))}</td>"
            f"<td class='num' data-v='{op.demand.score:.4f}'><span class='bar'><i style='width:{op.demand.score * 100:.0f}%'></i></span>{op.demand.score * 100:.0f}</td>"
            f"<td class='num' data-v='{op.risk:.4f}'>{op.risk * 100:.0f}</td>"
            f"<td class='num' data-v='{op.suggested_qty}'>{op.suggested_qty or '–'}</td>"
            f"<td>{_e(op.best.name if op.best else '—')}</td>"
            "</tr>"
        )

    cards = []
    for i, op in enumerate(ops, 1):
        e = op.event
        a = op.advice
        parts = [
            f"<details class='card' id='ev{i}'{' open' if i <= 3 and op.verdict in ('KUPI', 'RAZMOTRI') else ''}>",
            f"<summary><span class='pill {VERDICT_CLASS.get(op.verdict, 'v-skip')}'>{_e(op.verdict)}</span>"
            f"<h2>{i}. {_e(e.name)}</h2><span class='muted'>{_e(location(e))} · {_e(fmt_datetime(e.date))} · {_e(op.phase)}</span></summary>",
            f"<p>{_e(a.get('summary', ''))}</p>",
        ]
        if op.multiplier:
            parts.append(
                f"<p class='small muted'>Nominalna (ref.) {_e(fmt_eur(op.face_ref))} · trošak s naknadama {_e(fmt_eur(op.buy_cost, 2))} · "
                f"očekivana prodajna {_e(fmt_eur(op.expected_resale))} (×{op.multiplier:.2f}, {_e(op.multiplier_source)}) · "
                f"potražnja {op.demand.score * 100:.0f}/100 (pouzdanost {op.demand.confidence * 100:.0f} %) · rizik {op.risk * 100:.0f}/100</p>"
            )
        if _ceiling_text(op):
            parts.append(f"<p class='small'><b>{_e(_ceiling_text(op))}</b></p>")
        parts.append("<div class='grid2'>")
        for title, key in (("Kako kupiti", "buy"), ("Kako i gdje prodati", "sell")):
            if a.get(key):
                parts.append(f"<div><h3>{title}</h3><ul>" + "".join(f"<li>{_e(x)}</li>" for x in a[key]) + "</ul></div>")
        parts.append("</div>")
        if a.get("platforms"):
            parts.append("<h3>Usporedba platformi (po ulaznici)</h3><div class='tablewrap'><table><thead><tr><th>Platforma</th><th class='num'>Oglasna</th>"
                         "<th class='num'>Neto</th><th class='num'>P(prodaja)</th><th class='num'>Oček. vrijednost</th></tr></thead><tbody>")
            for p in a["platforms"]:
                parts.append(
                    f"<tr><td>{_e(p['name'])}</td><td class='num'>{_e(fmt_eur(p['list_price']))}{' (limit)' if p['capped'] else ''}</td>"
                    f"<td class='num'>{_e(fmt_eur(p['net']))}</td><td class='num'>{p['p_sell'] * 100:.0f} %</td><td class='num'>{_e(fmt_eur(p['ev']))}</td></tr>"
                )
            parts.append("</tbody></table></div>")
        if a.get("ladder"):
            parts.append("<h3>Cjenik – plan spuštanja cijene</h3><ul>" + "".join(
                f"<li><b>{_e(r['date'])}</b> → {_e(fmt_eur(r['price']))} — {_e(r['label'])}</li>" for r in a["ladder"]) + "</ul>")
        if a.get("safety"):
            icon = {"ok": "✓", "warn": "!", "bad": "✕"}
            parts.append("<h3>Sigurnosna provjera</h3><ul>" + "".join(f"<li><b>{icon.get(c['level'], '')}</b> {_e(c['text'])}</li>" for c in a["safety"]) + "</ul>")
        if a.get("links"):
            parts.append("<h3>Provjeri cijene i dostupnost</h3><p class='small'>" + " · ".join(
                f"{_e(link['group'])}: <a href='{_e(link['url'])}' rel='noopener noreferrer' target='_blank'>{_e(link['label'])}</a>"
                for link in a["links"]) + "</p>")
        if a.get("risks"):
            parts.append("<h3>Rizici</h3><ul>" + "".join(f"<li>{_e(x)}</li>" for x in a["risks"]) + "</ul>")
        if a.get("legal"):
            parts.append("<h3>Pravno</h3><ul>" + "".join(f"<li>{_e(x)}</li>" for x in a["legal"]) + "</ul>")
            if a.get("legal_sources"):
                parts.append("<p class='small'>Izvori: " + " · ".join(f"<a href='{_e(u)}' rel='noopener' target='_blank'>{_e(u.split('/')[2])}</a>" for u in a["legal_sources"]) + "</p>")
        if e.url:
            parts.append(f"<p class='small'><a href='{_e(e.url)}' rel='noopener' target='_blank'>Stranica događaja ↗</a></p>")
        parts.append("</details>")
        cards.append("".join(parts))

    warnings = "".join(f"<div class='warn'>⚠ {_e(w)}</div>" for w in result.warnings)
    banner = f"<div class='banner'>{_e(DEMO_BANNER)}</div>" if result.is_demo else ""
    if snapshot_banner(result):
        banner += f"<div class='banner info'>{_e(snapshot_banner(result))}</div>"
    head_cells = "".join(
        f"<th data-k='{k}' class='{'num' if k in (0, 6, 7, 8, 9, 10, 11, 12) else ''}'>{_e(h)}</th>" for k, h in enumerate(HEADERS)
    )
    return f"""<!doctype html>
<html lang="hr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Radar preprodaje ulaznica</title><style>{HTML_CSS}</style></head>
<body><div class="wrap">
<h1>Radar preprodaje ulaznica</h1>
<div class="muted">Generirano {_e(fmt_datetime(result.generated_at))} UTC · karte {__version__}</div>
{banner}
<div class="meta"><span>Države: <b>{_e(', '.join(o.countries) or '—')}</b></span><span>Prozor: <b>{o.days} d</b> (+ prodaje koje počinju u {o.onsale_days} d)</span>
<span>Budžet: <b>{_e(fmt_eur(o.budget))}</b></span><span>Kategorija: <b>{_e(o.category)}</b></span>{'<span><b>Strogo</b> (najavljeni zakoni)</span>' if o.strict else ''}
<span>Izvori: {_e('; '.join(result.sources) or '—')}</span></div>
{warnings}
<div class="kpis">
<div class="kpi"><span class="muted">Događaja</span><b>{len(result.opportunities)}</b></div>
<div class="kpi"><span class="muted">KUPI / RAZMOTRI</span><b>{sum(op.verdict == 'KUPI' for op in result.opportunities)} / {sum(op.verdict == 'RAZMOTRI' for op in result.opportunities)}</b></div>
<div class="kpi"><span class="muted">Preporučeno ulaganje</span><b>{_e(fmt_eur(total_cost))}</b></div>
<div class="kpi"><span class="muted">Očekivana vrijednost dobiti</span><b>{_e(fmt_eur(total_ev))}</b></div>
</div>
<div class="tablewrap"><table><thead><tr>{head_cells}</tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p class="small muted">{_e(LEGEND)} · Klik na zaglavlje sortira tablicu.</p>
<div class="cards">{''.join(cards)}</div>
<footer>{_e(DISCLAIMER)}</footer>
</div><script>{HTML_JS}</script></body></html>
"""


RENDERERS = {
    "table": render_terminal,
    "md": render_markdown,
    "html": render_html,
    "csv": render_csv,
    "json": render_json,
}
