# Što rade preprodavači (forumi i zajednice)

Sažetak onoga što preprodavači i brokeri stvarno rade — iz vodiča brokerskih servisa, opisa plaćenih Discord zajednica,
istraživanja potrošačkih udruga, policijskih kampanja i sudskih presuda (stanje: studeni 2026.).
Reddit nam nije bio izravno dostupan za čitanje, pa su ovdje samo provjerljivi izvori; tvrdnje prodavača alata označene su kao *marketing*.

> **Bitno:** dobar dio „savjeta s foruma” (botovi, više računa, kupljeni presale kodovi) je u EU i UK **protuzakonit**.
> Takve prakse su na dnu stranice označene crvenom zastavicom — nemoj ih kopirati.

## 1. Kako biraju događaje

- **Podaci, ne dojam.** Najčešća greška početnika je kupnja „na osjećaj”: događaj koji se čini uzbudljivim ne znači
  potražnju na preprodaji ([Stage Front](https://stagefront.com/news/how-ticket-brokers-identify-profitable-events),
  [ProTickets](https://protickets.ca/en/blog/how-to-buy-the-best-tickets-to-resell)).
- **Signali koje gledaju:** veličina reda i brzina rasprodaje u presaleu, **stvarne prodajne cijene** usporedivih mjesta
  (ne oglasi), brzina prodaje (sell-through) i **omjer ponude na preprodaji i kapaciteta dvorane**.
- **Rasprodano ≠ isplativo.** Brza rasprodaja je dobar znak tek ako na viagogu nema poplave oglasa — zato aplikacija
  koristi omjer *oglasa / kapacitet* (intenzitet preprodaje) i broj koncerata u istoj državi.
- **Rijetkost:** dodatni datumi nakon rasprodaje (`added_date`), prvi dolazak u zemlju (`first_visit`), oproštajne turneje
  (`farewell`) i mali broj koncerata u regiji — isto što model koristi kao „buzz”.

## 2. Kako dolaze do ulaznica (legalno)

- **Presale je glavni put** do boljih mjesta po nominalnoj cijeni: fan klub izvođača, newsletter, kartični presaleovi
  (American Express, Mastercard…), Verified Fan, presale dvorane ili radija ([SeatGeek](https://seatgeek.com/blog/how-do-concert-presales-work-how-to-get-presale-codes-and-early-access-tickets),
  [Ticketmaster](https://help.ticketmaster.com/hc/en-us/articles/9670692314897-How-do-I-get-a-presale-or-offer-code)).
- **Spotify presale** (npr. Fall Out Boy 2027.) nema javne prijave — pozivnica stiže onima koji slušaju izvođača
  ([SeatGeek](https://seatgeek.ca/blog/fall-out-boy-presale-onsale-resale-guide-how-to-get-twilight-of-the-punks-tour-tickets)).
- **Budi spreman prije početka** (često 10:00 ili 12:00 po lokalnom vremenu), s prijavljenim računom i karticom koja
  odgovara presaleu. Kodovi razlikuju velika i mala slova i ne jamče ulaznicu.
- **Ne kupuj presale kodove** od „prodavača kodova” — pritužbe na povrate su česte, a dijeljenje osobnih kodova krši uvjete.

## 3. Alati za koje plaćaju

| Vrsta | Primjeri (cijene iz njihovih oglasa) | Napomena |
|---|---|---|
| Discord „cook” grupe (monitori, obavijesti o dropovima, presale info, cijene) | 40–200 $/mj. ([Whop](https://whop.com/blog/ticket-reselling-discord-servers/)); Akari £65/mj., Retail.go 1.990 CZK/mj. (monitori za Ticketmaster, AXS, Eventim), Ticketwave 15–77 €/mj. (CZ/SK), TickIO (EU), Insiderz | *marketing*, ocjene su s njihovih stranica; neki nude i **auto-checkout botove** ⛔ |
| Brokerski softver | Skybox (Vivid Seats, autopricer), Lysted (naknada 7–13 % uz ručno/Uptick određivanje cijene, 10–16 % s njihovim timom), Stage Front AutoPricer/Broker Suite, Automatiq Uptick ([Stage Front](https://stagefront.com/news/best-ticket-broker-softwares), [Drew's rate sheet](https://intercom.help/drews-tickets/en/articles/6932561-drew-s-rate-sheet)) | uglavnom za SAD i veći obim |

**Pouka za nas:** analitički dio (koji događaji, do koje cijene kupiti, kad prodati) ova aplikacija radi besplatno;
obavijesti o presaleovima dobiješ besplatno preko newslettera i aplikacija prodavača. Botovi nisu opcija.

## 4. Kako određuju cijenu i kada oglašavaju

- **Cijena prema stvarnim prodajama, ne prema oglasima.** Oglasi odražavaju optimizam prodavača; brokeri kupuju i prodaju
  prema potvrđenim prodajama usporedivih mjesta ([Stage Front 2025](https://stagefront.com/news/2025-in-review-ticket-resale-industry)).
  Ni SeatGeekov tracker za SP 2026. ne mjeri prodaje, nego aktivne oglase ([SeatGeek](https://seatgeek.com/world-cup-ticket-tracker)).
  → U aplikaciji: najniži oglas se umanjuje (kupčeve naknade, „haircut”), a **tvoje stvarne prodaje u *Moje prodaje*** kalibriraju model.
- **Tempo prodaje je strategija:** brže uz nižu cijenu, sporije uz višu ili uravnoteženo (SeatGeek alati nude upravo ta tri načina,
  [TechCrunch](https://techcrunch.com/2024/02/27/seatgeeks-new-tools-help-fans-resell-tickets-at-the-best-price)).
- **Brzina je dio marže:** najduže je stajala roba oglašena na premalo mjesta. Oglasi na 2–3 platforme, ali **odmah povuci ostale oglase**
  kad se proda (inače dvostruka prodaja i kazna).
- **Ulaganje raspodijeli** na više događaja — koncentracija malog kapitala u jedan događaj je najveći rizik ([Stage Front](https://stagefront.com/news/how-to-start-a-ticket-brokering-business)).

## 5. Najčešće greške početnika

1. Kupnja na hype bez provjere broja oglasa i stvarnih cijena.
2. Sav kapital u jedan događaj ili u preskupe (VIP) ulaznice.
3. Ignoriranje ograničenja prijenosa: ulaznice na ime, provjera osobne na ulazu, *will-call*, prijenos tek par dana prije.
4. Oglašavanje ulaznica koje još nemaš (spekulativni oglasi) — viagogo ih skida i traži dokaz kupnje.
5. Zaboravljene naknade (kupnja + prodaja = 25–35 %) i porez.
6. Oglasi na više platformi bez praćenja → ista ulaznica prodana dvaput.

## 6. Prijevare — gdje ljudi gube novac

- **Nizozemska:** policija je na Marktplaatsu objavila lažne oglase za ulaznice da pokaže koliko je prevara lako; vidjelo ih je preko 300.000 ljudi
  (10/2025–1/2026). Godišnje primi ~50.000 prijava internetskih prijevara, od toga ~10 % za ulaznice ([Malwarebytes](https://www.malwarebytes.com/blog/scams/2026/01/dutch-police-sell-fake-tickets-to-show-how-easily-scams-work)).
- **Belgija:** policijska kampanja — provjeri profil prodavača, traži dokaz ulaznice, ne plaćaj pod pritiskom, koristi pouzdane platforme
  ([Brussels Times](https://www.brusselstimes.com/2028482/police-launch-campaign-against-concert-ticket-scams)).
- **UK:** gubici od prevara s ulaznicama za koncerte udvostručili su se 2024. na 1,6 mil. £ ([GOV.UK](https://www.gov.uk/government/news/gig-goers-urged-to-stop-think-fraud-before-buying-tickets));
  prema Lloyds Banku nogomet čini 32 % prijavljenih prevara s ulaznicama ([Bitdefender](https://www.bitdefender.com/en-gb/blog/hotforsecurity/football-ticket-scams-lloyds-bank)).
- **Telegram i grupe na društvenim mrežama** postali su veliko tržište ulaznica za SP 2026. — s lažnim dokazima, recikliranim slikama
  i lažnim komentarima ([Flare](https://flare.io/learn/resources/blog/inside-world-cup-2026-ticket-fraud-operation)).

**Pravilo:** kupuj i prodaj preko platforme s jamstvom ili osobno uz provjeru; nikad PayPal *Friends & Family* nepoznatima;
ulaznicu prenesi tek kad je novac stvarno na računu.

## 7. ⛔ Što NE kopirati s foruma

| Praksa | Zašto ne |
|---|---|
| Botovi i auto-checkout | U EU zabranjena preprodaja ulaznica kupljenih botom (Omnibus), u SAD-u BOTS Act; prodavači poništavaju narudžbe |
| Više računa, tuđa imena, lažne adrese, maskiranje IP-a | **Presuda Hunter & Smith (UK):** 4 godine i 30 mjeseci zatvora — 97 imena, 88 adresa i 290+ e-mail adresa, botovi i preglednik za skrivanje IP-a; kupili ulaznica za 4 mil. £ i prodali za 10,8 mil. £. Osuđeni za prijevarno poslovanje; žalba odbijena 2021. ([Judiciary UK](https://www.judiciary.uk/wp-content/uploads/2022/07/R-v-Hunter-Smith-summary-261121.pdf), [Pollstar](https://news.pollstar.com/2021/12/02/appeals-rejected-prison-sentences-for-ticket-resellers-upheld-in-the-uk/), [National Trading Standards](https://www.nationaltradingstandards.uk/news/pair-jailed-for-secondary-ticketing-fraud)) |
| Kupljeni presale kodovi | krše uvjete, česte prijevare |
| Spekulativni oglasi | zabranjeni (UK, dijelovi SAD-a), kazne platforme |
| Preprodaja personaliziranih ulaznica i ulaznica za utakmice gdje je zabranjeno | poništene ulaznice, zabrane, u UK kazneno djelo (nogomet) |

Organizatori stavljaju spekulante na crne liste i poništavaju ulaznice ponuđene na preprodaji
([Which?](https://www.which.co.uk/news/article/viagogo-and-stubhub-do-you-know-who-youre-really-buying-from-au5b64F4gMRe)).

## 8. Kako to primijeniti u aplikaciji

- **Radar → Snimka stvarnih događaja:** za događaje bez javne nominalne cijene vidiš *Kupi najviše do* — usporedi s cijenom na Eventimu/Entriju.
- **Kalkulator:** upiši nominalnu cijenu i najniži oglas iste kategorije na viagogu (to je tvoj „comp”).
- **Kategorije:** koja kategorija ima najveći postotni skok (parter i jeftina dobra mjesta obično prednjače).
- **Moje prodaje:** svaka prodaja je tvoj stvarni „sold comp” — nakon 5+ prodaja model predlaže kalibraciju.
- **Sigurnosna provjera** u svakom planu pokriva točke iz odjeljaka 5–7.
