# Model procjene isplativosti

Model je namjerno **jednostavan i transparentan** — heuristika na javnim podacima, ne „crna kutija”.
Svi parametri su u [`karte/data/model.toml`](../karte/data/model.toml) i mogu se nadjačati vlastitom datotekom
(`karte scan --model moj.toml`, dovoljno je navesti samo ono što mijenjaš).

## 1. Potražnja (0–1)

| Komponenta | Formula | Težina |
|---|---|---|
| **Popularnost** | log-skala Last.fm slušatelja: 50 tis. → 0, 5 mil. → 1 | 0,45 |
| **Rijetkost** | log-skala omjera `slušatelji / (kapacitet × broj koncerata u državi)`: 10 → 0, 1.000 → 1 | 0,40 |
| **Turneja** | ≤ 10 koncerata → 1, ≥ 100 → 0 (Ticketmaster `upcomingEvents`) | 0,15 |

`osnova = ponderirani prosjek` → **buzz** (oznake) gura prema 1: `osnova + 0,6 × buzz × (1 − osnova)`.

Oznake (`[buzz]`): `farewell` 0,45 · `reunion` 0,45 · `added_date` 0,35 · `regional_star` 0,40 · `first_visit` 0,30 ·
`anniversary` 0,15 · `new_album` 0,10 · rasprodano 0,50 (zbroj se ograničava na 1).

**Sekundarno tržište**: ako postoje stvarni oglasi (SeatGeek ili ručno iz viagoga/Njuškala), signal
`(realni multiplikator − 0,7) / 1,3` nosi **60 %** potražnje.

> Last.fm brojke su ~5–10× manje od Spotify „mjesečnih slušatelja”; top izvođači imaju ~5–9 mil. Balkanske zvijezde su
> na Last.fm-u jako podcijenjene → oznaka `regional_star` ili ručni broj u stupcu `slusatelji`.

**Pouzdanost** (0–1) raste s dostupnim podacima: slušatelji (+0,35), stvarni kapacitet (+0,15), nominalna cijena (+0,15), sekundarne cijene (+0,20).

## 2. Očekivana prodajna cijena

- **Sa sekundarnim podacima**: `najniži oglas × (1 − 0,20 kupčevih naknada) × 0,95` (za kategoriju `cheap`) ili
  `medijan × 0,80 × 0,85` (za `mid`/`premium`). Kupčeve naknade se ne odbijaju za izvore bez naknada (Njuškalo, Facebook).
- **Bez podataka**: `multiplikator = 0,8 + 1,7 × potražnja²` → potražnja 0,5 → ×1,23; 0,7 → ×1,63; 0,85 → ×2,03; 1,0 → ×2,5.
- Zadnjih 10 dana prije događaja, za potražnju < 0,6: × 0,9.

## 3. Trošak, platforme, zakon

- `trošak = nominalna × (1 + % naknade) + fiksno` (po prodavaču: Ticketmaster 12 %, Eventim 10 % + 1,5 €, Entrio 1,5 €…).
- Za svaku platformu dostupnu u državi: `oglasna = min(očekivana × faktor platforme, zakonski limit, limit platforme)`,
  `neto = oglasna × (1 − naknada prodavatelja) − fiksno`. Faktor platforme: viagogo 1,0, lokalni oglasnik 0,9, Facebook 0,85.
- Zakonski limit iz [`laws.toml`](../karte/data/laws.toml); `--strict` primjenjuje i najavljene limite (DE, UK).

## 4. Vjerojatnost prodaje i očekivana vrijednost

```
P(prodaja) = (0,40 + 0,55 × potražnja) × (0,85 + 0,15 × doseg platforme)
             + 0,08 ako je cijena postavljena prema stvarnim oglasima
             + 0,15 ako je cijena ograničena ispod tržišne      (max 0,97)
bescjenje  = 0,6 × nominalna   (0 ako je ulaznica personalizirana)
EV         = P × neto + (1 − P) × bescjenje − trošak
ROI        = EV / trošak
```

Najbolja platforma = najveći EV umanjen za mali penal rizika platforme (`trust_risk × 5 % troška`).

## 5. Rizik (0–1)

personalizirane ulaznice +0,35 (nepoznato +0,08) · pravni rizik države × 0,5 · niska pouzdanost do +0,2 ·
događaj > 180 dana +0,1 · isplata nakon događaja +0,05 · odgođeno +0,3 · slaba potražnja do +0,2 ·
**događaj u inozemstvu**: `access_risk` tržišta iz [`markets.toml`](../karte/data/markets.toml) × 0,35
(npr. AT 0,08, US 0,35, MX 0,5, JP 0,85).

## 5b. Globalno: savezne države, prodavatelj, lokalni kanali

- Pravila saveznih država/pokrajina (`US-VT`, `CA-ON`…) nadjačavaju državna; država događaja dolazi iz Ticketmastera
  (`venue.state.stateCode`) ili CSV stupca `regija`.
- `--seller-country` (zadano HR): platforme s `seller_countries` (Vivid Seats, SeatGeek, TickPick) se isključuju ako
  tvoja država nije na popisu; navode se u rizicima.
- Lokalni kanali (oglasnici, Facebook) za događaje izvan tvoje države: doseg × 0,35, rizik +0,15.
- Platforme mogu imati pravila po državi (`[x.overrides.US]`), npr. Ticketmaster preprodaja u SAD-u bez limita uz ~10 %.

## 6. Preporuka i količina

| Preporuka | Uvjet |
|---|---|
| **KUPI** | ROI ≥ 30 %, potražnja ≥ 0,6, rizik ≤ 0,5 |
| **RAZMOTRI** | ROI ≥ 10 % |
| **PRESKOČI** | ostalo |
| **RASPRODANO** | primarna prodaja rasprodana — savjet samo za prodaju |
| **ZAKONSKI OGRANIČENO** | država zabranjuje preprodaju radi zarade |
| **NEMA CIJENE** | izvor nema nominalnu cijenu — upiši je u CSV |

Količina: KUPI → 4 (potražnja ≥ 0,75) ili 2; RAZMOTRI → 2; uvijek ≤ limit po kupcu, ≤ 25 % budžeta, zaokruženo na paran broj.

## 7. Kalibracija vlastitim podacima

1. Vodi CSV svojih transakcija: nominalna, trošak, stvarna prodajna cijena, dan prodaje, platforma, potražnja koju je model dao.
2. Nakon 10–20 transakcija usporedi **stvarni multiplikator** (prodajna/nominalna) s modelom po razredima potražnje.
3. Ako model sustavno precjenjuje → smanji `demand_slope` (npr. 1,7 → 1,4); podcjenjuje → povećaj.
4. Ako ti se ulaznice prodaju sporije od P(prodaja) → smanji `p_base`/`p_slope`.
5. Ažuriraj naknade platformi u `platforms.toml` prema onome što stvarno vidiš na ekranu pri objavi oglasa.

Primjer `moj.toml`:
```toml
[resale]
demand_slope = 1.4

[verdict]
buy_roi = 0.4

[primary_fees.vendors]
entrio = { pct = 0.0, fixed = 2.0 }
```
