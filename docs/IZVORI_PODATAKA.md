# Izvori podataka — kako raditi bez Ticketmastera

Stanje: 22. 11. 2026. Ukratko: **aplikacija sada radi i bez ijednog ključa** (snimka stvarnih događaja + Deezer +
Wikipedia), a najbolja zamjena za Ticketmaster za Hrvatsku i Europu je **Google Events preko SerpApi** (besplatno
250 pretraga mjesečno). Nominalne cijene i cijene s preprodaje u Europi nemaju besplatan javni API — zato aplikacija
za takve događaje računa **do koje se cijene isplati kupiti** (preporuka *PROVJERI CIJENU*).

## 1. Što napraviti danas

| Korak | Što | Ključ |
|---|---|---|
| 1 | `karte gui` ili `karte scan` — bez ključeva automatski se koristi **snimka stvarnih događaja** (Hrvatska, regija, europske turneje 2027.) | ne treba |
| 2 | Registriraj se na [serpapi.com](https://serpapi.com) i upiši `SERPAPI_KEY` u `.env` → živi popis koncerata po gradovima (Zagreb, Split, Pula, Beč, Budimpešta…) | besplatno, 250 pretraga/mj. |
| 3 | (Opcionalno) `LASTFM_API_KEY` za precizniju popularnost — bez njega se koristi Deezer | besplatno, odmah |
| 4 | Za svaki zanimljiv koncert upiši **nominalnu cijenu** i **najnižu cijenu na viagogu** u *Kalkulator* (ili CSV) | — |
| 5 | Ticketmaster: provjeri status ključa prema odjeljku 2 i dodaj ga kad proradi | besplatno |
| 6 | Jednom mjesečno: `karte snimka --osvjezi` (svježi datumi turneja i popularnost) | ne treba |

## 2. Zašto Ticketmaster „ne odobrava” ključ i što napraviti

- **Discovery API (v2) je samoposlužni.** Nakon registracije na [developer.ticketmaster.com](https://developer.ticketmaster.com/)
  u *My Apps* automatski postoji aplikacija s **Consumer Key** — to je ključ za Discovery API (5.000 poziva dnevno,
  5 zahtjeva u sekundi). Prema dokumentaciji i neovisnim vodičima ključ je u pravilu aktivan odmah
  ([Vorp Labs](https://vorplabs.com/agent-tools/ticketmaster-cli), [tickets.dev](https://tickets.dev/guides/ticketmaster-discovery-api),
  [FreeAPIHub](https://freeapihub.com/apis/ticketmaster-discovery)).
- **International Discovery API ne prima nove zahtjeve.** Ticketmaster na svojoj stranici piše *„We are no longer accepting new
  API key requests for the International Discovery API”* i upućuje na Discovery API v2
  ([izvor](https://developer.ticketmaster.com/products-and-docs/apis/international-discovery/v2/)). Ako si zatražio taj proizvod,
  odobrenje neće doći — a ne treba ti: Discovery v2 pokriva i Europu.
- **Partner API, Commerce/Top Picks i Discovery Feed** namijenjeni su distribucijskim partnerima i traže ugovor ili posebno odobrenje
  ([FAQ](https://developer.ticketmaster.com/support/faq/), [Discovery Feed](https://developer.ticketmaster.com/products-and-docs/apis/dc-dataFeeds/)).
  Za ovu aplikaciju dovoljan je obični Consumer Key.

**Koraci:**
1. Prijavi se → *My Apps* → otvori zadanu aplikaciju → kopiraj **Consumer Key** (ne „Consumer Secret”).
2. Provjeri: `karte doctor` ili u pregledniku `https://app.ticketmaster.com/discovery/v2/events.json?size=1&apikey=TVOJ_KLJUČ`.
3. Ako je odgovor 401 ili račun stoji kao *pending*: potvrdi e-mail adresu računa, napravi novu aplikaciju s jasnim opisom
   (npr. „personal event discovery and price research, no resale of data”) i javi se na **devportalinquiry@ticketmaster.com**.
4. Dok čekaš: snimka + SerpApi pokrivaju Hrvatsku i regiju bolje od Ticketmastera (Ticketmaster nema HR/SI/RS/BA tržišta).

> Ne mogu vidjeti tvoj račun — gore su najčešći uzroci. Ako pošalješ točnu poruku koju vidiš, mogu suziti uzrok.

## 3. Usporedba izvora

| Izvor | Ključ / cijena | Pokrivenost | Što daje | U aplikaciji |
|---|---|---|---|---|
| **Snimka stvarnih događaja** (ugrađena) | bez ključa | HR, regija, europski datumi velikih turneja | provjereni događaji s izvorom, „od” cijene s preprodaje uz datum, nominalne gdje su javne, popularnost | ✅ zadano bez ključeva |
| **Wikipedia** — tablice turneja | bez ključa (User-Agent s kontaktom) | velike svjetske turneje | datumi, gradovi, dvorane (bez cijena); ažurno unutar par dana od najave | ✅ `karte snimka --osvjezi` |
| **Wikimedia Pageviews** | bez ključa | svaki izvođač s člankom | trend interesa: zadnjih 14 dana / prethodnih 60 | ✅ signal potražnje |
| **Deezer API** | bez ključa (~50 zahtjeva / 5 s) | globalno, jak u Europi | broj fanova izvođača | ✅ popularnost bez Last.fm-a |
| **Last.fm API** | besplatan ključ, odmah | globalno | broj slušatelja | ✅ |
| **SerpApi — Google Events** | ključ odmah; **250 pretraga/mj. besplatno**, 1.000 za 25 $/mj ([cjenik](https://serpapi.com/pricing), [CostBench](https://costbench.com/software/web-scraping/serpapi/free-plan/)) | globalno, uključujući HR (Google skuplja Eventim, Entrio, Ulaznice.hr, dvorane…) | naziv, datum, dvorana, poveznice na prodavače; **bez cijena**, bez godine u datumu | ✅ beta |
| **PredictHQ** | 14 dana probno, zatim besplatno **samo za spremljene lokacije**; plaćeno po dogovoru (treće strane navode od ~500 $/god.) ([podrška](https://www.predicthq.com/support/learn-about-our-trial-and-free-plan), [docs](https://docs.predicthq.com/getting-started/guides/using-the-api-with-the-free-plan)) | globalno | kategorije, predviđena posjećenost (`phq_attendance`), rang utjecaja | ✅ beta |
| **Ticketmaster Discovery v2** | besplatan ključ (obično odmah) | SAD, Kanada, Meksiko, AU, NZ, UK, IE, dio EU | nominalne cijene, presale datumi, limit po kupcu | ✅ |
| **SeatGeek Platform** | `client_id` (registracija) | uglavnom SAD | statistika oglasa (najniža/medijan, broj); cijene po oglasu traže partnerski pristup ([uvjeti](https://seatgeek.com/api-terms)) | ✅ |
| **Bandsintown** | `app_id` **samo za izvođače i njihove timove**, uz pisani pristanak ([pomoć](https://help.artists.bandsintown.com/en/articles/3372745-can-i-have-access-to-the-api-and-an-app-id-if-i-m-not-an-artist), [uvjeti](https://corp.bandsintown.com/data-applications-terms)) | — | — | ❌ nije za ovu namjenu |
| **Songkick** | zatvoren za nove korisnike | — | — | ❌ |
| **Spotify Web API** | Development Mode od 2026. traži Premium, ograničeni endpointi | — | — | ❌ |
| **Komercijalni podaci o preprodaji** (TicketsData, Eventory, Stage Front Broker Suite, Skybox) | plaćeno | uglavnom SAD | stvarne prodaje („sold comps”), cijene | ❌ tek uz veći obim |
| **Agregatori cijena** (karlobag.eu, SeatPick, Hellotickets, Eventworld, StubHub) | web stranice | globalno | „od” cijene po događaju | ✋ ručno — ne scrapati (uvjeti korištenja) |
| **Entrio / Eventim.hr / Ulaznice.hr** | nema javnog API-ja; zaštita od botova | HR | službene cijene i dostupnost | ✋ ručno ili CSV — ne scrapati |

Aplikacija namjerno **ne** „struže” stranice prodavača i agregatora: to krši njihove uvjete, a prodavači to prepoznaju kao bot
promet (Entrio i Eventim su naše probne automatske zahtjeve odmah odbili ili blokirali).

## 4. Kad nominalna cijena nije poznata: *PROVJERI CIJENU*

Za velik dio stvarnih događaja javno su dostupne samo **„od” cijene s preprodaje**. Aplikacija tada prolazi kroz cijeli model
(naknade kupnje i platformi, zakonski limiti, vjerojatnost prodaje, rizik) s hipotetskom nominalnom cijenom i binarnim
pretraživanjem nalazi:

- **Kupi najviše do** — najviša nominalna cijena uz koju je očekivani ROI ≥ 30 % (`verdict.buy_roi` u `model.toml`),
- **Granica isplativosti** — cijena uz koju je očekivana dobit 0.

Primjeri iz snimke (stanje 22. 11. 2026.):

| Događaj | Najniža na preprodaji (izvor, datum) | Kupi do | Granica |
|---|---|---|---|
| Rod Stewart, Arena Pula, 22. 6. 2027. | 195 € (karlobag.eu, 29. 9. 2026. — stara cijena!) | ~82 € | ~104 € |
| U2, Tottenham Hotspur Stadium, 19. 6. 2027. | £217 (SeatPick) | ~104 € | ~141 € |
| Fall Out Boy, Budimpešta, 19. 5. 2027. | £78 (SeatPick) | ~37 € | ~47 € |
| Laura Pausini, Arena Zagreb, 30. 11. 2027. | 97 $ (eventworld.com) | ~34 € | ~43 € |

Kad vidiš službenu cijenu (npr. na Eventimu), usporedi: ako je ispod „kupi do”, klikni **Upiši nominalnu cijenu → izračun**
za puni plan prodaje. „Od” cijene uključuju kupčeve naknade, mogu biti zastarjele i odnose se na najjeftiniju (često najlošiju)
ulaznicu — aplikacija ih zato umanjuje i upozorava kad su starije od 21 dan.

## 5. Snimka stvarnih događaja

- `karte/data/snimka/dogadaji.csv` — ručno provjereni događaji, svaki s poveznicom na izvor i bilješkom (gdje su druge cijene).
  Nominalne cijene samo iz službenih ili medijskih objava (npr. Fontaines D.C., Šalata: 49 € za prvih 1.500 kupaca, zatim 52 €).
- `turneje.json` — europski datumi turneja (Fall Out Boy, Olivia Rodrigo, U2, Karol G) iz tablica na Wikipediji.
- `popularnost.json` — Deezer fanovi i Wikipedia trend za sve izvođače (npr. Fall Out Boy ×3,0 i U2 ×2,0 zbog najava turneja).

```bash
karte snimka                # pregled snimke
karte snimka --list         # svi događaji iz snimke
karte snimka --osvjezi      # svježe turneje i popularnost → ~/.karte/snimka (ili KARTE_DATA_DIR/snimka)
karte scan --snimka         # procjena (zadano kad nema nijednog ključa za događaje)
```

Vlastite događaje dodaj u `~/.karte/snimka/dogadaji.csv` (predložak nastaje pri prvom osvježavanju) ili učitaj CSV u sučelju.
Oni **dopunjuju** ugrađenu snimku, a redak za isti događaj (izvođač + datum + grad) zamjenjuje ugrađeni — npr. kad saznaš
nominalnu cijenu ili svježu najnižu cijenu na viagogu.
Novi stupci: `sek_valuta` (valuta cijene s preprodaje), `sek_datum` (kad je zabilježena), `fanovi` (Deezer).

**Sport:** u snimci zasad nema utakmica s potvrđenim datumom i cijenom (raspored HNL-a 2026./27. za derbije nije bio
objavljen). Referentne cijene iz prošlih utakmica: Dinamo – Hajduk (Maksimir, 9. 5. 2026.) zapad dolje 25 € za članove /
30 € ostali ([Index](https://www.index.hr/sport/clanak/dinamo-objavio-informacije-o-ulaznicama-za-derbi-s-hajdukom/2787043.aspx));
Hrvatska – Francuska (Poljud, 3/2026.) 50/40/25 €, na dan utakmice +5 €
([Index](https://www.index.hr/sport/clanak/hrvatska-i-francuska-igrat-ce-na-poljudu-hns-je-objavio-cijene-ulaznica/2647766.aspx)).
Za HR klubove vrijede uvjeti kluba (vidi vodič *Nogomet i sport*).

## 6. Ograničenja

- Deezer fanovi ne mjere lokalnu potražnju: Thompson ima ~12 tisuća fanova, a puni stadione → oznaka `regional_star`.
- Wikipedia tablice mogu kasniti ili imati greške; mjerodavan je službeni prodavač.
- SerpApi/Google Events ne daje godinu (izvodi se) ni cijene, a izvođač se izvodi iz naslova.
- PredictHQ i SerpApi parseri napisani su prema službenoj dokumentaciji (oznaka *beta*); Deezer i Wikipedia testirani su na
  stvarnim odgovorima (`tests/fixtures/`).

## Izvori

- Ticketmaster: [International Discovery API v2](https://developer.ticketmaster.com/products-and-docs/apis/international-discovery/v2/) ·
  [FAQ](https://developer.ticketmaster.com/support/faq/) · [Discovery Feed](https://developer.ticketmaster.com/products-and-docs/apis/dc-dataFeeds/) ·
  [Discovery Feed 2.0](https://developer.ticketmaster.com/products-and-docs/apis/discovery-feed/) · [Vorp Labs](https://vorplabs.com/agent-tools/ticketmaster-cli) ·
  [tickets.dev](https://tickets.dev/guides/ticketmaster-discovery-api) · [FreeAPIHub](https://freeapihub.com/apis/ticketmaster-discovery)
- SerpApi: [cjenik](https://serpapi.com/pricing) · [CostBench: besplatni plan](https://costbench.com/software/web-scraping/serpapi/free-plan/)
- PredictHQ: [probni i besplatni plan](https://www.predicthq.com/support/learn-about-our-trial-and-free-plan) ·
  [API uz besplatni plan](https://docs.predicthq.com/getting-started/guides/using-the-api-with-the-free-plan) ·
  [usporedba s Ticketmasterom](https://www.predicthq.com/compare/ticketmaster-vs-predicthq) · [PricingSaaS](https://pricingsaas.com/companies/predicthq)
- Bandsintown: [API samo za izvođače](https://help.artists.bandsintown.com/en/articles/7053475-what-is-the-bandsintown-api) ·
  [nisam izvođač](https://help.artists.bandsintown.com/en/articles/3372745-can-i-have-access-to-the-api-and-an-app-id-if-i-m-not-an-artist) ·
  [Data Application Terms](https://corp.bandsintown.com/data-applications-terms)
- SeatGeek: [API/SDK uvjeti](https://seatgeek.com/api-terms) · [Jentic: limiti](https://jentic.com/apis/seatgeek.com/seatgeek)
- Wikimedia: [Pageviews API](https://wikitech.wikimedia.org/wiki/Analytics/AQS/Pageviews) · [User-Agent pravila](https://meta.wikimedia.org/wiki/User-Agent_policy) ·
  Deezer: [API](https://developers.deezer.com/api)
- Komercijalni podaci: [Eventory: ticket data APIs](https://eventory.ai/best/ticket-data-apis) · [TicketsData](https://ticketsdata.com/) ·
  [Stage Front: broker software](https://stagefront.com/news/best-ticket-broker-softwares)
- Cijene u snimci: [Croatia Week: Rod Stewart Pula](https://www.croatiaweek.com/rod-stewart-final-tour-croatia-pula-arena-2027/) ·
  [karlobag.eu: Rod Stewart](https://karlobag.eu/en/concerts/croatia/pula/rod-stewart-arena-22-june-2027-tgao2/) ·
  [tportal: Fontaines D.C.](https://www.tportal.hr/showtime/clanak/fontaines-d-c-dolaze-u-zagreb-20261026) ·
  [karlobag.eu: Joksimović rasprodan](https://karlobag.eu/en/music/zeljko-joksimovic-sells-out-first-zagreb-arena-concert-with-two-december-shows-o-xl0vy/) ·
  [Novi list: Laura Pausini](https://www.novilist.hr/mozaik/talijanska-zvijezda-laura-pausini-po-prvi-put-u-hrvatskoj/) ·
  [Official Charts: Fall Out Boy](https://www.officialcharts.com/chart-news/fall-out-boy-uk-eu-twilight-of-the-punks-tour-2027-tickets-dates-support-acts/) ·
  [SeatPick: U2 Europa 2027](https://seatpick.com/blog/cheapest-u2-tickets-in-europe-2027-every-city-compared) ·
  [karlobag.eu: Nickelback Beč](https://karlobag.eu/en/concerts/austria/vienna/nickelback-wiener-stadthalle-25-june-2027-a6rar/) ·
  [MVM Dome: Sabaton](https://mvm-dome.hu/en/events/sabaton)
