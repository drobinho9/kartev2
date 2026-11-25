"""Radar najava: nove turneje, dodatni datumi i početak prodaje ulaznica iz RSS izvora (bez API ključeva).

Zašto je ovo važno: zarada se radi na početku prodaje (presale), a najave izlaze dane ili tjedne prije nego
što događaj uopće postoji u Ticketmasterovom API-ju. Radar čita RSS izvore (karte/data/najave.toml),
prepoznaje izvođača, gradove/države i datume prodaje (hrvatski i engleski), označava nove stavke
i rangira ih po regiji, popularnosti izvođača (Deezer) i tome je li poznat početak prodaje.
"""

from __future__ import annotations

import json
import math
import re
import tomllib
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from importlib import resources
from pathlib import Path

from karte.net import HttpClient, ProviderError
from karte.providers.deezer import DeezerProvider
from karte.util import normalize, parse_datetime, to_naive_utc, utcnow

FEED_TTL = 2 * 3600

MONTHS = {
    # hrvatski (nominativ, genitiv, lokativ) + srpski/bosanski + engleski
    "sijecanj": 1, "sijecnja": 1, "sijecnju": 1, "januar": 1, "januara": 1, "january": 1, "jan": 1,
    "veljaca": 2, "veljace": 2, "veljaci": 2, "februar": 2, "februara": 2, "february": 2, "feb": 2,
    "ozujak": 3, "ozujka": 3, "ozujku": 3, "mart": 3, "marta": 3, "march": 3, "mar": 3,
    "travanj": 4, "travnja": 4, "travnju": 4, "april": 4, "aprila": 4, "apr": 4,
    "svibanj": 5, "svibnja": 5, "svibnju": 5, "maj": 5, "maja": 5, "may": 5,
    "lipanj": 6, "lipnja": 6, "lipnju": 6, "jun": 6, "juna": 6, "june": 6,
    "srpanj": 7, "srpnja": 7, "srpnju": 7, "jul": 7, "jula": 7, "july": 7,
    "kolovoz": 8, "kolovoza": 8, "kolovozu": 8, "avgust": 8, "avgusta": 8, "august": 8, "augusta": 8, "aug": 8,
    "rujan": 9, "rujna": 9, "rujnu": 9, "septembar": 9, "septembra": 9, "september": 9, "sep": 9, "sept": 9,
    "listopad": 10, "listopada": 10, "listopadu": 10, "oktobar": 10, "oktobra": 10, "october": 10, "oct": 10,
    "studeni": 11, "studenoga": 11, "studenog": 11, "studenom": 11, "novembar": 11, "novembra": 11, "november": 11, "nov": 11,
    "prosinac": 12, "prosinca": 12, "prosincu": 12, "decembar": 12, "decembra": 12, "december": 12, "dec": 12,
}
_M = r"(?P<m>[^\W\d_]{3,10})"  # riječ; mjesec se provjerava preko MONTHS (s ili bez dijakritika)
DATE_PATTERNS = [
    # 27. studenoga (2026.) / 5. veljače 2027.
    re.compile(rf"\b(?P<d>\d{{1,2}})\.\s*{_M}\b\.?(?:\s*(?P<y>20\d\d)\.?)?", re.I),
    # 27 November (2026) / 27th November
    re.compile(rf"\b(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\s+{_M}\b\.?(?:,?\s*(?P<y>20\d\d))?", re.I),
    # November 27(, 2026) / Nov. 27th
    re.compile(rf"\b{_M}\.?\s+(?P<d>\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s*(?P<y>20\d\d))?", re.I),
    # 27.11.(2026.)
    re.compile(r"\b(?P<d>\d{1,2})\.\s?(?P<mn>\d{1,2})\.(?:\s?(?P<y>20\d\d)\.?)?(?!\d)"),
]
TIME_RE = re.compile(r"\b(?:u|at|od|from)\s+(?P<h>\d{1,2})(?:[:.](?P<min>\d{2}))?\s*(?P<suf>am|pm|a\.m\.|p\.m\.|h\b|sati)?", re.I)
SALE_RE = re.compile(
    r"ulaznic|prodaj[aeu]|prodavat|u prodaji|on sale|on-sale|onsale|general sale|ticket sales|tickets go on|go on sale|"
    r"tickets will be available|available from|karte|bilet|vstopnic|jegy",
    re.I,
)
PRESALE_RE = re.compile(r"presale|pre-sale|pretprodaj|fan ?club|fan klub|članov|members|amex|mastercard|verified fan", re.I)
EVENT_RE = re.compile(
    r"koncert|nastup|svira|stiž|dolaz|održat|festival|show|concert|perform|plays?|headline|tour|turnej|večer|veče|"
    r"night|datum|zatvara|otvara",
    re.I,
)
CONCERT_RE = re.compile(
    r"koncert|turnej|nastup|ulaznic|festival|arena|stadion|stižu|stiže|dolaze|dolazi|rasprodan|dodatni|svira|vraća|"
    r"\btour\b|concert|tickets|on sale|presale|announce|stadium|sold out|headline|dates|world tour",
    re.I,
)
SKIP_CATEGORIES = re.compile(r"^(theatre|theater|comedy|film|tv|tv & movies|sport|gastro|lifestyle|autozona|biznis)$", re.I)
TITLE_VERBS = re.compile(
    r"\s+(?:se\s+)?(?:stižu|stiže|dolaze|dolazi|vraćaju|vraća|sviraju|svira|nastupaju|nastupa|objavili|objavio|objavila|"
    r"najavili|najavio|najavila|otkazali|otkazao|otkazala|odgodili|odgodio|odgodila|rasprodali|rasprodao|rasprodala|"
    r"prekinuli|prekinuo|ide na|idu na|slave|slavi|pune|puni|zatvara|zatvaraju|otvara|otvaraju|predvode|predvodi|"
    r"announces?|adds?|unveils?|reveals?|confirms?|returns?|to headline|headlines?|will play|sets?|brings?|extends?|"
    r"postpones?|cancels?|embarks?|launch(?:es)?|details?|plots?|schedules?|expands?|sells? out|sold out|is coming|are coming)\b",
    re.I,
)
TITLE_CUT = re.compile(r"\s+(?:se|s|sa|uz|with|and|i)\s+|\s+[–—-]\s+|:\s+|,\s+")  # veznici malim slovima (As I Lay Dying!)
DESCRIPTORS = re.compile(
    r"^(?:kultni|kultna|kultno|legendarni|legendarna|slavni|slavna|popularni|britanski|britanska|američki|američka|irski|"
    r"švedski|njemački|kanadski|australski|frontmen|grammy-winning|multiplatinum|legendary|iconic|british|american|irish)\s+",
    re.I,
)

# Gradovi i države → (ISO, ocjena regije: 3 = HR, 2 = susjedi, 1 = ostatak Europe)
PLACES = [
    (r"zagreb\w*|jarun\w*|šalat\w*|salat\w*|tvornic\w+ kulture|tvornic\w+|boogaloo\w*|dom sportova|inmusic|hala zagreb",
     "HR", 3, "Zagreb"),
    (r"split\w*|spaladium\w*", "HR", 3, "Split"),
    (r"pul[aieu]\b|pulsk\w*", "HR", 3, "Pula"),
    (r"rijek\w+", "HR", 3, "Rijeka"),
    (r"zad(?:ar|ru|ra)\b", "HR", 3, "Zadar"),
    (r"osijek\w*", "HR", 3, "Osijek"),
    (r"dubrovnik\w*", "HR", 3, "Dubrovnik"),
    (r"šibenik\w*|sibenik\w*", "HR", 3, "Šibenik"),
    (r"hrvatsk\w+|croatia\w*", "HR", 3, "Hrvatska"),
    (r"ljubljan\w+|stožic\w+|stozic\w+|kino šišk\w+|kino sisk\w+", "SI", 2, "Ljubljana"),
    (r"sloven\w+", "SI", 2, "Slovenija"),
    (r"beograd\w*|belgrade|štark aren\w+|stark aren\w+|sava centr\w+|ušć\w+", "RS", 2, "Beograd"),
    (r"novi sad\w*|novom sadu", "RS", 2, "Novi Sad"),
    (r"sarajev\w+|zetr\w+", "BA", 2, "Sarajevo"),
    (r"budimpešt\w+|budimpest\w+|budapest\w*|mvm dome|papp l[aá]szl[oó]", "HU", 2, "Budimpešta"),
    (r"beč\b|beču\b|beča\b|vienn\w+|wien\w*|stadthalle", "AT", 2, "Beč"),
    (r"graz\w*", "AT", 2, "Graz"),
    (r"prag\b|pragu\b|praga\b|prague|praha", "CZ", 1, "Prag"),
    (r"bratislav\w+", "SK", 1, "Bratislava"),
    (r"milan\w*|milano", "IT", 1, "Milano"),
    (r"trst\w*|triest\w*", "IT", 1, "Trst"),
    (r"münchen\w*|munich|minhen\w*", "DE", 1, "München"),
    (r"berlin\w*", "DE", 1, "Berlin"),
    (r"krak[oó]w\w*|krakov\w*|warsaw|varšav\w+", "PL", 1, "Poljska"),
    (r"london\w*", "GB", 1, "London"),
    (r"amsterdam\w*", "NL", 1, "Amsterdam"),
    (r"pariz\w*|paris\b", "FR", 1, "Pariz"),
    (r"madrid\w*|barcelon\w+", "ES", 1, "Španjolska"),
    (r"europ\w+|eu leg|european", "EU", 1, "Europa"),
]
GENERIC_PLACES = {"Hrvatska", "Slovenija", "Europa"}
_PLACE_RE = [(re.compile(rf"\b(?:{pattern})", re.I), code, score, label) for pattern, code, score, label in PLACES]


@dataclass
class Announcement:
    source: str
    title: str
    link: str
    published: datetime | None
    summary: str = ""
    categories: list[str] = field(default_factory=list)
    artist: str | None = None
    places: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    region_score: int = 0
    onsale: datetime | None = None
    presale: datetime | None = None
    event_date: date | None = None
    fans: int | None = None
    kind: str = "opcenito"
    new: bool = False

    @property
    def score(self) -> float:
        s = float(self.region_score) * 1.5
        s += 1.0 if (self.onsale or self.presale) else 0.0
        s += 0.5 if self.kind == "turneje" else 0.0
        if self.fans:
            s += min(2.0, max(0.0, math.log10(self.fans) - 5.0))  # 100 tis. → 0, 10 mil. → 2
        return round(s, 2)

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "title": self.title,
            "link": self.link,
            "published": self.published.isoformat() if self.published else None,
            "summary": self.summary,
            "artist": self.artist,
            "places": self.places,
            "countries": self.countries,
            "region_score": self.region_score,
            "onsale": self.onsale.isoformat() if self.onsale else None,
            "presale": self.presale.isoformat() if self.presale else None,
            "event_date": self.event_date.isoformat() if self.event_date else None,
            "fans": self.fans,
            "kind": self.kind,
            "new": self.new,
            "score": self.score,
        }


# ----------------------------------------------------------------------------- izvori
def load_sources(extra_path: Path | None = None) -> list[dict]:
    data = tomllib.loads(resources.files("karte.data").joinpath("najave.toml").read_text(encoding="utf-8"))
    sources = list(data.get("izvor", []))
    if extra_path and extra_path.is_file():
        try:
            extra = tomllib.loads(extra_path.read_text(encoding="utf-8")).get("izvor", [])
        except (OSError, tomllib.TOMLDecodeError):
            extra = []
        known = {s["url"] for s in sources}
        sources += [s for s in extra if s.get("url") and s["url"] not in known]
    return sources


def add_source(data_dir: Path, url: str, name: str = "", kind: str = "opcenito") -> tuple[bool, dict]:
    """Dodaj vlastiti RSS/Atom izvor (npr. Google Alerts → RSS) u data_dir/najave.toml. Vraća (dodano, izvor)."""
    url = (url or "").strip()
    if not re.match(r"^https?://[^\s/]+\.[^\s/]+(?:/\S*)?$", url):
        raise ValueError("adresa izvora mora biti potpuna adresa (https://…)")
    if kind not in ("turneje", "opcenito"):
        raise ValueError("vrsta izvora: turneje ili opcenito")
    path = data_dir / "najave.toml"
    source = {"naziv": (name or "").strip() or urllib.parse.urlparse(url).netloc, "url": url, "jezik": "hr", "vrsta": kind}
    if any(s["url"] == url for s in load_sources(path)):
        return False, source
    block = (f'\n[[izvor]]\nnaziv = {json.dumps(source["naziv"], ensure_ascii=False)}\nurl = {json.dumps(url)}\n'
             f'jezik = "hr"\nvrsta = "{kind}"\n')
    data_dir.mkdir(parents=True, exist_ok=True)
    header = "" if path.exists() else "# Moji izvori najava (dopunjuju ugrađene iz karte/data/najave.toml)\n"
    with path.open("a", encoding="utf-8") as fh:
        fh.write(header + block)
    return True, source


# ----------------------------------------------------------------------------- RSS / Atom
def _strip(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html or "")
    text = unescape(unescape(text))
    text = re.sub(r"The post .*? appeared first on .*?\.?$", "", text)
    return re.sub(r"\s+", " ", text).strip()


def parse_feed(xml_text: str) -> list[dict]:
    """RSS 2.0 i Atom → [{title, link, published, summary, categories}]."""
    try:
        root = ET.fromstring(xml_text.strip().encode("utf-8") if isinstance(xml_text, str) else xml_text)
    except ET.ParseError:
        return []
    items: list[dict] = []
    ns_atom = "{http://www.w3.org/2005/Atom}"
    for it in root.iter("item"):
        pub = it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date")
        items.append({
            "title": _strip(it.findtext("title") or ""),
            "link": (it.findtext("link") or "").strip(),
            "published": _pubdate(pub),
            "summary": _strip(it.findtext("description") or "")[:600],
            "categories": [_strip(c.text or "") for c in it.findall("category") if c.text],
        })
    for entry in root.iter(f"{ns_atom}entry"):
        link = entry.find(f"{ns_atom}link")
        items.append({
            "title": _strip(entry.findtext(f"{ns_atom}title") or ""),
            "link": (link.get("href") if link is not None else "") or "",
            "published": _pubdate(entry.findtext(f"{ns_atom}published") or entry.findtext(f"{ns_atom}updated")),
            "summary": _strip(entry.findtext(f"{ns_atom}summary") or entry.findtext(f"{ns_atom}content") or "")[:600],
            "categories": [c.get("term", "") for c in entry.findall(f"{ns_atom}category")],
        })
    return items


def _pubdate(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return to_naive_utc(parsedate_to_datetime(value.strip()))
    except (TypeError, ValueError):
        return parse_datetime(value)


# ----------------------------------------------------------------------------- analiza teksta
def _infer_year(month: int, day: int, year: str | None, ref: datetime) -> date | None:
    try:
        if year:
            return date(int(year), month, day)
        candidate = date(ref.year, month, day)
    except ValueError:
        return None
    if candidate < (ref - timedelta(days=45)).date():
        try:
            candidate = date(ref.year + 1, month, day)
        except ValueError:
            return None
    return candidate


def find_dates(text: str, ref: datetime) -> list[tuple[int, date, int]]:
    """[(pozicija, datum, kraj)] svih prepoznatih datuma u tekstu."""
    found: list[tuple[int, date, int]] = []
    taken: list[tuple[int, int]] = []
    for pattern in DATE_PATTERNS:
        for m in pattern.finditer(text):
            if any(a <= m.start() < b for a, b in taken):
                continue
            gd = m.groupdict()
            month = int(gd["mn"]) if gd.get("mn") else MONTHS.get(normalize(gd["m"]).replace(" ", ""))
            if not 1 <= int(gd["d"]) <= 31:
                continue
            if not month or not 1 <= month <= 12:
                continue
            d = _infer_year(month, int(gd["d"]), gd.get("y"), ref)
            if d:
                found.append((m.start(), d, m.end()))
                taken.append((m.start(), m.end()))
    return sorted(found)


def _time_after(text: str, pos: int) -> tuple[int, int] | None:
    """Vrijeme odmah iza datuma ('u 10 sati', 'at 10am', 'u 12:00'); None ako ga nema."""
    m = TIME_RE.search(text, pos, min(len(text), pos + 40))
    if not m:
        return None
    hour, minute = int(m.group("h")), int(m.group("min") or 0)
    suffix = (m.group("suf") or "").lower().replace(".", "")
    if not (m.group("min") or suffix):
        return None  # "u 2027", "od 30" – nije vrijeme
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return hour, minute


def _last(regex: re.Pattern, text: str) -> int:
    """Pozicija zadnjeg pogotka u tekstu (-1 ako ga nema)."""
    pos = -1
    for m in regex.finditer(text):
        pos = m.start()
    return pos


def sale_dates(text: str, ref: datetime) -> tuple[datetime | None, datetime | None, date | None]:
    """(početak opće prodaje, presale, datum događaja) iz teksta najave.

    Za svaki datum gleda riječi neposredno ispred njega: najbliža riječ o prodaji/presaleu/koncertu određuje
    značenje ("ulaznice u prodaji od 27. studenoga" → prodaja; "koncert 21. lipnja" → događaj).
    """
    onsale = presale = None
    event_day = None
    for pos, d, end in find_dates(text, ref):
        window = text[max(0, pos - 90):pos]
        pre, sale, event = _last(PRESALE_RE, window), _last(SALE_RE, window), _last(EVENT_RE, window)
        hm = _time_after(text, end) or (0, 0)
        when = datetime(d.year, d.month, d.day, hm[0], hm[1])
        if pre >= 0 and pre >= event and presale is None:
            presale = when
        elif sale >= 0 and sale > event and onsale is None:
            onsale = when
        elif event_day is None and (event >= 0 or (pre < 0 and sale < 0)) and d >= ref.date():
            event_day = d
    return onsale, presale, event_day


def detect_places(text: str) -> tuple[list[str], list[str], int]:
    places: list[str] = []
    countries: list[str] = []
    score = 0
    for regex, code, value, label in _PLACE_RE:
        if regex.search(text):
            if label not in places:
                places.append(label)
            if code != "EU" and code not in countries:
                countries.append(code)
            score = max(score, value)
    if len(places) > 1:  # "Zagreb, Hrvatska, Europa" → "Zagreb"
        places = [p for p in places if p not in GENERIC_PLACES] or places
    return places, countries, score


def artist_candidates(title: str) -> list[str]:
    """Mogući nazivi izvođača iz naslova: dio prije glagola ('stižu', 'announces'…), bez opisnih riječi, pa kraći podnizovi."""
    m = TITLE_VERBS.search(title)
    head = title[: m.start()] if m else ""
    if not head:
        return []
    head = TITLE_CUT.split(head, maxsplit=1)[0]
    head = re.sub(r"[“”\"'‘’«»]", "", head).strip(" .:-–")
    head = re.sub(r"\s+(?:20\d\d\.?|\d+\.?)$", "", head).strip()
    words = head.split()
    if not words or len(words) > 8:
        return []
    out: list[str] = []
    clean = DESCRIPTORS.sub("", head).strip()
    for cand in (clean, head):
        if cand and cand not in out:
            out.append(cand)
    for i in range(1, min(len(words), 5)):
        tail = " ".join(words[i:])
        if tail and tail[0].isupper() and tail not in out:
            out.append(tail)
    return out


def analyse(item: dict, source: dict, now: datetime) -> Announcement | None:
    title, summary = item.get("title", ""), item.get("summary", "")
    categories = item.get("categories") or []
    text = f"{title}. {summary}"
    kind = source.get("vrsta", "opcenito")
    if kind != "turneje":
        if categories and all(SKIP_CATEGORIES.match(c.strip()) for c in categories):
            return None
        if not CONCERT_RE.search(text):
            return None
    published = item.get("published")
    ref = published or now
    onsale, presale, event_day = sale_dates(text, ref)
    places, countries, region = detect_places(text)
    candidates = artist_candidates(title)
    return Announcement(
        source=source.get("naziv", ""),
        title=title,
        link=item.get("link", ""),
        published=published,
        summary=summary,
        categories=categories,
        artist=candidates[0] if candidates else None,
        places=places,
        countries=countries,
        region_score=region,
        onsale=onsale,
        presale=presale,
        event_date=event_day,
        kind=kind,
    )


# ----------------------------------------------------------------------------- dohvat
def seen_path(data_dir: Path) -> Path:
    return data_dir / "najave_vidjeno.json"


def load_seen(data_dir: Path) -> set[str]:
    try:
        return set(json.loads(seen_path(data_dir).read_text(encoding="utf-8")).get("links", []))
    except (OSError, ValueError):
        return set()


def mark_seen(data_dir: Path, links: list[str]) -> None:
    seen = list(load_seen(data_dir) | set(links))[-2000:]
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        seen_path(data_dir).write_text(json.dumps({"links": seen, "provjereno": utcnow().isoformat()}), encoding="utf-8")
    except OSError:
        pass


def fetch_announcements(
    http: HttpClient,
    now: datetime | None = None,
    days: int = 21,
    sources: list[dict] | None = None,
    enrich: bool = True,
    data_dir: Path | None = None,
    max_lookups: int = 40,
) -> tuple[list[Announcement], list[str]]:
    now = now or utcnow()
    sources = sources if sources is not None else load_sources(data_dir / "najave.toml" if data_dir else None)
    warnings: list[str] = []
    out: list[Announcement] = []
    links: set[str] = set()
    for source in sources:
        try:
            items = parse_feed(http.get_text(source["url"], cache_ttl=FEED_TTL))
        except ProviderError as exc:
            warnings.append(f"Najave – {source.get('naziv', source['url'])}: {exc}")
            continue
        if not items:
            warnings.append(f"Najave – {source.get('naziv', source['url'])}: izvor nije vratio stavke (provjeri adresu).")
        for item in items:
            if item["published"] and item["published"] < now - timedelta(days=days):
                continue
            ann = analyse(item, source, now)
            if ann and ann.link not in links:
                links.add(ann.link)
                out.append(ann)
    if enrich:
        _enrich_artists(http, out, max_lookups, warnings)
    if data_dir is not None:
        seen = load_seen(data_dir)
        for ann in out:
            ann.new = ann.link not in seen
    out.sort(key=lambda a: (-(a.score + (1.0 if a.new else 0.0)), -(a.published.timestamp() if a.published else 0)))
    return out, warnings


def _enrich_artists(http: HttpClient, items: list[Announcement], max_lookups: int, warnings: list[str]) -> None:
    """Potvrdi izvođača na Deezeru (točno ime) i dodaj broj fanova – najviše max_lookups upita."""
    deezer = DeezerProvider(http)
    cache: dict[str, dict | None] = {}
    lookups = 0
    ranked = sorted(items, key=lambda a: (-a.region_score, a.kind != "turneje"))
    for ann in ranked:
        confirmed = exhausted = False
        for cand in artist_candidates(ann.title):
            key = normalize(cand)
            if key not in cache:
                if lookups >= max_lookups:
                    exhausted = True
                    break
                lookups += 1
                try:
                    cache[key] = deezer.lookup(cand)
                except ProviderError as exc:
                    warnings.append(f"Deezer: {exc}")
                    return
            found = cache.get(key)
            if found and found.get("fans", 0) >= 1000:
                ann.artist, ann.fans = found["name"], found["fans"]
                confirmed = True
                break
        if not confirmed and not exhausted:
            ann.artist = None  # nijedan kandidat nije izvođač na Deezeru ("Novi festival", "Koncert godine"…)
