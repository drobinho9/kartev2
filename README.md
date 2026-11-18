# karte — radar za preprodaju ulaznica 🎟️

Aplikacija koja **traži koncerte** u idućih 1–2 mjeseca (i koncerte kojima **prodaja tek počinje**),
**procjenjuje potencijalnu zaradu** od preprodaje nakon svih naknada i rizika te za svaki događaj daje
**konkretan plan**: kako i kada kupiti, koju kategoriju i količinu, gdje prodati, po kojoj cijeni
i kako spuštati cijenu prema datumu događaja. Uz to provjerava **zakonska ograničenja** po državama.

> ⚠️ Prije svega pročitaj [docs/ISTRAZIVANJE.md](docs/ISTRAZIVANJE.md) — iskrena analiza tržišta, platformi,
> zakona (HR/EU/UK/DE) i poreza. Ukratko: zarada postoji, ali je koncentrirana u malom broju događaja,
> naknade pojedu 25–35 %, a regulativa se u Europi stalno postrožuje.

---

## Što aplikacija radi

| Korak | Opis |
|---|---|
| 1. Pretraga | Ticketmaster Discovery API (većina zapadne/srednje Europe), SeatGeek (cijene sa sekundarnog tržišta), ručni CSV za Hrvatsku/regiju (Entrio, Eventim.hr, Ulaznice.hr nemaju javni API) |
| 2. Obogaćivanje | Last.fm popularnost izvođača, kapacitet dvorane (ugrađena baza), broj koncerata istog izvođača u državi (ponuda), veličina turneje |
| 3. Procjena | Potražnja (0–100), očekivana prodajna cijena, trošak kupnje s naknadama, neto isplata po platformi, vjerojatnost prodaje, očekivana vrijednost, ROI, rizik |
| 4. Pravna provjera | Pravila po državama (zabrana iznad nominalne cijene u IE/BE/IT/PT/PL…, najavljeni limiti u DE i UK uz `--strict`), EU zabrana botova |
| 5. Savjet | **KUPI / RAZMOTRI / PRESKOČI / RASPRODANO / ZAKONSKI OGRANIČENO** + plan kupnje (presale datumi), plan prodaje (platforme, cjenik po datumima), rizici |
| 6. Izvještaj | Terminal, HTML (sortabilna tablica, tamni način), Markdown, CSV, JSON; tjedno automatsko skeniranje preko GitHub Actions |

![Primjer HTML izvještaja](docs/img/izvjestaj.png)

## Brzi početak

```bash
git clone https://github.com/drobinho9/kartev2.git
cd kartev2
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .

# 1) Isprobaj bez ikakvih ključeva (izmišljeni demo podaci)
karte scan --demo

# 2) HTML izvještaj
karte scan --demo --format html --out izvjestaj.html
```

Potreban je samo Python 3.11+ — aplikacija **nema vanjskih ovisnosti**.

### Pravi podaci (besplatni API ključevi)

```bash
cp .env.example .env     # upiši ključeve
karte doctor             # provjera ključeva
karte scan --days 60 --countries AT,DE,HU,CZ,PL --budget 1500 --format html --out izvjestaj.html
```

| Ključ | Gdje | Za što |
|---|---|---|
| `TICKETMASTER_API_KEY` | [developer.ticketmaster.com](https://developer.ticketmaster.com/) — odmah, besplatno, 5000 poziva/dan | Događaji, nominalne cijene, presale datumi, limit po kupcu |
| `LASTFM_API_KEY` | [last.fm/api/account/create](https://www.last.fm/api/account/create) — odmah, besplatno | Popularnost izvođača (signal potražnje) |
| `SEATGEEK_CLIENT_ID` | [seatgeek.com/account/develop](https://seatgeek.com/account/develop) — opcionalno | Cijene na sekundarnom tržištu (uglavnom SAD/UK) |

### Hrvatska i regija: ručni CSV

Ticketmaster ne pokriva HR/SI/RS/BA, a Entrio/Eventim.hr/Ulaznice.hr nemaju javni API. Zato događaje upisuješ
u CSV (Excel/Google Sheets → *Spremi kao CSV*) — najbolje **s najnižom cijenom koju vidiš na viagogu ili Njuškalu**,
jer je to najjači signal:

```bash
karte scan --csv primjeri/dogadaji.csv --countries HR
karte scan --csv primjeri/hr_watchlist_2026-11.csv --countries HR,AT,HU   # stvarni nadolazeći koncerti – dopuni cijene
```

Stupci (hrvatski ili engleski nazivi, razdjelnik `,` ili `;`):

| Stupac | Primjer | Napomena |
|---|---|---|
| `izvodjac`, `datum` | `Rod Stewart`, `2027-06-22` | **obavezno** (datum i kao `22.06.2027.`) |
| `naziv`, `dvorana`, `grad`, `drzava`, `vrijeme` | `Arena Pula`, `Pula`, `HR`, `21:00` | kapacitet poznatih dvorana se dopunjava sam |
| `cijena_min`, `cijena_max`, `valuta` | `45`, `95`, `EUR` | nominalne cijene (bez naknada) |
| `status` | `u prodaji` / `najava` / `rasprodano` / `odgođeno` / `otkazano` | |
| `prodaja_od`, `presale_naziv`, `presale_od` | `2026-12-05 10:00` | za događaje kojima prodaja tek počinje |
| `kapacitet`, `limit`, `personalizirano` | `7000`, `6`, `ne` | personalizirane ulaznice = veliki rizik |
| `oznake` | `farewell\|first_visit` | `farewell`, `reunion`, `first_visit`, `added_date`, `anniversary`, `regional_star`, `new_album` |
| `sek_najniza`, `sek_medijan`, `sek_izvor` | `140`, `190`, `ručno (viagogo)` | cijena koju vidi kupac; za Njuškalo upiši `Njuškalo` u `sek_izvor` |
| `slusatelji`, `prodavac`, `url`, `biljeske` | `1200000`, `eventim` | `prodavac`: `entrio`, `eventim`, `ulaznice_hr`, `ticketmaster` |

## Naredbe

```bash
karte scan [opcije]        # glavna pretraga i rangiranje
karte calc --face 59 --resale 140 --country HR --listeners 1500000 --capacity 16000   # brzi kalkulator za jedan događaj
karte platforms --country HR   # platforme za preprodaju, naknade, limiti
karte laws [--country DE]      # pravila po državama
karte doctor                   # provjera API ključeva
```

Najvažnije opcije za `scan`:

| Opcija | Zadano | Opis |
|---|---|---|
| `--days N` | 60 | koncerti koji se održavaju u idućih N dana |
| `--onsale-days N` | 30 | + koncerti (do 12 mj. unaprijed) kojima prodaja počinje u idućih N dana — **ovdje je najveća prilika** |
| `--countries` | iz `.env` | ISO kodovi, npr. `HR,SI,AT,HU,DE` |
| `--budget` | 1000 | ukupni budžet; u jedan događaj ide najviše 25 % |
| `--category` | `cheap` | `cheap` / `mid` / `premium` — koju kategoriju ciljaš |
| `--strict` | isključeno | primijeni i najavljene limite (DE +20 %/max +20 €, UK nominalna cijena) |
| `--csv FILE` | — | dodaj ručne događaje (može više puta) |
| `--only KUPI,RAZMOTRI` | — | filtriraj preporuke |
| `--model FILE` | — | vlastiti parametri modela ([docs/MODEL.md](docs/MODEL.md)) |
| `--format` / `--out` | `table` | `table`, `html`, `md`, `csv`, `json` |

## Automatsko skeniranje na GitHubu

Workflow [`.github/workflows/scan.yml`](.github/workflows/scan.yml) pokreće skeniranje svakog **ponedjeljka i četvrtka**
(i ručno: *Actions → Tjedni radar ulaznica → Run workflow*). Izvještaji (HTML/MD/CSV/JSON) se spremaju kao *artifact*,
a sažetak preporuka KUPI/RAZMOTRI vidi se izravno na stranici izvođenja.

1. *Settings → Secrets and variables → Actions → New repository secret*: `TICKETMASTER_API_KEY`, `LASTFM_API_KEY` (opcionalno `SEATGEEK_CLIENT_ID`).
2. Za svoje HR događaje dodaj `primjeri/moji_dogadaji.csv` — workflow ga automatski uključuje.

## Kako se računa isplativost (ukratko)

```
trošak        = nominalna × (1 + naknada kupnje) + fiksna naknada
oček. prodaja = nominalna × multiplikator        (iz stvarnih oglasa ako postoje, inače iz potražnje)
neto          = min(oček. prodaja × faktor platforme, zakonski/platformski limit) × (1 − naknada prodavatelja)
oček. vrij.   = P(prodaja) × neto + (1 − P) × prodaja u bescjenje − trošak
ROI           = oček. vrij. / trošak
```

**KUPI** = ROI ≥ 30 %, potražnja ≥ 60, rizik ≤ 50. **RAZMOTRI** = ROI ≥ 10 %. Sve je objašnjeno i podesivo u
[docs/MODEL.md](docs/MODEL.md) i `karte/data/model.toml`.

## Dokumentacija

- 📊 [docs/ISTRAZIVANJE.md](docs/ISTRAZIVANJE.md) — tržište, platforme i naknade, zakoni po državama, porezi u HR, slični projekti i alati, izvori podataka
- 🧭 [docs/STRATEGIJA.md](docs/STRATEGIJA.md) — praktični priručnik: odabir događaja, kupnja, prodaja, cijene, rizik, porezi
- 🧮 [docs/MODEL.md](docs/MODEL.md) — kako model radi i kako ga kalibrirati vlastitim podacima

## Struktura projekta

```
karte/
  cli.py            naredbe
  pipeline.py       dohvat → spajanje → obogaćivanje → procjena
  scoring.py        model potražnje, cijene, rizika i preporuke
  advisor.py        savjeti: kupnja, prodaja, cjenik
  legal.py          pravila po državama
  platforms.py      platforme za preprodaju i naknade
  report.py         terminal / HTML / Markdown / CSV / JSON
  providers/        ticketmaster, seatgeek, lastfm, manual (CSV), demo
  data/             laws.toml, platforms.toml, venues.toml, model.toml, demo_events.json
primjeri/           primjeri CSV-a (uklj. stvarnu HR watchlistu)
docs/               istraživanje, strategija, model
tests/              pytest (bez mreže)
```

Testovi: `pip install -e ".[dev]" && pytest`

## Pravila igre (važno)

- **Bez botova i bez zaobilaženja limita** (više lažnih računa, tuđi računi). U EU je preprodaja tako kupljenih
  ulaznica zabranjena (Omnibus direktiva; u HR Zakon o zaštiti potrošača, NN 19/22). Aplikacija namjerno **ne** automatizira kupnju.
- **Ne prodaj ono što nemaš** (spekulativni oglasi) i ne prodaj istu ulaznicu više puta.
- Poštuj zakone države događaja — aplikacija označava države s limitom cijene kao *ZAKONSKI OGRANIČENO*.
- Sustavna preprodaja radi zarade je **gospodarska djelatnost** (obrt/porez), a platforme prijavljuju prodavatelje poreznoj upravi (DAC7).
- Ništa ovdje nije financijski ni pravni savjet; naknade i propisi se mijenjaju — provjeri prije kupnje.

Licenca: MIT
