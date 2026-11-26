"""Krivulja „kada prodati” iz javnog skupa NeedATicket (Hugging Face: streetvisit/uk-resale-ticket-prices, CC BY 4.0).

NeedATicket svaki sat bilježi najnižu cijenu na StubHubu za tisuće događaja. Skup sadrži agregat: za X dana prije
događaja, medijan promjene najniže cijene u odnosu na dan događaja (i p25/p75, udio skupljih/jeftinijih događaja),
po segmentu (koncerti, sport, kazalište; velike/srednje/male dvorane) i tržištu (sve, GB, US).

Pokretanje (treba pandas i huggingface_hub – nisu ovisnosti aplikacije):
    python modeliranje/needaticket_krivulja.py
Rezultat: karte/data/vrijeme_prodaje.json (koristi ga cjenik prodaje u aplikaciji, bez dodatnih ovisnosti).
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from huggingface_hub import hf_hub_download

REPO = "streetvisit/uk-resale-ticket-prices"
OUT = Path(__file__).resolve().parents[1] / "karte" / "data" / "vrijeme_prodaje.json"


def main() -> None:
    path = hf_hub_download(REPO, "needaticket-when-to-buy.csv", repo_type="dataset")
    df = pd.read_csv(path)
    curves: dict[str, dict] = {}
    for (scope, segment), g in df.groupby(["scope", "segment"]):
        g = g.sort_values("days_before_show")
        curves[f"{scope}:{segment}"] = {
            "dogadaja": int(g["shows_in_segment"].max()),
            "tocke": [
                {
                    "dana_prije": int(r.days_before_show),
                    "medijan_pct": float(r.median_change_vs_show_day_pct),
                    "p25_pct": float(r.p25_change_pct),
                    "p75_pct": float(r.p75_change_pct),
                    "udio_skuplje": float(r.share_dearer_than_show_day),
                    "udio_jeftinije": float(r.share_cheaper_than_show_day),
                    "uzorak": int(r.shows_at_point),
                }
                for r in g.itertuples()
            ],
        }
    first = df.iloc[0]
    OUT.write_text(json.dumps({
        "izvor": "NeedATicket (najniža cijena na StubHubu, bez naknade kupca), Hugging Face: " + REPO + ", licenca CC BY 4.0",
        "dogadaji_od": str(first.shows_from), "dogadaji_do": str(first.shows_to), "azurirano": str(first.updated),
        "objasnjenje": "medijan_pct = promjena najniže cijene X dana prije događaja u odnosu na dan događaja; "
                       "udio_skuplje = udio događaja kojima je najniža cijena X dana prije bila viša nego na dan događaja.",
        "krivulje": curves,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Spremljeno {len(curves)} krivulja u {OUT}")


if __name__ == "__main__":
    main()
