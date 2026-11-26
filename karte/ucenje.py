"""Naš model koji uči iz stvarnih cijena: koliko će se ulaznica preprodavati u odnosu na nominalnu cijenu.

Javni skupovi s pojedinačnim cijenama (StubHub, SeatGeek – rebrowser na Hugging Faceu) imaju cijene zaključane, a
Hugging Face nema gotov model za ovu namjenu. Zato aplikacija sama skuplja primjere:
  - radar svaki dan za svaki događaj zapiše značajke (potražnja, rijetkost, turneja, oznake, kapacitet, dani do događaja)
    i cijene (najniža na preprodaji, nominalna) → radar_stanje.json,
  - trenutna procjena (snimka/živi izvori) daje događaje koji već imaju i nominalnu i cijenu s preprodaje.

Model: ridge regresija na ln(preprodaja / nominalna) – mali, objašnjiv, radi bez dodatnih biblioteka. Uključuje se tek
kad ima dovoljno primjera (MIN_PRIMJERA) i kad u unakrsnoj provjeri griješi manje od postojeće heuristike; tada se
miješa s heuristikom s težinom n / (n + 50). `karte model` pokazuje koliko je primjera i koliko je model točan.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from karte.util import utcnow

MODEL_FILE = "naucen_model.json"
MIN_PRIMJERA = 25
LAMBDA = 1.0
FEATURES = ["popularity", "scarcity", "tour", "buzz", "log_capacity", "sport", "first_visit", "farewell", "added_date",
            "derby", "trend", "days_before"]


def features(op) -> dict:
    """Značajke događaja u trenutku procjene (iste kao u modelu potražnje)."""
    return features_from(op.event, op.demand.components, op.days_to_event)


def features_from(e, comps: dict, days_to_event: int) -> dict:
    return {
        "popularity": round(comps.get("popularity", 0.0), 4),
        "scarcity": round(comps.get("scarcity", 0.0), 4),
        "tour": round(comps.get("tour", 0.0), 4),
        "buzz": round(comps.get("buzz", 0.0), 4),
        "log_capacity": round(math.log10(e.capacity) / 5, 4) if e.capacity else 0.8,
        "sport": 1.0 if e.segment == "sport" else 0.0,
        "first_visit": 1.0 if "first_visit" in e.tags else 0.0,
        "farewell": 1.0 if ("farewell" in e.tags or "reunion" in e.tags) else 0.0,
        "added_date": 1.0 if "added_date" in e.tags else 0.0,
        "derby": 1.0 if ("derby" in e.tags or "final" in e.tags) else 0.0,
        "trend": round(min((e.artist_trend or 1.0), 4.0) / 4, 4),
        "days_before": round(min(max(days_to_event, 0), 365) / 365, 4),
    }


def observation(op) -> dict | None:
    """Primjer za učenje: značajke + ln(preprodaja/nominalna); None ako nema obje cijene ili su spekulativne."""
    from karte.knowledge import ModelConfig

    e = op.event
    sec = e.secondary
    if sec is None or not sec.lowest or not op.face_ref or "spekulativ" in (sec.source or ""):
        return None
    resale = ModelConfig.load().to_eur(sec.lowest, sec.currency)
    if not resale or resale <= 0:
        return None
    return {"znacajke": features(op), "y": round(math.log(resale / op.face_ref), 5),
            "heuristika": round(math.log(op.multiplier), 5) if op.multiplier and op.multiplier_source.startswith("model") else None}


# ---------------------------------------------------------------------- ridge regresija bez numpy-ja

def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        m[col], m[piv] = m[piv], m[col]
        if abs(m[col][col]) < 1e-12:
            continue
        for r in range(n):
            if r != col:
                factor = m[r][col] / m[col][col]
                for c in range(col, n + 1):
                    m[r][c] -= factor * m[col][c]
    return [m[i][n] / m[i][i] if abs(m[i][i]) > 1e-12 else 0.0 for i in range(n)]


def fit(rows: list[dict], lam: float = LAMBDA) -> dict:
    """Ridge regresija (slobodni član se ne kažnjava)."""
    x = [[1.0] + [r["znacajke"].get(f, 0.0) for f in FEATURES] for r in rows]
    y = [r["y"] for r in rows]
    k = len(x[0])
    xtx = [[sum(row[i] * row[j] for row in x) + (lam if i == j and i > 0 else 0.0) for j in range(k)] for i in range(k)]
    xty = [sum(row[i] * yy for row, yy in zip(x, y)) for i in range(k)]
    w = _solve(xtx, xty)
    return {"intercept": w[0], "coef": dict(zip(FEATURES, w[1:]))}


def predict(model: dict, feats: dict) -> float:
    """Predviđeni ln(preprodaja / nominalna)."""
    return model["intercept"] + sum(model["coef"].get(f, 0.0) * feats.get(f, 0.0) for f in FEATURES)


def cross_validate(rows: list[dict], folds: int = 5) -> dict:
    """Prosječna apsolutna pogreška u omjeru cijena: model vs heuristika (gdje je zapisana)."""
    if len(rows) < folds:
        return {}
    err_model, err_heur = [], []
    for k in range(folds):
        test = rows[k::folds]
        train = [r for i, r in enumerate(rows) if i % folds != k]
        m = fit(train)
        for r in test:
            err_model.append(abs(math.exp(predict(m, r["znacajke"])) - math.exp(r["y"])))
            if r.get("heuristika") is not None:
                err_heur.append(abs(math.exp(r["heuristika"]) - math.exp(r["y"])))
    out = {"mae_model": round(sum(err_model) / len(err_model), 3)}
    if err_heur:
        out["mae_heuristika"] = round(sum(err_heur) / len(err_heur), 3)
    return out


# ---------------------------------------------------------------------- skup podataka i spremanje

def dataset(data_dir: Path, ops: list | None = None) -> list[dict]:
    """Jedan primjer po događaju: zadnje opažanje iz povijesti radara + događaji iz trenutne procjene."""
    from karte.radar import event_key, load_state

    rows: dict[str, dict] = {}
    for key, info in load_state(data_dir)["dogadaji"].items():
        for h in reversed(info.get("povijest", [])):
            if h.get("znacajke") and h.get("preprodaja") and h.get("nominalna") and not h.get("spekulativno"):
                rows[key] = {"znacajke": h["znacajke"], "y": round(math.log(h["preprodaja"] / h["nominalna"]), 5),
                             "heuristika": h.get("heuristika"), "naziv": info.get("naziv", key)}
                break
    for op in ops or []:
        obs = observation(op)
        if obs:
            rows[event_key(op)] = {**obs, "naziv": op.event.name}
    return list(rows.values())


def train(data_dir: Path, ops: list | None = None) -> dict:
    rows = dataset(data_dir, ops)
    report: dict = {"primjera": len(rows), "potrebno": MIN_PRIMJERA, "trenirano": utcnow().isoformat(timespec="minutes")}
    if len(rows) < 5:
        report["poruka"] = f"Premalo primjera ({len(rows)}). Radar ih skuplja automatski; model se uključuje od {MIN_PRIMJERA}."
        return report
    model = fit(rows)
    report.update(model)
    report.update(cross_validate(rows))
    active = len(rows) >= MIN_PRIMJERA and report.get("mae_model", 9) < report.get("mae_heuristika", 9)
    report["aktivan"] = active
    report["poruka"] = (f"Model je aktivan: u provjeri griješi {report['mae_model']} (heuristika {report.get('mae_heuristika', '—')})."
                        if active else f"Model je naučen na {len(rows)} primjera, ali se još ne koristi "
                        f"(treba ≥ {MIN_PRIMJERA} primjera i manja pogreška od heuristike).")
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / MODEL_FILE).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    return report


def load(data_dir: Path | None = None) -> dict | None:
    from karte.snapshot import data_dir as default_dir

    try:
        model = json.loads(((data_dir or default_dir()) / MODEL_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return model if model.get("aktivan") and model.get("coef") else None


def blend_multiplier(model: dict, op_like_features: dict, heuristic: float) -> tuple[float, str]:
    """Miješanje heuristike i naučenog modela prema broju primjera."""
    n = model.get("primjera", 0)
    w = n / (n + 50)
    learned = math.exp(predict(model, op_like_features))
    return w * learned + (1 - w) * heuristic, f"model naučen na {n} primjera ({w * 100:.0f} %) + heuristika"
