# Kako zaraditi: plan za 2026./2027.

Konkretan plan zarade na temelju istraživanja tržišta (studeni 2026.), stvarnih cijena iz snimke i modela aplikacije.
Iskreno na početku: **zarada postoji, ali je koncentrirana u malom broju događaja**, naknade pojedu velik dio razlike,
a profesionalci s botovima (koje ne kopiramo) uzimaju najveći dio kolača. Pametan pristup je malo dobro odabranih događaja,
strogo upravljanje kapitalom i legalna tržišta.

## 1. Koliko se realno zarađuje

| Izvor | Što kaže |
|---|---|
| [Which?](https://www.which.co.uk/policy-and-insight/article/how-much-could-resellers-make-from-summer-2026-events-azmpv0j8FoFv) (2026.) | Preprodavači bi na 66 izvođača (UK, travanj–rujan 2026.) mogli zaraditi gotovo **24 mil. £** (StubHub 13,3 mil., viagogo 10,2 mil.); profesionalci 18,5 mil. £. Na viagogu 129.443 oglasa, na StubHubu 61.032. Ekstremi: BTS 450 £ → 4.872 £, Ariana Grande 135 £ → 2.832 £. *Mjereno po oglasima, ne prodajama – viagogo tvrdi da se puno prodaje po nominalnoj ili nižoj cijeni.* |
| [Vanderbilt](https://www.axios.com/local/nashville/2026/08/25/second-hand-ticket-fees-cost-billion) (kolovoz 2026.) | U Sjevernoj Americi preprodajne marže ~4,5 mlrd. $ godišnje; procjene marže brokera ~41–49 % (metodologija osporavana). |
| [US Senat PSI](https://www.blumenthal.senate.gov/newsroom/press/release/so-casually-cruel-new-psi-report-reveals-how-ticketmasters-monopoly-supercharges-prices-and-fees-for-consumers) (ožujak 2026.) | Na jednoj turneji marže **fanova-preprodavača bile su veće od brokerskih** – brokeri prodaju brže i jeftinije. |
| [ITV](https://www.itv.com/news/2026-09-24/three-ticket-touts-responsible-for-75-of-1600-listings-investigation), [Irish Times](https://irishtimes.com/culture/music/2026/11/14/one-tout-2000-u2-tickets-and-a-potential-1m-pay-day/) | Tri preprodavača drže 75 % od 1.600 oglasa (Manchester); jedan preprodavač nudi 2.000+ ulaznica za U2 London (~1 mil. £) – to je razina botova i lažnih računa, **nezakonito u EU** i nije naš model. |
| Brokerske stranice ([Stage Front](https://stagefront.com/news/how-much-do-ticket-flippers-make), [TicketFlipping](https://ticketflipping.com/blog/can-you-make-money-reselling-tickets-honest-numbers-for-2026/)) | Tipična marža 10–30 %; povremeni preprodavači zarade od nekoliko stotina do nekoliko tisuća dolara godišnje (*izvori imaju interes da zvuče optimistično*). |

**Realan cilj za početak:** s 500–1.000 € i 6–10 dobro odabranih događaja u sezoni — nekoliko stotina eura godišnje,
uz stvaran rizik gubitka na pojedinim događajima. Više od toga traži više kapitala, vremena i tolerancije rizika.

## 2. Pravilo palca: koliko iznad nominalne mora biti preprodaja

Kupac na viagogu vidi cijenu s naknadama (~20 %), tebi platforma uzme ~10–15 %, a kod kupnje platiš naknadu prodavaču
(npr. Eventim ~10 % + 1,5 €). Iz parametara modela (najjeftinija kategorija, viagogo, realna vjerojatnost prodaje):

| Najniži oglas na viagogu (ukupna cijena kupca) | Što znači |
|---|---|
| < **~1,9 ×** nominalne | očekivani gubitak – ne kupuj radi preprodaje |
| **~1,9 – 2,4 ×** | mala, rizična zarada (RAZMOTRI od ~2,2 ×) |
| ≥ **~2,5 ×** | ROI 30 % i više (KUPI), ako je potražnja jaka i rizik prihvatljiv |

*Provjereno u aplikaciji (Kalkulator, ulaznica 60 €, Eventim naknade): 1,85 × → −5 %, 2,0 × → +4 %, 2,2 × → +16 %, 2,5 × → +36 %.*

Bez naknada (Njuškalo, Facebook) prag je niži, ali je doseg manji, a rizik prijevare veći.
Aplikacija to računa za svaki događaj; kad nominalna cijena nije javna, pokazuje **„kupi najviše do”** (PROVJERI CIJENU).

## 3. Pet načina zarade

### A. Presale na otvorenim tržištima (glavna strategija)
Kupuješ u presaleu ili prvih minuta javne prodaje (po nominalnoj cijeni, unutar limita, s jednog računa) događaje gdje je
potražnja veća od ponude, i prodaješ na viagogu/StubHubu ili lokalno.

**Signali:** brza rasprodaja prvog datuma i dodatni datum (`added_date`), prvi dolazak ili prvi nakon desetljeća (`first_visit`),
oproštajna turneja (`farewell`), velik izvođač u maloj dvorani, jedan datum u široj regiji, rastući interes (trend s Wikipedije).

**Primjer iz snimke — Scorpions & Europe, Arena Zagreb, 12. 6. 2027.** (prvi koncert u Zagrebu nakon 37 godina;
[cijene: Index.hr](https://www.index.hr/magazin/clanak/scorpions-i-europe-stizu-u-zagreb-2027-objavljene-su-cijene-ulaznica/2852356.aspx)):

| | Iznos |
|---|---|
| Parter B (nominalna) | 58 € → s naknadom ~61,90 € |
| Očekivana prodajna (model, bez podataka s preprodaje) | ~107 € (×1,85) → neto na viagogu ~91 € |
| Vjerojatnost prodaje | ~83 % |
| Očekivana vrijednost | **+19,6 € po ulaznici (ROI +32 %)** → KUPI |
| Plan (budžet 1.000 €) | 4 ulaznice = 248 €, očekivano **+78 €**; 90 % simulacija između −48 € i +191 €, vjerojatnost gubitka 17 % |
| Cjenik | odmah 118 € → T-30 107 € → T-14 99 € → T-7 91 € → T-2 73 € (break-even) |

⚠️ To je **procjena modela** (Deezer popularnost, kapacitet, oznake) — za Zagreb još nema cijena na preprodaji, a turneja 2027.
objavljena je nakon odgode koncerata 2026. Prije kupnje provjeri viagogo (poveznice u aplikaciji) i uvjete prijenosa ulaznica.

### B. Regionalna arbitraža
Velika imena u regiji često imaju **niže nominalne cijene** nego u zapadnoj Europi, a na viagogu ulaznice kupuju i fanovi iz
inozemstva (cijene u £/$/€). Najbolje kad je to **jedini datum u široj regiji**.
- U2 2027.: najjeftinija ulaznica u Berlinu od £116, London £200–217 ([SeatPick](https://seatpick.com/blog/cheapest-u2-tickets-in-europe-2027-every-city-compared)).
- Iste arena turneje u Portugalu i do 40 % jeftinije nego u Austriji ([Wanderu](https://www.wanderu.com/blog/cheap-concert-tickets-europe/)).
- Eric Clapton u Zagrebu 5. 5. 2027. — prvi put nakon 48 godina; ostali datumi u regiji: Sofija 7. 5., Budimpešta 10. 5.

**Protuprimjer — Bryan Adams, prosinac 2026.:** Ljubljana 12. 12., Prag 13. 12., Budimpešta 16. 12. — tri koncerta u 5 dana,
preprodaja od ~79 € (Ljubljana) i ~£84 (Budimpešta). Aplikacija: kupi najviše do **32–38 €**, a nominalne su više → **preskoči**.
Ponuda ubija maržu.

### C. Domaće zvijezde i dodatni datumi
Regionalne zvijezde rasprodaju Arenu (Joksimović: prvi koncert rasprodan, preprodaja od 75 €; Seka Aleksić treći datum;
Severina 15. 12. nakon dvije rasprodane Arene). Prodaja ide i lokalno (Njuškalo bez naknade), ali marže su manje,
kupci su osjetljivi na cijenu, a prijevare česte — novac na račun prije prijenosa ili osobna primopredaja.

### D. Partnerski (affiliate) kanal — zarada bez zalihe
Ako imaš publiku (Instagram, TikTok, Telegram, web), objavljuj nadolazeće koncerte i gdje kupiti, s partnerskim poveznicama:
StubHub ~**4 %** od vrijednosti narudžbe (Partnerize, kolačić 30 dana), viagogo ~**4–10 %** (najčešće navođeno ~7 %)
([Partnerize: StubHub](https://partnerize.com/resources/blog/stubhub-affiliate-program-spotlight-and-sign-up-information),
[pregled stopa](https://ecomobi.com/viagogo-affiliate-program/)). Primjer: 2.000 klikova mjesečno × 2 % kupnji × 150 € × 5 % ≈ **300 €/mj.**
Bez rizika zalihe i legalno svugdje — ali poveznice moraš jasno označiti kao partnerske i ne smiješ zavaravati o cijenama.

### E. Sport — samo gdje je legalno
U europskom nogometu preprodaja je uglavnom zabranjena zakonom ili uvjetima klubova (vodič *Nogomet i sport*).
SP 2026. pokazao je i suprotan rizik: cijene na preprodaji naglo su pale u zadnjih 30 dana.

## 4. Upravljanje kapitalom

- Najviše **25 % budžeta po događaju**, ulaznice **u parovima**, 6–10 događaja u sezoni.
- **30–50 % rezerve** za nove najave i presaleove (najbolje prilike dolaze iznenada).
- Pazi na zarobljeni kapital: viagogo isplaćuje **nakon događaja** → novac uložen u lipanj 2027. vraća se tek tada.
- Raspon ishoda je velik: kartica **Plan zarade** (ili `karte plan`) simulira 4.000 ishoda i pokazuje vjerojatnost gubitka.
- Izlaz: prema cjeniku; kod slabije potražnje prodaj do break-evena najkasnije T-7 dana.

## 5. Kada kupiti i kada prodati

- Kupnja: presale ili prvi sat javne prodaje; poslije rasprodaje kupnja na preprodaji radi preprodaje rijetko se isplati.
- Prodaja: analiza 307.000 prodaja na 2.292 koncerta (SeatData, 2026.) — **medijan cijene najniži 90+ dana prije** (139 $),
  **najviši 2–4 tjedna prije** (162 $), a nagli pad tek zadnjih 1–2 dana ([SeatData](https://seatdata.io/articles/best-time-to-buy-concert-tickets-2026/)).
  Za rasprodane hitove oglasi odmah nakon rasprodaje; za ostale ciljaj prozor 2–4 tjedna prije koncerta.
- StubHub: kod slabije potražnje cijene padaju pred koncert, kod rasprodanih se drže ([StubHub](https://newsroom.stubhub.com/2026/09/28/the-psychology-of-ticket-pricing-why-prices-fluctuate/)).

## 6. Karta tržišta za prodavača iz Hrvatske (2026./2027.)

| Status | Države | Napomena |
|---|---|---|
| Otvoreno | HR, SI, HU, CZ, SK, AT, SE, CH, RS, BA | nema zakonskog limita cijene; vrijede uvjeti organizatora i zabrana botova |
| Otvoreno, ali se zatvara | GB (koncerti) | zabrana preprodaje iznad nominalne najavljena, nacrt zakona — realno **2027.–2028.** ([TicketNews](https://www.ticketnews.com/2026/05/uk-ticket-resale-price-cap-reportedly-pushed-back-as-debate-over-consumer-harm-intensifies/)) |
| Otvoreno do limita | DE | najavljen limit ~+20 %; sudovi priznaju zabrane u uvjetima ako dopuštaju do ~25 % |
| Ograničeno platformom | NL (TicketSwap +20 %), UK fanSALE (+10 %) | viagogo bez limita, ali pazi na uvjete |
| Samo nominalna / zabranjeno | IT, BE, IE, PL, PT, FR (bez dopuštenja), DK, NO | ne kupuj radi preprodaje |

## 7. Gdje kupiti po nominalnoj cijeni (strani prodavači)

| Država | Službena prodaja | Napomena |
|---|---|---|
| UK / IE | Ticketmaster, AXS, See Tickets, DICE | DICE se ne može preprodati (samo lista čekanja); Ticketmaster preprodaja samo po nominalnoj |
| DE / AT / CH | Eventim (oeticket, Ticketcorner), Ticketmaster | fanSALE je službena preprodaja; česte personalizirane ulaznice |
| HU | Live Nation HU, jegy.hu, Funcode | naknada se prikazuje odvojeno (tipično 2–10 %) |
| CZ / SK | Ticketmaster CZ, Ticketportal, GoOut, Live Nation CZ | cijene rastu nakon spajanja platformi (PLG) |
| SI / RS | Eventim, Moje karte, Entrio / Tickets.rs, Eventim | |
| PL | eBilet, Going., Ticketmaster PL | preprodaja iznad nominalne zabranjena |
| IT | TicketOne, Vivaticket | ulaznice na ime za događaje > 5.000 posjetitelja |
| ES / FR / NL | Ticketmaster, Entradas.com, El Corte Inglés / Fnac, Ticketmaster / Ticketmaster NL | provjeri pravila države |

U aplikaciji svaki događaj ima gumbe **„Provjeri cijene i dostupnost”** — pretragu na službenim stranicama države,
platformama za preprodaju (viagogo, StubHub, Ticombo, Gigsberg, TicketSwap…), usporedbama (SeatPick, Stereoboard, karlobag.eu)
i lokalnom oglasniku (Njuškalo, willhaben, Jófogás, Bolha…).

## 8. Čega se čuvati

- **Previše ponude:** više datuma u regiji u kratkom razdoblju (Bryan Adams) → preprodaja oko nominalne.
- **Zastarjele cijene:** „od” cijena iz rujna (Rod Stewart, 195 €) nije današnja — aplikacija upozorava nakon 21 dan.
- **Neprenosive ulaznice:** DICE, personalizirane ulaznice, prijenos tek par dana prije koncerta.
- **Botovi, više računa, lažni identiteti:** kazneni progon (Hunter & Smith) i poništene ulaznice — nikad.
- **Plaćene Discord grupe** prije nego imaš vlastiti proces — 40–200 $ mjesečno brzo pojede zaradu.

## 9. Prvih 30 dana (prema snimci od 22. 11. 2026.)

1. Postavi `.env`: `SERPAPI_KEY` (besplatno), `KARTE_USER_AGENT`; pokreni `karte plan`. Ticketmaster ključ nije potreban
   (vidi *Radar bez Ticketmastera*): dvaput tjedno pogledaj **Najave i uvoz** (`karte najave`) i povuci gumb **karte: spremi**
   u traku oznaka — njime spremaš nominalne cijene s Eventima/Ticketmastera i „preprodaja od” s viagoga.
2. **Scorpions Zagreb** (KUPI po modelu): provjeri viagogo i uvjete Core Eventa; najviše 4 ulaznice; oglas tek kad ih imaš.
3. **Eric Clapton Zagreb**: pogledaj cijene na eventim.hr i upiši najjeftiniju kategoriju u Kalkulator (potražnja 75/100).
4. **Rod Stewart Pula**: provjeri današnju najnižu cijenu na viagogu; isplati se samo uz nominalnu ≤ ~82 €.
5. **Bryan Adams (prosinac)**: preskoči.
6. Registriraj se za presale obavijesti: Live Nation (HU, CZ, AT), Eventim, Core Event, Entrio, Arena Zagreb, O2 Arena Prag, MVM Dome.
7. Ako imaš publiku: prijavi se u partnerske programe (Partnerize) i objavljuj tjedni pregled koncerata u regiji.
8. Svaku kupnju i prodaju upiši u *Moje prodaje* — nakon 5+ prodaja model se kalibrira prema tvojim stvarnim rezultatima.
