"""Nogomet: klubovi, derbiji i jasna analiza utakmica (može li se kupiti, smije li se preprodati, kako kupiti).

Pravila preprodaje su u sport.toml (sport.py). Ovdje je samo znanje o klubovima koje treba za raspored
utakmica iz javnih izvora bez ključa (fixturedownload.com) ili API-Footballa: kojoj državi klub pripada,
je li „veliki” klub, koji parovi su derbiji i gdje hrvatski klubovi prodaju ulaznice.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from karte.util import normalize


@dataclass(frozen=True)
class Club:
    name: str
    country: str
    city: str = ""
    big: bool = False  # klub čije utakmice redovito traže puno više ulaznica nego što ih ima
    aliases: tuple[str, ...] = ()  # normalizirani nazivi; "=x" znači samo točno podudaranje
    tickets: str = ""  # službena prodaja (samo gdje je provjereno)


def _c(name, country, city="", big=False, aliases=(), tickets="") -> Club:
    return Club(name, country, city, big, tuple(aliases), tickets)


# Redoslijed je važan: specifičniji nazivi prije općenitijih (npr. Espanyol prije Barcelone).
CLUBS: list[Club] = [
    # ---------------------------------------------------------------- Hrvatska
    _c("Dinamo Zagreb", "HR", "Zagreb", aliases=("gnk dinamo", "dinamo zagreb", "=dinamo"), tickets="https://tickets.gnkdinamo.hr"),
    _c("Hajduk Split", "HR", "Split", aliases=("hajduk",), tickets="https://hajduk.mojekarte.hr"),
    _c("Rijeka", "HR", "Rijeka", aliases=("hnk rijeka", "=rijeka", "nk rijeka")),
    _c("Osijek", "HR", "Osijek", aliases=("osijek",)),
    _c("Lokomotiva Zagreb", "HR", "Zagreb", aliases=("lokomotiva zagreb", "=lokomotiva")),
    _c("Varaždin", "HR", "Varaždin", aliases=("varazdin",)),
    _c("Slaven Belupo", "HR", "Koprivnica", aliases=("slaven",)),
    _c("Istra 1961", "HR", "Pula", aliases=("istra",)),
    _c("Gorica", "HR", "Velika Gorica", aliases=("hnk gorica", "=gorica")),
    _c("Šibenik", "HR", "Šibenik", aliases=("sibenik",)),
    _c("Vukovar 1991", "HR", "Vukovar", aliases=("vukovar",)),
    # ---------------------------------------------------------------- regija
    _c("Crvena zvezda", "RS", "Beograd", big=True, aliases=("crvena zvezda", "red star belgrade", "=red star")),
    _c("Partizan", "RS", "Beograd", aliases=("partizan",)),
    _c("Celje", "SI", "Celje", aliases=("celje",)),
    _c("Olimpija Ljubljana", "SI", "Ljubljana", aliases=("olimpija",)),
    _c("Maribor", "SI", "Maribor", aliases=("maribor",)),
    _c("Borac Banja Luka", "BA", "Banja Luka", aliases=("borac",)),
    _c("Zrinjski", "BA", "Mostar", aliases=("zrinjski",)),
    _c("Ferencváros", "HU", "Budimpešta", aliases=("ferencvaros",)),
    _c("Salzburg", "AT", "Salzburg", aliases=("salzburg",)),
    _c("Sturm Graz", "AT", "Graz", aliases=("sturm graz",)),
    _c("Rapid Wien", "AT", "Beč", aliases=("rapid wien", "rapid vienna")),
    _c("Austria Wien", "AT", "Beč", aliases=("austria wien", "austria vienna", "fk austria")),
    _c("LASK", "AT", "Linz", aliases=("lask",)),
    _c("Slavia Praha", "CZ", "Prag", aliases=("slavia praha", "slavia prague")),
    _c("Sparta Praha", "CZ", "Prag", aliases=("sparta praha", "sparta prague")),
    _c("Viktoria Plzeň", "CZ", "Plzeň", aliases=("viktoria plzen",)),
    _c("Slovan Bratislava", "SK", "Bratislava", aliases=("s bratislava", "slovan bratislava")),
    # ---------------------------------------------------------------- Engleska i Škotska
    _c("Arsenal", "GB", "London", big=True, aliases=("arsenal",)),
    _c("Chelsea", "GB", "London", big=True, aliases=("chelsea",)),
    _c("Liverpool", "GB", "Liverpool", big=True, aliases=("liverpool",)),
    _c("Manchester City", "GB", "Manchester", big=True, aliases=("man city", "manchester city")),
    _c("Manchester United", "GB", "Manchester", big=True, aliases=("man utd", "manchester united", "man united")),
    _c("Tottenham", "GB", "London", big=True, aliases=("spurs", "tottenham")),
    _c("Newcastle", "GB", "Newcastle", big=True, aliases=("newcastle",)),
    _c("Everton", "GB", "Liverpool", aliases=("everton",)),
    _c("Aston Villa", "GB", "Birmingham", aliases=("aston villa",)),
    _c("Celtic", "GB", "Glasgow", big=True, aliases=("celtic",)),
    _c("Rangers", "GB", "Glasgow", big=True, aliases=("=rangers", "rangers fc", "glasgow rangers")),
    # ---------------------------------------------------------------- Njemačka
    _c("Bayern München", "DE", "München", big=True, aliases=("bayern",)),
    _c("Borussia Dortmund", "DE", "Dortmund", big=True, aliases=("dortmund",)),
    _c("Bayer Leverkusen", "DE", "Leverkusen", big=True, aliases=("leverkusen",)),
    _c("RB Leipzig", "DE", "Leipzig", aliases=("leipzig",)),
    _c("Schalke 04", "DE", "Gelsenkirchen", aliases=("schalke",)),
    _c("VfB Stuttgart", "DE", "Stuttgart", aliases=("stuttgart",)),
    _c("Eintracht Frankfurt", "DE", "Frankfurt", aliases=("eintracht frankfurt",)),
    _c("Hamburger SV", "DE", "Hamburg", aliases=("hamburger sv", "=hamburg")),
    # ---------------------------------------------------------------- Španjolska
    _c("Espanyol", "ES", "Barcelona", aliases=("espanyol",)),
    _c("Real Madrid", "ES", "Madrid", big=True, aliases=("real madrid",)),
    _c("Atlético Madrid", "ES", "Madrid", big=True, aliases=("atleti", "atletico de madrid", "atletico madrid")),
    _c("Barcelona", "ES", "Barcelona", big=True, aliases=("barcelona",)),
    _c("Sevilla", "ES", "Sevilla", aliases=("sevilla",)),
    _c("Real Betis", "ES", "Sevilla", aliases=("real betis", "=betis")),
    _c("Villarreal", "ES", "Villarreal", aliases=("villarreal",)),
    _c("Real Sociedad", "ES", "San Sebastián", aliases=("real sociedad",)),
    _c("Athletic Club", "ES", "Bilbao", aliases=("athletic club", "athletic bilbao")),
    # ---------------------------------------------------------------- Italija
    _c("Inter", "IT", "Milano", big=True, aliases=("internazionale", "=inter", "inter milan", "fc internazionale")),
    _c("Milan", "IT", "Milano", big=True, aliases=("=milan", "ac milan")),
    _c("Juventus", "IT", "Torino", big=True, aliases=("juventus",)),
    _c("Napoli", "IT", "Napulj", big=True, aliases=("napoli",)),
    _c("Roma", "IT", "Rim", big=True, aliases=("=roma", "as roma")),
    _c("Lazio", "IT", "Rim", aliases=("lazio",)),
    _c("Atalanta", "IT", "Bergamo", aliases=("atalanta",)),
    # ---------------------------------------------------------------- Francuska
    _c("Paris Saint-Germain", "FR", "Pariz", big=True, aliases=("paris saint germain", "=paris", "=psg", "paris sg")),
    _c("Marseille", "FR", "Marseille", big=True, aliases=("marseille",)),
    _c("Lyon", "FR", "Lyon", aliases=("olympique lyonnais", "=lyon")),
    _c("Monaco", "FR", "Monaco", aliases=("monaco",)),
    _c("Lille", "FR", "Lille", aliases=("lille", "losc")),
    _c("Lens", "FR", "Lens", aliases=("rc lens", "=lens")),
    # ---------------------------------------------------------------- ostali
    _c("Benfica", "PT", "Lisabon", big=True, aliases=("benfica",)),
    _c("Porto", "PT", "Porto", big=True, aliases=("=porto", "fc porto")),
    _c("Sporting CP", "PT", "Lisabon", big=True, aliases=("sporting cp", "sporting lisbon", "=sporting")),
    _c("Braga", "PT", "Braga", aliases=("braga",)),
    _c("Ajax", "NL", "Amsterdam", big=True, aliases=("ajax",)),
    _c("PSV", "NL", "Eindhoven", big=True, aliases=("psv",)),
    _c("Feyenoord", "NL", "Rotterdam", big=True, aliases=("feyenoord",)),
    _c("AZ Alkmaar", "NL", "Alkmaar", aliases=("az alkmaar",)),
    _c("Twente", "NL", "Enschede", aliases=("twente",)),
    _c("Galatasaray", "TR", "Istanbul", big=True, aliases=("galatasaray",)),
    _c("Fenerbahçe", "TR", "Istanbul", big=True, aliases=("fenerbahce",)),
    _c("Beşiktaş", "TR", "Istanbul", big=True, aliases=("besiktas",)),
    _c("Trabzonspor", "TR", "Trabzon", aliases=("trabzonspor",)),
    _c("Olympiacos", "GR", "Pirej", big=True, aliases=("olympiacos", "olympiakos")),
    _c("Panathinaikos", "GR", "Atena", big=True, aliases=("panathinaikos",)),
    _c("AEK Atena", "GR", "Atena", aliases=("aek athens", "aek")),
    _c("Club Brugge", "BE", "Brugge", aliases=("club brugge",)),
    _c("Anderlecht", "BE", "Bruxelles", aliases=("anderlecht",)),
    _c("Union SG", "BE", "Bruxelles", aliases=("union sg", "union saint gilloise")),
    _c("Copenhagen", "DK", "Kopenhagen", aliases=("copenhagen", "kobenhavn")),
    _c("Midtjylland", "DK", "Herning", aliases=("midtjylland",)),
    _c("Nordsjælland", "DK", "Farum", aliases=("nordsjaelland", "nordsjalland")),
    _c("Sint-Truiden", "BE", "Sint-Truiden", aliases=("sint truidense", "sint truiden")),
    _c("Rennes", "FR", "Rennes", aliases=("rennes", "stade rennais")),
    _c("Thun", "CH", "Thun", aliases=("=thun", "fc thun")),
    _c("Hapoel Beer-Sheva", "IL", "Beer Sheva", aliases=("beer sheva",)),
    _c("Lincoln Red Imps", "GI", "Gibraltar", aliases=("red imps",)),
    _c("NEC Nijmegen", "NL", "Nijmegen", aliases=("n e c", "nec nijmegen")),
    _c("Sunderland", "GB", "Sunderland", aliases=("sunderland",)),
    _c("Shakhtar", "UA", "", aliases=("shakhtar",)),
]

# Derbiji: (naziv, klub A, klub B) – nazivi klubova kao u CLUBS
DERBIES: list[tuple[str, str, str]] = [
    ("Vječni derbi", "Dinamo Zagreb", "Hajduk Split"),
    ("Jadranski derbi", "Hajduk Split", "Rijeka"),
    ("Derbi Dinamo – Rijeka", "Dinamo Zagreb", "Rijeka"),
    ("Vječiti derbi (Beograd)", "Crvena zvezda", "Partizan"),
    ("Bečki derbi", "Rapid Wien", "Austria Wien"),
    ("Praški derbi", "Slavia Praha", "Sparta Praha"),
    ("El Clásico", "Real Madrid", "Barcelona"),
    ("Madridski derbi", "Real Madrid", "Atlético Madrid"),
    ("Sjevernolondonski derbi", "Arsenal", "Tottenham"),
    ("Manchesterski derbi", "Manchester City", "Manchester United"),
    ("Merseysideski derbi", "Liverpool", "Everton"),
    ("Liverpool – Manchester United", "Liverpool", "Manchester United"),
    ("Old Firm", "Celtic", "Rangers"),
    ("Derby della Madonnina", "Inter", "Milan"),
    ("Derby d'Italia", "Inter", "Juventus"),
    ("Derby della Capitale", "Roma", "Lazio"),
    ("Der Klassiker", "Bayern München", "Borussia Dortmund"),
    ("Revierderby", "Borussia Dortmund", "Schalke 04"),
    ("Le Classique", "Paris Saint-Germain", "Marseille"),
    ("O Clássico", "Porto", "Benfica"),
    ("Lisabonski derbi", "Benfica", "Sporting CP"),
    ("De Klassieker", "Ajax", "Feyenoord"),
    ("Interkontinentalni derbi", "Galatasaray", "Fenerbahçe"),
    ("Derbi vječnih rivala (Atena)", "Olympiacos", "Panathinaikos"),
]

_BY_NAME = {c.name: c for c in CLUBS}


def find_club(team: str | None) -> Club | None:
    """Klub po nazivu iz bilo kojeg izvora ('GNK Dinamo', 'Man Utd', 'FC Bayern München' …)."""
    name = normalize(team)
    if not name:
        return None
    padded = f" {name} "
    for club in CLUBS:
        for alias in club.aliases:
            if alias.startswith("="):
                if name == alias[1:]:
                    return club
            elif f" {alias} " in padded:
                return club
    return None


def derby_name(home: str, away: str) -> str | None:
    a, b = find_club(home), find_club(away)
    if not a or not b:
        return None
    pair = {a.name, b.name}
    for name, x, y in DERBIES:
        if pair == {x, y}:
            return name
    return None


@dataclass
class MatchInfo:
    home: Club | None
    away: Club | None
    derby: str | None
    tags: list[str] = field(default_factory=list)
    reason: str = ""  # zašto je utakmica zanimljiva (za prikaz)

    @property
    def country(self) -> str:
        return self.home.country if self.home else ""

    def involves(self, country: str) -> bool:
        return any(c and c.country == country for c in (self.home, self.away))


def match_info(home: str, away: str, seller_country: str = "HR", competition: str = "") -> MatchInfo:
    """Oznake i razlog interesa: derbi, velika utakmica, hrvatski klub."""
    h, a = find_club(home), find_club(away)
    derby = derby_name(home, away)
    tags: list[str] = []
    reasons: list[str] = []
    if derby:
        tags.append("derby")
        reasons.append(derby)
    local = [c for c in (h, a) if c and c.country == seller_country]
    big = [c for c in (h, a) if c and c.big]
    if len(big) == 2 and not derby:
        tags.append("big_match")
        reasons.append("dva velika kluba")
    elif local and big and not derby:
        tags.append("big_match")
        reasons.append(f"{local[0].name} protiv velikog kluba ({big[0].name})")
    if local and not reasons:
        reasons.append(f"igra {local[0].name}")
    if any(w in normalize(competition) for w in ("final", "finale")):
        tags.append("final")
    return MatchInfo(h, a, derby, tags, "; ".join(reasons))


def is_notable(info: MatchInfo, seller_country: str = "HR") -> bool:
    """Utakmice koje prikazujemo: derbiji, velike utakmice i sve utakmice klubova iz države prodavatelja."""
    return bool(info.tags) or info.involves(seller_country)


# ---------------------------------------------------------------------- analiza za prikaz

RESALE_STATUS = {
    "criminal": ("zabranjeno", "Preprodaja je kazneno djelo"),
    "face": ("zabranjeno", "Zakon: ne iznad nominalne cijene"),
    "club_terms": ("zabranjeno", "Uvjeti kluba zabranjuju preprodaju"),
    "official_only": ("sluzbeno", "Samo službena preprodaja (po nominalnoj)"),
    "official_marketplace": ("sluzbeno_trziste", "Samo službeno tržište (cijena slobodna, uz naknade)"),
    "none": ("dopusteno", "Dopušteno (vrijede opći zakoni države)"),
}


RULES_IN_SHORT = [
    "Hrvatska (HNL, reprezentacija): ulaznice glase na ime, na ulazu se traži osobna; klubovi i HNS poništavaju preprodane ulaznice.",
    "UK, Francuska i Portugal: neovlaštena preprodaja ulaznica za nogomet je kazneno djelo – po bilo kojoj cijeni.",
    "Italija, Belgija, Poljska, Irska: zakonom zabranjeno iznad nominalne cijene; Njemačka, Španjolska, Nizozemska: zabranjuju uvjeti klubova.",
    "UEFA natjecanja (Liga prvaka, Europska, Konferencijska): ulaznice personalizirane, dopuštena je samo službena preprodaja po nominalnoj cijeni.",
    "Gdje je preprodaja dopuštena: SAD i Kanada (MLS, prijateljske utakmice) po zakonima savezne države; FIFA natjecanja samo na službenom FIFA tržištu.",
]


def split_match(event) -> tuple[str, str]:
    """'Domaćin – Gost' iz naziva događaja."""
    for text in (event.artist, event.name):
        for sep in (" – ", " - ", " vs ", " v "):
            if text and sep in text:
                home, away = text.split(sep, 1)
                return home.strip(), away.split(" (")[0].strip()
    return (event.artist or event.name or ""), ""


def analyze(ops, seller_country: str = "HR") -> dict:
    """Nogometne utakmice iz procjena → retci za prikaz (zašto je zanimljiva, smije li se preprodati, kako kupiti)."""
    from karte.report import location
    from karte.service import opportunity_dict

    rows = []
    for op in ops:
        e = op.event
        if e.segment != "sport" or (e.sport or "football") != "football":
            continue
        home, away = split_match(e)
        info = match_info(home, away, seller_country, e.league or "")
        rule = op.legal.sport_rule or "none"
        status, label = RESALE_STATUS.get(rule, RESALE_STATUS["none"])
        if op.legal.profit_prohibited and status == "dopusteno":
            status, label = "zabranjeno", "Zakon države ne dopušta preprodaju iznad nominalne"
        if op.verdict == "RIZIČNO":
            status, label = "rizicno", "Krši uvjete kluba – isplativo samo uz visok rizik poništenja"
        notes = list(dict.fromkeys(how_to_buy(home, away, e.league or "") + [n for n in op.legal.sport_notes if n]))
        market = market_info(e, op, status)
        rows.append({
            "date": e.date.isoformat(),
            "match": f"{home} – {away}" if away else home,
            "home": home,
            "away": away,
            "competition": e.league or "",
            "location": location(e),
            "country": e.country,
            "why": info.reason,
            "derby": info.derby,
            "local": info.involves(seller_country),
            "demand": round(op.demand.score, 3),
            "verdict": op.verdict,
            "resale": status,
            "resale_label": label,
            "official": op.legal.official_channel,
            "how_to_buy": notes[:5],
            "legal": op.legal.summary,
            "market": market,
            "notes": e.notes or "",
            "url": e.url,
            "op": opportunity_dict(op),
        })
    rows.sort(key=lambda r: r["date"])
    counts = Counter(r["resale"] for r in rows)
    return {
        "rows": rows,
        "total": len(rows),
        "local": sum(1 for r in rows if r["local"]),
        "derbies": sum(1 for r in rows if r["derby"]),
        "with_market": sum(1 for r in rows if r["market"]),
        "forbidden": counts.get("zabranjeno", 0) + counts.get("sluzbeno", 0),
        "allowed": counts.get("dopusteno", 0) + counts.get("sluzbeno_trziste", 0),
        "rules": RULES_IN_SHORT,
    }


WHY_NOT_RESELL = {
    "zabranjeno": (
        "Ulaznica glasi na ime i provjerava se osobnom – kupac s preprodaje može biti odbijen na ulazu. Tada prodavatelj "
        "snosi trošak povrata/zamjene na platformi, a klub poništava ulaznicu i blokira članstvo."
    ),
    "rizicno": (
        "Ulaznica može biti poništena ili kupac odbijen na ulazu (ulaznica na ime); računica već uključuje tu šansu i kaznu "
        "platforme. Siguran izlaz bez zarade je službena razmjena kluba."
    ),
    "sluzbeno": "Jedini dopušteni kanal je službena preprodaja po nominalnoj cijeni – zarade nema, ali vraćaš novac bez rizika.",
    "sluzbeno_trziste": "Preprodaja samo na službenom tržištu organizatora, uz naknade (FIFA: 15 % prodavatelju).",
    "dopusteno": "Preprodaja je dopuštena – vrijede opći zakoni države i pravila platforme.",
}


def market_info(event, op, status: str) -> dict | None:
    """Što se nudi na preprodaji (viagogo/StubHub) u odnosu na nominalnu cijenu – samo kao informacija."""
    from karte.knowledge import ModelConfig
    from karte.util import days_between, parse_datetime

    sec = event.secondary
    if sec is None or not sec.lowest:
        return None
    cfg = ModelConfig.load()
    lowest = cfg.to_eur(sec.lowest, sec.currency)
    median = cfg.to_eur(sec.median, sec.currency) if sec.median else None
    face_lo = cfg.to_eur(event.face_min, event.currency) if event.face_min else None
    face_hi = cfg.to_eur(event.face_max, event.currency) if event.face_max else None
    observed = parse_datetime(sec.observed) if sec.observed else None
    lead = days_between(observed, event.date) if observed else None
    return {
        "source": sec.source,
        "lowest": round(lowest, 2),
        "median": round(median, 2) if median else None,
        "count": sec.listing_count,
        "observed": sec.observed,
        "face_min": face_lo,
        "face_max": face_hi,
        "multiple": round(lowest / (face_hi or face_lo), 2) if (face_hi or face_lo) else None,
        # oglasi daleko prije početka službene prodaje (klubovi prodaju 1–3 tjedna prije utakmice) – prodavač još nema ulaznice
        "speculative": bool(lead is not None and lead > 21),
        "why": WHY_NOT_RESELL.get(status, ""),
    }


def how_to_buy(home: str, away: str, competition: str = "") -> list[str]:
    """Kratki, konkretni koraci za kupnju ulaznica za utakmicu (za vlastiti odlazak)."""
    h, a = find_club(home), find_club(away)
    steps: list[str] = []
    if h and h.tickets:
        steps.append(f"Domaće ulaznice prodaje {h.name}: {h.tickets} – ulaznica glasi na ime, na ulazu se traži osobni dokument.")
    elif h:
        steps.append(f"Ulaznice prodaje domaćin ({h.name}) na službenoj stranici kluba (Tickets) – prednost imaju članovi i vlasnici sezonskih.")
    else:
        steps.append(f"Ulaznice prodaje domaćin ({home}) na službenoj stranici kluba – prednost imaju članovi i vlasnici sezonskih.")
    if a and a.tickets:
        steps.append(f"Za gostujući sektor ulaznice prodaje {a.name} ({a.tickets}), obično samo članovima kluba.")
    else:
        steps.append(f"Navijači gostiju kupuju preko svog kluba ({away}) – gostujuća kvota, obično za članove.")
    if "uefa" in normalize(competition) or any(w in normalize(competition) for w in ("champions", "europa", "conference")):
        steps.append("UEFA natjecanja: ulaznice su personalizirane (često u aplikaciji kluba/UEFA); jedini dopušteni prijenos je službena preprodaja.")
    steps.append("Učlani se na vrijeme – za derbije i velike utakmice ulaznice često ne dođu u slobodnu prodaju.")
    return steps
