# karte — radar za preprodaju ulaznica 🎟️

Aplikacija koja **traži koncerte i sportske događaje bilo gdje u svijetu** u idućih 1–2 mjeseca (i događaje kojima **prodaja tek počinje**),
**procjenjuje potencijalnu zaradu** od preprodaje nakon svih naknada i rizika te za svaki događaj daje
**konkretan plan**: kako i kada kupiti, koju kategoriju i količinu, gdje prodati, po kojoj cijeni
i kako spuštati cijenu prema datumu događaja. Uz to provjerava **zakonska ograničenja** po državama i saveznim
državama/pokrajinama (SAD, Kanada, Australija…) te **može li prodavatelj iz Hrvatske uopće kupiti i prodati** na tom tržištu.

> 🆕 **Radi i bez ijednog API ključa** — uz aplikaciju dolazi **snimka stvarnih događaja** (Hrvatska, regija i europski
> datumi velikih turneja 2027., s izvorima i cijenama s preprodaje), popularnost s **Deezera** i trend s **Wikipedije**.
> Ticketmaster ti ne odobrava ključ? Vidi [docs/IZVORI_PODATAKA.md](docs/IZVORI_PODATAKA.md) — uzroci i zamjene
> (najbolja za HR/Europu: Google Events preko SerpApi, besplatno 250 pretraga mjesečno).

> ⚠️ Prije svega pročitaj [docs/ISTRAZIVANJE.md](docs/ISTRAZIVANJE.md) — iskrena analiza tržišta, platformi,
> zakona (Europa, SAD, Kanada, Australija, Azija, Latinska Amerika) i poreza. Ukratko: zarada postoji, ali je
> koncentrirana u malom broju događaja, naknade pojedu 25–35 %, a regulativa se u Europi i dijelu SAD-a postrožuje.

---

## Što aplikacija radi

| Korak | Opis |
|---|---|
| 1. Pretraga | **Bez ključa:** snimka stvarnih događaja + datumi turneja s Wikipedije. **S ključem:** Google Events preko SerpApi (i Hrvatska), Ticketmaster Discovery API (SAD, Kanada, Meksiko, Australija, NZ, UK, IE i većina Europe – ili cijeli svijet odjednom), PredictHQ, SeatGeek (cijene sa sekundarnog tržišta). Uvijek: vlastiti CSV (Entrio, Eventim.hr, Ulaznice.hr nemaju javni API) |
| 2. Obogaćivanje | Popularnost izvođača (Last.fm ili **Deezer bez ključa**), **trend interesa s Wikipedije**, kapacitet dvorane (ugrađena baza), broj koncerata istog izvođača u državi (ponuda), veličina turneje |
| 3. Procjena | Potražnja (0–100), očekivana prodajna cijena, trošak kupnje s naknadama, neto isplata po platformi, vjerojatnost prodaje, očekivana vrijednost, ROI, rizik |
| 4. Pravna provjera | ~40 država + savezne države/pokrajine (US-VT, US-NC, CA-ON, CA-QC…): zabrane iznad nominalne (IE, BE, IT, PT, PL, NO, JP, KR, BR…), limit +10 % (AU, VT…), najavljeni limiti (DE, UK, DC) uz `--strict` |
| 4a. Sport i nogomet | Posebna pravila za nogomet (UK kazneno djelo, HR/DE/ES/NL uvjeti klubova, Italija, Francuska…) i natjecanja (UEFA, FIFA, NFL/NBA u Europi, F1); presuda **UVJETI ZABRANJUJU** + službeni kanal za povrat novca |
| 4b. Pristup tržištu | Može li prodavatelj iz HR prodavati na platformi (Vivid Seats/SeatGeek traže prebivalište u SAD-u), lokalni kanali u inozemstvu, rizik računa/isplata/valute |
| 5. Savjet | **KUPI / RAZMOTRI / PROVJERI CIJENU / PRESKOČI / RASPRODANO / ZAKONSKI OGRANIČENO** + plan kupnje (presale datumi), plan prodaje (platforme, cjenik po datumima), rizici. Kad nominalna cijena nije javna, iz cijena na preprodaji računa **do koje se cijene isplati kupiti** |
| 6. Izvještaj | Terminal, HTML (sortabilna tablica, tamni način), Markdown, CSV, JSON; tjedno automatsko skeniranje preko GitHub Actions |
| 7. Grafičko sučelje | `karte gui` – sve gore navedeno u pregledniku + analiza kategorija, dnevnik prodaja s kalibracijom modela, plan po datumima i podsjetnici u kalendaru, vodiči |

## Brzi početak

```bash
git clone https://github.com/drobinho9/kartev2.git
cd kartev2
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -e .

# Grafičko sučelje (otvara se u pregledniku na http://127.0.0.1:8765)
karte gui
```

Bez ključeva sučelje odmah prikazuje **snimku stvarnih događaja** (izvor podataka možeš promijeniti u prvom polju pretrage).
Za žive podatke kopiraj `.env.example` u `.env` i upiši bar jedan ključ (preporuka: `SERPAPI_KEY`) — vidi
[docs/IZVORI_PODATAKA.md](docs/IZVORI_PODATAKA.md).

## Grafičko sučelje (`karte gui`)

Najlakši način korištenja — sve radi lokalno na tvom računalu (server sluša samo na 127.0.0.1, podaci ostaju kod tebe).

| Kartica | Čemu služi |
|---|---|
| **Radar** | Odabereš izvor (snimka stvarnih događaja / živi API-ji / demo), regiju (ili cijeli svijet), dane i budžet → tablica preporuka (KUPI / RAZMOTRI / PROVJERI CIJENU / …), graf koncerata s najvećim očekivanim skokom cijene ili do koje se cijene isplati kupiti, filtri i sortiranje. Klik na koncert otvara **plan po datumima**: presale, javna prodaja, kada oglasiti i po kojoj cijeni, kada spuštati cijenu. Gumb **📅 Kalendar (.ics)** sve to doda u tvoj kalendar s podsjetnikom 30 min prije prodaje. |
| **Kalkulator** | Za jedan koncert (npr. s Entrija/Eventima) upišeš nominalnu cijenu i najnižu cijenu na viagogu → isplativost, platforme, cjenik. Gumb *Dohvati* uz **Deezer fanove** popuni popularnost i pokaže trend s Wikipedije (bez ključa). |
| **Kategorije** | **Koje ulaznice se najviše isplati preprodati** za isti koncert: parter, tribine, VIP, zaklonjena mjesta… rangirano po očekivanom ROI-ju i zaradi. |
| **Moje prodaje** | Dnevnik kupnji i prodaja (npr. tvoja **A$AP Rocky prodaja na viagogu** – gumb *Primjer*): dobit, ROI, koliko dana prije koncerta prodaješ, po platformi. Iz stvarnih prodaja **kalibrira model** i predlaže podešavanje. Uvoz/izvoz CSV. |
| **Tržišta** | Rang država za prodavača iz HR + pravila po državama i saveznim državama (US-VT, CA-ON…). |
| **Vodiči** | Virtualni redovi (kako najbolje doći do ulaznice), kada kupiti i prodati, viagogo korak po korak, koje karte se najviše preprodaju, **sigurna preprodaja bez kazni** (savjeti prodavača s foruma i iz pritužbi), **nogomet i sport** (kako klubovi prodaju ulaznice i gdje je preprodaja legalna), **što rade preprodavači** (alati, presaleovi, određivanje cijene, prijevare i što ne kopirati). |

![Radar – snimka stvarnih događaja](docs/img/gui_radar.png)
![Provjeri cijenu – do koje cijene se isplati kupiti](docs/img/gui_provjeri.png)
![Plan kupnje i prodaje](docs/img/gui_plan.png)
![Analiza kategorija](docs/img/gui_kategorije.png)
![Sport: nogomet i američke lige](docs/img/gui_sport.png)

## Naredbeni redak

```bash
# 1) Bez ikakvih ključeva: snimka stvarnih događaja (HR, regija, europske turneje 2027.)
karte scan
karte snimka --list            # što je u snimci (izvori, cijene s preprodaje)
karte snimka --osvjezi         # svježi datumi turneja (Wikipedia) i popularnost (Deezer) – bez ključeva

# 2) HTML izvještaj
karte scan --snimka --format html --out izvjestaj.html

# 3) Izmišljeni demo (samo za isprobavanje sučelja)
karte scan --demo
```

Potreban je samo Python 3.11+ — aplikacija **nema vanjskih ovisnosti**.

> **Limiti API-ja kod globalnog skeniranja:** Ticketmaster vraća najviše 1000 rezultata po upitu, pa aplikacija sama dijeli
> razdoblje na manje dijelove (`svijet` za 60 dana ≈ nekoliko stotina poziva od 5000 dnevno). Last.fm se poziva samo za
> najperspektivnijih `--max-artists` izvođača (najprije oni s cijenom i najskupljim ulaznicama). Rezultati se cacheiraju 6 h.

### Pravi podaci (besplatni API ključevi)

```bash
cp .env.example .env     # upiši ključeve
karte doctor             # provjera ključeva
karte scan --days 60 --countries otvoreno --budget 1500 --format html --out izvjestaj.html
karte scan --countries svijet --days 45 --only KUPI,RAZMOTRI          # cijeli svijet
karte scan --countries sjeverna_amerika,GB --category mid             # regije i države zajedno
karte scan --vrsta sport --countries sjeverna_amerika                  # sport (NFL, NBA, MLB, NHL, MLS…)
```

### Gdje se isplati? Regije i rangiranje tržišta

```bash
karte markets --details     # rang država: veličina tržišta × legalnost × dostupnost iz HR
```

| Regija (`--countries`) | Države |
|---|---|
| `otvoreno` (zadano) | HR, SI, AT, HU, CZ, SK, DE, NL, SE, CH, GB, US, RS, BA — bez zakonskog limita i dostupno iz HR |
| `europa`, `zapadna_europa`, `srednja_europa`, `dach`, `benelux`, `nordijske`, `balkan` | europske skupine |
| `sjeverna_amerika`, `latam`, `oceanija`, `azija` | SAD/Kanada/Meksiko, Latinska Amerika, AU/NZ, Azija |
| `svijet` | sva Ticketmaster tržišta odjednom (bez filtra države) |

Države s limitom cijene i dalje se prikazuju, ali kao **ZAKONSKI OGRANIČENO**, pa vidiš i gdje *nemaš* što tražiti.

| Ključ | Gdje | Za što |
|---|---|---|
| *(bez ključa)* | ugrađeno | Snimka stvarnih događaja, Deezer (popularnost), Wikipedia (turneje, trend interesa) |
| `SERPAPI_KEY` | [serpapi.com](https://serpapi.com) — odmah, **250 pretraga/mj. besplatno** | Google Events: koncerti po gradovima, **i Hrvatska/regija** (bez cijena) — najbolja zamjena za Ticketmaster |
| `TICKETMASTER_API_KEY` | [developer.ticketmaster.com](https://developer.ticketmaster.com/) — besplatno, 5000 poziva/dan ([ako ne radi](docs/IZVORI_PODATAKA.md#2-zašto-ticketmaster-ne-odobrava-ključ-i-što-napraviti)) | Događaji, nominalne cijene, presale datumi, limit po kupcu |
| `PREDICTHQ_TOKEN` | [control.predicthq.com](https://control.predicthq.com) — 14 dana probno | Događaji + predviđena posjećenost (beta) |
| `LASTFM_API_KEY` | [last.fm/api/account/create](https://www.last.fm/api/account/create) — odmah, besplatno | Preciznija popularnost izvođača (inače Deezer) |
| `SEATGEEK_CLIENT_ID` | [seatgeek.com/account/develop](https://seatgeek.com/account/develop) — opcionalno | Cijene na sekundarnom tržištu (uglavnom SAD/UK) |
| `KARTE_USER_AGENT` | npr. `karte/0.6 (ime@primjer.hr)` | Wikimedia traži kontakt u User-Agentu |

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
| `sek_valuta`, `sek_datum` | `GBP`, `2026-11-22` | valuta cijene s preprodaje (ako nije ista kao nominalna) i kad je zabilježena (upozorenje nakon 21 dan) |
| `fanovi` | `1467166` | Deezer fanovi (ako nemaš Last.fm slušatelje) |
| `slusatelji`, `prodavac`, `url`, `biljeske` | `1200000`, `eventim` | `prodavac`: `entrio`, `eventim`, `ulaznice_hr`, `ticketmaster` |

## Naredbe

```bash
karte scan [opcije]        # glavna pretraga i rangiranje (bez ključeva: snimka stvarnih događaja)
karte gui                  # grafičko sučelje u pregledniku
karte snimka [--osvjezi] [--list]   # snimka stvarnih događaja: pregled i osvježavanje (bez ključeva)
karte calc --face 59 --resale 140 --country HR --listeners 1500000 --capacity 16000   # brzi kalkulator za jedan događaj
karte kategorije --cat "Parter:59:parter" --cat "Tribina:79" --cat "VIP:189:vip" --venue "Arena Zagreb" --listeners 2000000
karte dnevnik              # statistika mojih prodaja (unos u: karte gui → Moje prodaje)
karte platforms --country US --vendor ticketmaster   # platforme, naknade, limiti, tko prima prodavatelje iz HR
karte laws [--country US-VT]   # pravila po državama i saveznim državama
karte markets --details        # rang tržišta za prodavača iz HR
karte sport --country HR       # nogomet: kako klubovi prodaju ulaznice i što je dopušteno
karte doctor                   # provjera API ključeva i izvora bez ključa
```

Najvažnije opcije za `scan`:

| Opcija | Zadano | Opis |
|---|---|---|
| `--days N` | 60 | koncerti koji se održavaju u idućih N dana |
| `--onsale-days N` | 30 | + koncerti (do 12 mj. unaprijed) kojima prodaja počinje u idućih N dana — **ovdje je najveća prilika** |
| `--countries` | `otvoreno` | ISO kodovi i/ili regije, npr. `US,GB,DE`, `europa`, `svijet` |
| `--seller-country` | `HR` | tvoje prebivalište – koje platforme te primaju i rizik pristupa |
| `--snimka` | uključeno kad nema ključeva | snimka stvarnih događaja umjesto živih API-ja |
| `--gradovi` | glavni gradovi država | gradovi za Google Events (SerpApi), npr. `Zagreb,Split,Vienna:AT` |
| `--no-deezer`, `--no-wikipedia` | — | bez popularnosti s Deezera / trenda s Wikipedije |
| `--max-artists` | 300 | koliko najperspektivnijih izvođača obogatiti Last.fm-om/Deezerom (bitno za `svijet`) |
| `--show-all` | isključeno | prikaži i događaje bez nominalne cijene u izvoru |
| `--vrsta` | `koncerti` | `koncerti`, `sport` ili `sve` |
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

1. *Settings → Secrets and variables → Actions → New repository secret* (sve opcionalno): `SERPAPI_KEY`, `TICKETMASTER_API_KEY`, `PREDICTHQ_TOKEN`, `LASTFM_API_KEY`, `SEATGEEK_CLIENT_ID`. Bez njih se koristi snimka stvarnih događaja.
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
- 🔌 [docs/IZVORI_PODATAKA.md](docs/IZVORI_PODATAKA.md) — **zamjene za Ticketmaster**, zašto ključ nije odobren, usporedba svih izvora, snimka stvarnih događaja
- 🧭 [docs/STRATEGIJA.md](docs/STRATEGIJA.md) — praktični priručnik: odabir događaja, kupnja, prodaja, cijene, rizik, porezi
- 🧮 [docs/MODEL.md](docs/MODEL.md) — kako model radi i kako ga kalibrirati vlastitim podacima
- 🎫 Vodiči (i u kartici *Vodiči*): [virtualni redovi](karte/data/guides/1_redovi.md) · [kada kupiti/prodati](karte/data/guides/2_kada_kupiti_prodati.md) · [viagogo za prodavatelje](karte/data/guides/3_viagogo.md) · [koje karte se najviše preprodaju](karte/data/guides/4_koje_karte.md) · [**sigurna preprodaja bez kazni**](karte/data/guides/5_sigurnost.md) · [**nogomet i sport**](karte/data/guides/6_nogomet_sport.md) · [**što rade preprodavači (forumi i zajednice)**](karte/data/guides/7_sto_rade_preprodavaci.md)

## Struktura projekta

```
karte/
  cli.py            naredbe
  pipeline.py       dohvat → spajanje → obogaćivanje → procjena
  snapshot.py       snimka stvarnih događaja (učitavanje, osvježavanje bez ključeva)
  geo.py            nazivi država → ISO kodovi
  scoring.py        model potražnje, cijene, rizika i preporuke
  advisor.py        savjeti: kupnja, prodaja, cjenik
  categories.py     analiza kategorija (koje ulaznice se najisplativije preprodaju)
  journal.py        dnevnik kupnji/prodaja, statistika, kalibracija modela
  service.py        zajednički sloj za CLI i sučelje
  gui/              lokalni web server + sučelje (HTML/CSS/JS, bez vanjskih biblioteka)
  legal.py          pravila po državama i saveznim državama/pokrajinama
  sport.py          sport/nogomet: prepoznavanje sporta i natjecanja, posebna pravila (sport.toml)
  platforms.py      platforme za preprodaju i naknade
  report.py         terminal / HTML / Markdown / CSV / JSON
  providers/        ticketmaster, serpapi (Google Events), predicthq, seatgeek, lastfm, deezer, wikipedia (turneje, trend), manual (CSV), demo
  data/             laws.toml, markets.toml (regije, pristup), platforms.toml, venues.toml, model.toml, snimka/ (stvarni događaji), demo_events.json, guides/
primjeri/           primjeri CSV-a (uklj. stvarnu HR watchlistu)
docs/               istraživanje, strategija, model
tests/              pytest (bez mreže; fixturei sa stvarnim odgovorima Deezera i Wikipedije)
```

Testovi: `pip install -e ".[dev]" && pytest`

## Pravila igre (važno)

- **Bez botova i bez zaobilaženja limita** (više lažnih računa, tuđi računi). U EU je preprodaja tako kupljenih
  ulaznica zabranjena (Omnibus direktiva; u HR Zakon o zaštiti potrošača, NN 19/22). Aplikacija namjerno **ne** automatizira kupnju.
- **Ne prodaj ono što nemaš** (spekulativni oglasi) i ne prodaj istu ulaznicu više puta.
- Poštuj zakone države (i savezne države) događaja — aplikacija označava mjesta s limitom cijene kao *ZAKONSKI OGRANIČENO*.
- Sustavna preprodaja radi zarade je **gospodarska djelatnost** (obrt/porez), a platforme prijavljuju prodavatelje poreznoj upravi (DAC7).
- Ništa ovdje nije financijski ni pravni savjet; naknade i propisi se mijenjaju — provjeri prije kupnje.

Licenca: MIT
