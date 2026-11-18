# Koje ulaznice i koji koncerti se najviše preprodaju

## Koji koncerti

Najveći skok cijene imaju koncerti gdje je **potražnja puno veća od ponude**:

- svjetska zvijezda s **jednim datumom** u regiji i kratkom turnejom;
- **oproštajne** i **reunion** turneje, **prvi dolazak** u državu;
- **mali kapacitet** u odnosu na popularnost (npr. jak izvođač u Tvornici kulture ili Areni Pula);
- prvi datum **rasprodan** u minutama → dodan drugi;
- ljeto na obali (turisti kupuju kasno i plaćaju više).

U aplikaciji to mjere **Potražnja (0–100)** i **očekivani multiplikator** (prodajna / nominalna cijena).
Graf *„Najveći očekivani skok cijene”* u tabu Radar pokazuje top koncerte.

**Intenzitet preprodaje**: ako upišeš broj oglasa na viagogu (`sek_broj_oglasa` u CSV-u ili polje u kalkulatoru),
aplikacija računa **oglase kao % kapaciteta**. Puno oglasa uz visoku cijenu = vruće tržište; puno oglasa uz cijene
blizu nominalne = prezasićeno (preprodavači se natječu, cijena pada).

## Koje kategorije (za isti koncert)

| Kategorija | Postotni skok | Brzina prodaje | Napomena |
|---|---|---|---|
| **Najjeftinije s dobrim pogledom** | najveći | najbrža | najmanji kapital, najviše kupaca |
| **Parter / stajanje blizu bine, golden circle** | velik | brza | fanovi plaćaju za blizinu |
| Sjedeće – standard | srednji | srednja | |
| Tribina / gornji prsten | manji | srednja | |
| **VIP paketi / hospitality** | najmanji (%) | spora | velik kapital, često personalizirani |
| **Zaklonjeni pogled** | mali | spora | izbjegavaj |

Tab **Kategorije** računa ovo za tvoj koncert: upišeš kategorije i nominalne cijene (i, ako ih vidiš, najniže cijene
po kategoriji na viagogu) — aplikacija rangira kategorije po očekivanom ROI-ju i zaradi po ulaznici i kaže koje izbjegavati.

Kako računa (kad nema stvarnih cijena po kategoriji): multiplikator koncerta × `(cijena kategorije / medijan)^-0,35`
× faktor vrste (prednji sektor 1,15, parter 1,10, tribina 0,95, VIP 0,85, zaklonjeno 0,75); jeftinije kategorije
dobivaju i nešto veću vjerojatnost prodaje. Stvarne cijene s viagoga uvijek imaju prednost.

## Pravila palca

- **Parovi** se prodaju najbrže; neparan broj ostavlja „siroče” koje se teško prodaje.
- **Mjesta uz prolaz**, prvi redovi sektora i sredina parternog dijela vrijede više.
- Kod jako skupih koncerata kupci traže **ulaz** — najjeftinija kategorija se rasproda prva i na sekundarnom tržištu.
- Kategorije koje organizator **naknadno pušta** (novi blokovi) obaraju cijenu toj kategoriji.
