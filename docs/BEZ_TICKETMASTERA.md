# Radar bez Ticketmastera

Stanje: 25. 11. 2026. Ticketmaster ključ i dalje nije odobren? Aplikaciji više ne treba. Sve što bi nam dao
Ticketmaster Discovery API zamijenjeno je izvorima **bez ključa**. Svaki je dopušten za strojno čitanje ili radi u tvom
pregledniku, na stranici koju si sam otvorio.

| Što bi dao Ticketmaster API | Zamjena u aplikaciji | Ključ |
|---|---|---|
| Popis budućih koncerata | **1. Otkrivanje turneja na Wikipediji:** sve turneje iz kategorija „2026/2027 concert tours” i „Upcoming concert tours”, samo europski datumi. **2. Radar najava (RSS):** hrvatski portali, TicketNews, Pollstar, Ticketmaster UK blog… Uz to snimka i, po želji, Google Events preko SerpApi | ne |
| Datumi presalea i početka prodaje | **Radar najava** čita datume iz teksta najave (presale, opća prodaja, datum koncerta) i nudi podsjetnik u kalendaru | ne |
| Nominalne cijene i status (rasprodano, otkazano, najava) | **3. Gumb „karte: spremi”** u pregledniku. Na stranici događaja koju si otvorio (Ticketmaster, Eventim, Entrio, See Tickets…) pročita podatke koje stranica objavljuje za Google (schema.org/JSON-LD) | ne |
| Cijene na preprodaji | Isti gumb na viagogu, StubHubu ili Ticombu sprema „preprodaja od” s današnjim datumom | ne |
| Popularnost izvođača | Deezer fanovi i trend pregleda na Wikipediji (bilo i prije) | ne |

Ukratko, za tjedan rada bez ijednog ključa:

```bash
karte najave                 # što je novo: turneje, dodatni datumi, presale/prodaja (Hrvatska → Europa)
karte gui                    # kartica "Najave i uvoz": isto + gumb "karte: spremi" + moji događaji
karte snimka --osvjezi       # jednom mjesečno: nove turneje s Wikipedije i svježa popularnost
karte scan                   # procjena svega zajedno (snimka + moji događaji)
```

---

## 1. Otkrivanje turneja (Wikipedia)

`karte snimka --osvjezi` radi ovo:

- Preko Wikipedijinog API-ja dohvati **sve članke** u kategorijama `<tekuća godina> concert tours`,
  `<iduća godina> concert tours` i `Upcoming concert tours` (najavljene turneje koje još nemaju godinu).
- Za svaki članak pročita tablicu datuma, a izvođača iz infookvira. Zadrži **samo buduće datume u Europi**: postavka
  `regija_otkrivanja` u `karte/data/snimka/snimka.toml`, može i `regija` za Hrvatsku i susjede ili `svijet`.
- Članke koji se nisu promijenili (ista revizija) ne dohvaća ponovno. Pamti i turneje bez europskih datuma, da ih
  ne provjerava svaki put.
- Turneju otkrivenu u zadnjih 14 dana označi s **NOVA turneja**.

Uz aplikaciju već dolazi gotova snimka, pa osvježavanje nije nužno odmah. Prvo osvježavanje na novom računalu traje dulje:
Wikipedia ograničava broj zahtjeva u minuti, a aplikacija to poštuje i čeka. Iduća osvježavanja dohvaćaju samo promijenjene članke.

**Ograničenja:** Wikipedia ima samo veće turneje, a članak se pojavi ili dopuni danima do tjednima nakon najave.
Domaći izvođači (Severina, Thompson, Gibonni…) često nemaju tablicu datuma, pa njih pokriva radar najava. Mjerodavan je
uvijek službeni prodavač.

## 2. Radar najava (RSS)

```bash
karte najave                           # zadnjih 21 dan, Hrvatska i susjedi i Europa
karte najave --regija hr --dana 7      # samo Hrvatska, zadnjih tjedan dana
karte najave --regija sve --top 80     # i ostatak svijeta
karte najave --bez-deezera             # brže, bez provjere izvođača na Deezeru
karte najave --izvori                  # popis izvora (ugrađeni + moji)
karte najave --dodaj-izvor URL --naziv "Arena Zagreb (Google Alerts)"   # svoj RSS izvor
```

Isto je u sučelju, u kartici **Najave i uvoz**: filtri, oznaka **NOVO** za stavke koje još nisi vidio,
gumb **📅 Podsjetnik** (.ics, 30 min prije presalea ili prodaje) i gumb **Kalkulator** koji prenese izvođača i grad.

Što radar izvlači iz svake najave:

| Podatak | Kako |
|---|---|
| Izvođač | iz naslova („Foo Fighters stižu u Zagreb”, „Fall Out Boy announce…”), potvrđen na Deezeru s brojem fanova; ako nije pravi izvođač („Novi festival”), ne prikazuje se |
| Mjesto | gradovi i dvorane (Arena Zagreb, Tvornica kulture, Stožice, Štark Arena, MVM Dome…) → ocjena regije: Hrvatska 3, susjedi 2, Europa 1 |
| Presale | datum uz riječi *presale, pretprodaja, fan klub, članovi, Amex, Verified Fan…* |
| Opća prodaja | datum uz riječi *ulaznice, u prodaji, on sale, general sale, tickets go on…* (s vremenom ako piše „u 10 sati”, „at 10am”) |
| Datum koncerta | datum uz riječi *koncert, nastup, održat će se, plays, show, tour…* |

Najave su poredane po regiji, poznatom datumu prodaje i popularnosti izvođača. Ugrađeni izvori su u
[`karte/data/najave.toml`](../karte/data/najave.toml): muzika.hr, Croatia Week, Ajme.hr, tportal, Novi list, TicketNews,
Pollstar, Ticketmaster UK blog i Consequence.

**Svoji izvori i Google Alerts.** Najkorisniji vlastiti izvor je Google Alerts, jer prati bilo koji pojam:

1. Na [google.com/alerts](https://www.google.com/alerts) upiši upit, npr. `"Arena Zagreb" ulaznice`, `presale Beč koncert`
   ili `"Live Nation Croatia"`.
2. *Prikaži opcije* → *Isporuči na:* **RSS feed** (ako je izbornik siv, prvo postavi *Koliko često: kako se dogodi*)
   → *Izradi upozorenje*.
3. Desni klik na ikonu RSS → kopiraj adresu → u aplikaciji **Najave i uvoz → Dodaj svoj izvor**, ili
   `karte najave --dodaj-izvor ADRESA --naziv "Arena Zagreb"`.

Isto vrijedi za RSS bilo kojeg portala, kluba ili dvorane. Izvori se spremaju u `~/.karte/najave.toml` i dopunjuju ugrađene.
Opći izvori se filtriraju ključnim riječima (koncert, ulaznice, tour…). Uz `--samo-koncerti` zadržavaju se sve stavke izvora.

Zašto RSS: to je format namijenjen strojnom čitanju i sindikaciji. Aplikacija ne struže stranice. Svaki izvor dohvaća najviše
jednom u dva sata (predmemorija) i ne šalje ništa osim običnog zahtjeva za feed.

**Ograničenja:** datumi se prepoznaju iz teksta, pa ponekad pogrešno. Prije kupnje otvori najavu (poveznica je uz svaku
stavku). Vrijeme je lokalno vrijeme iz članka: 10:00 u britanskoj najavi je 11:00 u Hrvatskoj. Portali koji ne objave
datum prodaje u prvom odlomku neće ga imati ni u radaru.

## 3. Uvoz sa stranice: gumb „karte: spremi”

1. `karte gui` → **Najave i uvoz** → povuci gumb **karte: spremi** u traku oznaka preglednika.
2. Otvori stranicu događaja kod prodavača (Ticketmaster, Eventim, Entrio, See Tickets, AXS…) ili na preprodaji (viagogo,
   StubHub, Ticombo…) i klikni oznaku.
3. Otvori se aplikacija s pročitanim podacima: naziv, izvođač, datum i vrijeme, dvorana, grad, država, cijene, status i
   početak prodaje. Provjeri ih, dopuni i klikni **Spremi u Moje događaje**.

Gumb čita podatke koje stranice za ulaznice objavljuju za Google (schema.org `Event` u JSON-LD obliku: `startDate`,
`location`, `offers` s `price`/`lowPrice`/`highPrice`, `priceCurrency`, `availability`, `validFrom`, `eventStatus`). Google te
podatke koristi za prikaz događaja u pretrazi, pa ih velike stranice za ulaznice obično imaju. Nemaju ih sve, a sadržaj se
razlikuje od stranice do stranice.

- Na stranici **prodavača** cijene se spremaju kao **nominalne** (`cijena_min`/`cijena_max`, uz `prodavac`).
- Na stranici **preprodaje** spremaju se kao **„preprodaja od”** (`sek_najniza`, `sek_izvor`, `sek_datum` = danas).
- `validFrom` u budućnosti znači da je događaj **najavljen**, pa se sprema i početak prodaje.
  `SoldOut` znači **rasprodano**, `EventCancelled` znači **otkazano**.
- Spremljeno ide u `~/.karte/snimka/dogadaji.csv` i odmah ulazi u snimku, Radar i Plan zarade. Isti događaj (izvođač, datum,
  grad) se **dopunjuje**: prvo spremiš nominalnu cijenu s Eventima, zatim „preprodaja od” s viagoga, i aplikacija ima sve za
  pravu procjenu umjesto *PROVJERI CIJENU*.

Bez gumba: spremi stranicu (Ctrl+S, „Web stranica, cijela”) i pokreni:

```bash
karte uvoz stranica.html --url https://www.eventim.hr/event/...   # --url: s koje je domene stranica (prodavač ili preprodaja)
karte uvoz stranica.html --dry-run                                  # samo prikaži što bi se spremilo
```

**Sigurnost i privatnost:**

- Gumb radi **samo kad ga ti klikneš** i čita samo stranicu koja je već otvorena. Prodavaču ne šalje nijedan dodatni zahtjev,
  a podatke šalje jedino tvojoj aplikaciji na tvom računalu (127.0.0.1).
- Aplikacija ne sprema ništa dok ne klikneš **Spremi**, pa tuđa stranica ne može tiho upisati događaj u tvoj popis.
  Zahtjeve za spremanje i brisanje s drugih stranica sučelje odbija.
- Ako preglednik blokira skočni prozor, gumb kopira podatke u međuspremnik. Zalijepi ih u **Najave i uvoz → Zalijepi**.
- Chrome od verzije 142 traži dopuštenje kad javna stranica šalje zahtjeve prema lokalnoj mreži. Pravilo pokriva `fetch()`,
  dohvat resursa i okvire (iframe). Gumb otvara aplikaciju kao novu karticu, što na tom popisu nije. Ako preglednik ipak pita,
  dopusti ili koristi lijepljenje.

## 4. Što je ostalo od prije

- **Snimka stvarnih događaja** (provjereni HR i europski događaji s izvorima i cijenama s preprodaje).
- **Deezer** (fanovi) i **Wikimedia** (trend pregleda), bez ključa.
- **SerpApi / Google Events** (250 pretraga mjesečno besplatno). Najbolja živa zamjena za popis događaja po gradovima,
  uključujući Hrvatsku.
- **PredictHQ**, **SeatGeek**, **Last.fm** i **vlastiti CSV**, sve opisano u [IZVORI_PODATAKA.md](IZVORI_PODATAKA.md).
- **Ticketmaster**: kad ključ proradi, samo ga upiši u `.env`. Sve gore nastavlja raditi uz njega.

## 5. Tjedni ritam bez ključeva

| Kada | Što | Gdje |
|---|---|---|
| Ponedjeljak i četvrtak | Nove najave u regiji: tko dolazi, kad je presale | `karte najave` ili sažetak tjednog GitHub Actions izvođenja |
| Odmah nakon najave | Stranica prodavača → **karte: spremi** (nominalne cijene, početak prodaje) → 📅 podsjetnik | preglednik + Najave i uvoz |
| Isti dan | Ista ili slična ranija turneja na viagogu/StubHubu → **karte: spremi** (cijena preprodaje) | preglednik |
| Prije presalea | Radar / Plan zarade: KUPI · RAZMOTRI · PROVJERI CIJENU (do koje cijene se isplati) | `karte scan` / `karte plan` |
| Jednom mjesečno | Nove turneje s Wikipedije i svježa popularnost | `karte snimka --osvjezi` |

## 6. Što smo odbacili i zašto

| Ideja | Zašto ne |
|---|---|
| Struganje stranica Ticketmastera, Eventima, Entrija | Krši uvjete korištenja, a zaštita od botova to prepoznaje (Entrio i Eventim odbili su naše probne automatske zahtjeve). Gumb čita samo stranicu koju si sam otvorio. |
| Neslužbeni Ticketmaster endpointi | Protivno uvjetima, nestabilno, rizik blokade računa |
| Bandsintown API | `app_id` samo za izvođače i njihove timove |
| Songkick API | zatvoren za nove korisnike |
| setlist.fm API | besplatan **samo za nekomercijalne projekte** (preprodaja radi zarade to nije), a daje setliste **prošlih** koncerata, bez budućih datuma i cijena |
| Komercijalni podaci o preprodaji | plaćeno i uglavnom za SAD. Isplati se tek uz veći obim. |

## Izvori

- Google Search Central: [Event structured data](https://developers.google.com/search/docs/appearance/structured-data/event):
  Event, Offer, `validFrom`, `availability`, `eventStatus`
- Chrome: [Local Network Access, novi zahtjev za dopuštenje](https://developer.chrome.com/blog/local-network-access) ·
  [vodič za Local Network Access](https://developer.chrome.com/docs/modern-web-guidance/guides/security/local-network-access)
- Wikipedia: [Category:2027 concert tours](https://en.wikipedia.org/wiki/Category:2027_concert_tours) ·
  [Category:Upcoming concert tours](https://en.wikipedia.org/wiki/Category:Upcoming_concert_tours) ·
  [MediaWiki API: categorymembers](https://www.mediawiki.org/wiki/API:Categorymembers) ·
  [User-Agent pravila](https://meta.wikimedia.org/wiki/User-Agent_policy)
- Google Alerts kao RSS: [How-To Geek: RSS feed iz Google Alerta](https://www.howtogeek.com/444549/how-to-create-an-rss-feed-from-a-google-alert/) · [Feeder: Google Alerts](https://feeder.co/help/rss/add-google-alerts-to-feeder/)
- RSS izvori: [muzika.hr](https://www.muzika.hr/category/turneje/) · [TicketNews: tour dates](https://www.ticketnews.com/category/tour-dates/) ·
  [Pollstar: tour announcements](https://news.pollstar.com/category/tour-announcements/) ·
  [Ticketmaster UK Discover](https://discover.ticketmaster.co.uk/category/music/) · [Croatia Week](https://www.croatiaweek.com/category/entertainment/)
- setlist.fm: [API](https://api.setlist.fm/) (besplatno samo za nekomercijalne projekte) · [API Terms of Use](https://www.setlist.fm/help/api-terms)
- Ostali odbačeni izvori (Bandsintown, Songkick, Spotify): vidi [IZVORI_PODATAKA.md](IZVORI_PODATAKA.md), odjeljak 3
