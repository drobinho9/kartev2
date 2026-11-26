# Radar – rano upozorenje na događaje koji će poskupjeti

Zarada od preprodaje nastaje u prvim satima: kad je turneja najavljena, prije i tijekom presalea. Radar svaka 3 sata
provjeri izvore, svakom događaju i najavi da **hype score 0–100** i na Telegram pošalje samo ono što je **novo ili se
promijenilo**.

```
izvori ──► događaji + najave ──► hype score + „zašto” ──► usporedba sa stanjem ──► Telegram
(snimka, Ticketmaster, raspored,      (model potražnje,        (radar_stanje.json:       ★ 82/100 · NOVO
 RSS najave, cijene s preprodaje)      rijetkost, trend,        što je već javljeno,      Scorpions – Arena Zagreb
                                       preprodaja, prodaja)     povijest ocjena)          Kupi 4 kom … Zašto: …
```

## Kada stiže obavijest

| Vrsta | Uvjet |
|---|---|
| **NOVO** | događaj koji prije nije viđen, ocjena ≥ prag (zadano 70) |
| **NAJAVA** | nova vijest iz RSS izvora (muzika.hr, Croatia Week, Pollstar…) s ocjenom ≥ prag – često prije bilo kakve cijene |
| **RASTE** | ocjena je prešla prag (npr. objavljen dodatni datum, skok interesa na Wikipediji) |
| **KUPI** | preporuka je postala KUPI (npr. objavljena nominalna cijena) |
| **CIJENA** | najniža cijena na preprodaji porasla ≥ 25 % |
| **PRODAJA USKORO** | presale ili javna prodaja počinje za manje od 48 h (jednom po terminu) |

Prvo pokretanje šalje najviše 5 najboljih događaja i 5 najava, da te ne zatrpa.

## Hype score (objašnjiv model)

| Signal | Bodovi |
|---|---|
| Potražnja iz modela (popularnost izvođača, kapacitet dvorane, broj koncerata u regiji, turneja) | do 55 |
| Prvi put u državi, oproštajna turneja, reunion | +10 |
| Dodatni datum (prvi rasprodan) | +12 |
| Interes na Wikipediji raste (zadnja 2 tjedna / prije) | do +12 |
| Preprodaja iznad nominalne (×1,5 i više) | do +15 (spekulativni oglasi samo +3) |
| Prodaja počinje za ≤ 14 dana | +8 |
| Presuda modela: KUPI / RAZMOTRI / PROVJERI CIJENU | +15 / +7 / +6 |
| Najava: fanovi na Deezeru, Hrvatska/regija, datum presalea, riječi „rasprodano”, „dodatni koncert”, „prvi put” | do 100 |

Svaka obavijest ispisuje razloge („Zašto: prvi put u državi; potražnja 79/100; preprodaja od 195 €”).

**Kalibracija:** stanje radara pamti povijest ocjena, presuda i cijena na preprodaji za svaki događaj. Kad se skupi
30–50 događaja s poznatim ishodom (stvarna cijena 1–2 tjedna nakon početka prodaje, iz *Moje prodaje* ili ručne
provjere), težine se mogu podesiti tako da ocjena predviđa stvarni skok cijene (logistička regresija na istim signalima).

## Postavljanje

1. **Telegram bot:** u Telegramu otvori @BotFather → `/newbot` → kopiraj token u `.env` kao `TELEGRAM_BOT_TOKEN`.
2. Pošalji svom botu bilo koju poruku (npr. `/start`).
3. `karte telegram --chat-id` → redak `TELEGRAM_CHAT_ID=…` upiši u `.env`.
4. `karte telegram --test` → stiže probna poruka.
5. Probaj lokalno: `karte radar` (samo ispis) ili `karte radar --posalji`.
6. **Automatski (GitHub Actions):** u repozitoriju *Settings → Secrets and variables → Actions* dodaj
   `TELEGRAM_BOT_TOKEN` i `TELEGRAM_CHAT_ID` (po želji `TICKETMASTER_API_KEY`, `LASTFM_API_KEY`, `API_FOOTBALL_KEY`).
   Workflow `.github/workflows/radar.yml` radi svaka 3 sata i kad je računalo ugašeno; ručno: *Actions → Radar → Run workflow*.
   Prag i države: varijable `KARTE_RADAR_PRAG` (zadano 70) i `KARTE_RADAR_DRZAVE` (zadano `otvoreno`).

## Nogomet uz rizik

Utakmice na kojima preprodaju zabranjuju **samo uvjeti kluba/UEFA-e** (HNL, Bundesliga, LaLiga, Liga prvaka…) računaju se
uz šansu poništenja ulaznice (25 % + 15 % ako je na ime + 5 % u HR) i kaznu platforme (20 % oglasne cijene). Ako je i
tada isplativo, presuda je **RIZIČNO** i ulaze samo u poseban paket *Nogomet – visok rizik* (najviše 20 % budžeta).
Zakonske zabrane (UK, Francuska, Portugal – kazneno djelo; Italija, Belgija, Poljska, Irska – ne iznad nominalne) se nikad
ne računaju kao prilika. Isključi s `KARTE_NOGOMET_RIZIK=0`.

## API-ji koji radaru najviše pomažu

| API | Što dodaje radaru | Cijena |
|---|---|---|
| Ticketmaster Discovery | najave s točnim datumima presalea i prodaje (najbolji okidač) | besplatno |
| SerpApi | Google Events (novi događaji po gradovima), Google Trends | 250 pretraga/mj. besplatno – zato samo u tjednom skeniranju |
| YouTube Data API v3 | rast pregleda novih spotova (signal potražnje) | besplatno, 10.000 jedinica/dan – planirano |
| Last.fm, Deezer, Wikimedia | popularnost i trend interesa | besplatno – ugrađeno |
| API-Football | HNL, nokaut faze, ždrijebovi | 100 zahtjeva/dan besplatno – ugrađeno |
| Telegram Bot API | obavijesti | besplatno – ugrađeno |
| Chartmetric / Soundcharts | profesionalni podaci o izvođačima (Spotify, TikTok, radio) | plaćeno – opcija |
| tickets.dev / TicketsData | žive cijene s preprodaje → automatsko mjerenje ishoda za kalibraciju | plaćeno – opcija |
