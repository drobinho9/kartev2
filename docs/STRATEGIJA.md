# Strategija: kako legalno i isplativo preprodavati ulaznice

Praktični priručnik uz aplikaciju `karte`. Temelji se na [ISTRAZIVANJE.md](ISTRAZIVANJE.md).

---

## 1. Model koji ima smisla: „selektivni preprodavač”

| | |
|---|---|
| **Broj događaja** | 5–15 godišnje, ne „sve što se prodaje” |
| **Količina** | 2–4 ulaznice po događaju (parovi), uvijek unutar limita po kupcu |
| **Budžet** | najviše 25 % budžeta u jedan događaj; nikad posuđen novac |
| **Gdje kupuješ** | presale ili prvi sat javne prodaje na službenom prodavaču |
| **Gdje prodaješ** | viagogo (doseg, najviša cijena) + Njuškalo/Facebook (bez naknade, brza isplata) + fan-to-fan platforme kao izlaz bez gubitka |
| **Cilj** | ROI 30–80 % na uspješnim događajima, uz prihvaćanje da će dio događaja biti na nuli ili u minusu |

Zarada dolazi iz **odabira događaja**, ne iz volumena. Profesionalni brokeri imaju softver i kapital; tvoja prednost je
lokalno znanje (regionalne zvijezde, HR presaleovi, festivali i turistička sezona) i disciplina.

## 2. Odabir događaja — kontrolna lista

**Jaki signali (✅)**
- Svjetska zvijezda s **jednim datumom** u regiji (HR/SI/AT/HU) i kratkom europskom turnejom.
- **Oproštajna** turneja (`farewell`), **reunion**, **prvi dolazak** u državu (`first_visit`).
- **Rasprodan prvi datum → dodan drugi** (`added_date`) — ali drugi datum ima manju maržu od prvog.
- Mali kapacitet u odnosu na popularnost (npr. Arena Pula ~7.000, Šalata, Tvornica kulture za jake indie izvođače).
- Ljeto na obali (Pula, Split, Dubrovnik) — turisti plaćaju više i kupuju kasno.
- Regionalne zvijezde s ogromnom lokalnom bazom (Last.fm ih podcjenjuje → koristi oznaku `regional_star`).
- Već postoje oglasi na viagogu/Njuškalu **znatno iznad nominalne** prije javne prodaje → upiši u CSV (`sek_najniza`).

**Crvene zastavice (❌)**
- **Personalizirane ulaznice** (ime na ulaznici, provjera osobne) — možeš ostati s neprodanom ulaznicom.
- Izvođač ima **više datuma u istom gradu** ili cijeloj regiji (velika ponuda).
- **Dinamične cijene** („platinum”/„official resale” po tržišnoj cijeni) — kupuješ već po visokoj cijeni.
- Države s limitom cijene (IE, BE, IT, PT, PL, DK, FR, ES; uskoro DE, UK).
- Nogomet u HR (HNS poništava preprodane ulaznice).
- Događaj za više od 6 mjeseci — kapital dugo zarobljen, rizik otkazivanja.
- Organizator dopušta preprodaju samo preko službene platforme po nominalnoj cijeni.

Aplikacija sve to boduje automatski; ti samo dodaješ lokalno znanje kroz oznake i ručne cijene.

## 3. Kupnja

1. **Pripremi račune unaprijed**: Entrio, Eventim.hr, Ulaznice.hr; za inozemstvo Ticketmaster (AT/DE/HU/CZ/PL…) i Eventim.de/oeticket.
   Spremi karticu, provjeri limit kartice i 3D Secure.
2. **Prijavi se za presale**: newsletter i fan klub izvođača, Live Nation, promotori (u HR npr. organizatori velikih koncerata šalju
   kodove newsletterom), partnerski presaleovi banaka i telekoma. `karte scan` ispisuje presale datume za Ticketmaster događaje.
3. **Virtualni red**: uđi 10–15 min ranije, jedan preglednik, ne osvježavaj. **Bez botova i bez više računa** — zabranjeno (EU/HR).
4. **Što kupiti**:
   - Kod jake potražnje: najjeftinije kategorije s dobrim pogledom i **parter/stajanje** — najveći postotni skok i najbrža prodaja.
   - Kod srednje potražnje: srednje kategorije; izbjegavaj zaklonjena mjesta i skupe VIP pakete (često personalizirani).
   - **Parovi** (2 ili 4) — najtraženiji. Mjesta jedno do drugog.
5. **Maksimalna cijena**: aplikacija za svaki događaj ispisuje „ne plaćaj više od X € po ulaznici” — iznad toga očekivani ROI pada ispod 30 %.
6. **Provjeri uvjete** odmah nakon kupnje: personalizacija, promjena imena (i cijena promjene), način prijenosa (aplikacija, PDF, mobilna ulaznica).

## 4. Prodaja

### 4.1 Gdje
| Situacija | Kanal |
|---|---|
| Svjetski izvođač, strani kupci, maksimalna cijena | **viagogo** (isplata tek nakon događaja) |
| Regionalni izvođač, brzo do novca, bez naknade | **Njuškalo**, Facebook grupe (oprez s prijevarama) |
| Ticketmaster ulaznica koju ne možeš prodati skuplje | **Ticketmaster Fan-to-Fan** (po nominalnoj, bez naknade) |
| Festival / zapadna Europa | **TicketSwap** (max +20 %, brzo i sigurno) |
| Eventim ulaznica (DE/AT) | **fanSALE** |

### 4.2 Kada i po kojoj cijeni
- **Jaka potražnja**: oglasi **odmah nakon rasprodaje** primarne prodaje (prvih 24–72 h cijene su najviše), ~10 % iznad ciljne cijene;
  drži do ~T-14, zatim spuštaj prema cjeniku iz aplikacije.
- **Srednja potražnja**: oglasi **odmah po kupnji**, malo ispod konkurencije; cijene obično padaju prema datumu — ne čekaj zadnji tjedan.
- **Slaba potražnja**: ne kupuj radi preprodaje. Ako imaš višak, prodaj odmah po nominalnoj.
- Uvijek budi **1–3 % ispod najnižeg oglasa iste kategorije** — kupci sortiraju po cijeni.
- **Donja granica (break-even)** = trošak / (1 − naknada platforme). Ispod nje idi tek zadnjih dana (cjenik to predviđa).

### 4.3 Sigurna isporuka i naplata
- Prijenos samo **službenim kanalom** (aplikacija prodavača / promjena imena). Nikad ne prodaj isti PDF/screenshot više puta — to je prijevara.
- Lokalno: uplata na račun **prije** prijenosa ili osobna primopredaja; pazi na lažne „potvrde uplate” i „kurirske” prijevare.
- Ne prodaj ulaznice koje još **nemaš** (spekulativni oglasi) — zabranjeno na većini platformi i u UK zakonu.

## 5. Rizik i kapital

- **Najviše 25 % budžeta po događaju**, raspodijeli na 3–6 događaja s različitim datumima.
- Računaj da je novac s viagoga **zarobljen do događaja** (+ nekoliko dana).
- Planiraj **izlaz** prije kupnje: koja je platforma za izlaz bez gubitka (Fan-to-Fan, TicketSwap) ako potražnja podbaci.
- Otkazivanje: službeni povrat ide kupcu koji je kupio kod prodavača (tebi) — na viagogu se prodaja poništava; drži evidenciju.
- Vodi tablicu svake kupnje i prodaje (`karte scan --format csv` + svoje stvarne cijene) i nakon 10–20 transakcija **kalibriraj model** ([MODEL.md](MODEL.md)).

## 6. Primjer izračuna (Arena Zagreb, jaka potražnja)

| Stavka | Iznos |
|---|---|
| Nominalna cijena (najjeftinija kategorija) | 59,00 € |
| Naknada pri kupnji (Eventim ~10 % + 1,50 €) | 7,40 € |
| **Trošak po ulaznici** | **66,40 €** |
| Očekivana oglasna cijena na viagogu (×2,0) | 120 € |
| Naknada prodavatelja (~15 %) | −18 € |
| **Neto isplata** | **~102 €** |
| **Dobit ako se proda** | **~36 € (+54 %)** |
| Vjerojatnost prodaje (model) | ~86 % |
| Ako se ne proda: prodaja u bescjenje (60 % nominalne) | ~35 € |
| **Očekivana vrijednost po ulaznici** | **~26 € (ROI ~+40 %)** |

Za 2 ulaznice: ulaganje ~133 €, očekivana dobit ~53 €. Isti koncert s **tri datuma** i personaliziranim ulaznicama bio bi u minusu.

## 7. Tjedni radni tok

1. **Pon/čet**: GitHub Actions pokreće `karte scan` (ili ručno) → pregledaj KUPI/RAZMOTRI.
2. Za HR događaje: dopuni `primjeri/moji_dogadaji.csv` (nominalna cijena, najniža cijena na viagogu/Njuškalu, oznake).
3. Za kandidate: provjeri uvjete organizatora (personalizacija!), zabilježi presale datume u kalendar.
4. Dan prodaje: kupi unutar limita i maksimalne cijene.
5. Odmah: objavi oglase prema planu prodaje; postavi podsjetnike za T-30 / T-14 / T-7 iz cjenika.
6. Nakon događaja: upiši stvarnu prodajnu cijenu → kalibracija modela.

## 8. Porezi i pravila

- Jednom kad ovo radiš redovito radi zarade → **obrt** (paušalni) ili d.o.o.; platforme te prijavljuju Poreznoj (DAC7: ≥ 30 prodaja ili > 2.000 €/god.).
- Poštuj zakon države **u kojoj je događaj** (aplikacija upozorava).
- Bez botova, bez lažnih računa, bez spekulativnih oglasa, bez prodaje iste ulaznice dvaput.
