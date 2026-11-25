"""Wikipedia / Wikimedia – BEZ API ključa.

1. Turneje: datumi, gradovi i dvorane iz tablica "Tour dates" u člancima o turnejama
   (npr. https://en.wikipedia.org/wiki/Twilight_of_the_Punks). Velike turneje imaju ažurne tablice
   unutar nekoliko dana od najave – dobar besplatan izvor "gdje i kada svira", ali BEZ cijena.
2. Trend: dnevni pregledi članka o izvođaču (Wikimedia Pageviews API). Nagli rast pregleda
   (nova pjesma, najava turneje, viralni trenutak) je rani signal potražnje.

Wikimedia traži opisni User-Agent s kontaktom – postavi KARTE_USER_AGENT u .env
(npr. "karte/0.7 (ime@primjer.hr)"). Zahtjeve šaljemo polako i cacheiramo (429 → čekanje).
"""

from __future__ import annotations

import hashlib
import re
import urllib.parse
from html import unescape
from datetime import date, datetime, timedelta
from html.parser import HTMLParser

from karte.geo import country_code
from karte.models import Event
from karte.net import HttpClient, ProviderError
from karte.util import normalize, utcnow

API_URL = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia/all-access/user/{title}/daily/{start}/{end}"
TITLE_TTL = 30 * 24 * 3600
PAGEVIEWS_TTL = 24 * 3600
TOUR_TTL = 24 * 3600

MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
MUSIC_RE = re.compile(
    r"singer|band|musician|rapper|group|duo|trio|\bdj\b|songwriter|composer|vocalist|guitarist|pianist|violinist|"
    r"orchestra|conductor|music|rock|\bpop\b|metal|hip hop|\brap\b|choir|folk|jazz|producer|entertainer|performer|idol",
    re.I,
)
TITLE_SUFFIXES = ("(band)", "(singer)", "(musician)", "(rapper)", "(group)", "(entertainer)")
SKIP_CAPTION = re.compile(r"cancel|postpon|otkaz", re.I)
VOID_TAGS = {"br", "img", "hr", "meta", "link", "input", "wbr", "col", "source"}


# ----------------------------------------------------------------------------- HTML tablice
class _TableParser(HTMLParser):
    """Skuplja tablice 'wikitable' (naslov + redovi ćelija s rowspan/colspan); preskače fusnote i skriveni tekst."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[dict] = []
        self._stack: list[dict] = []
        self._cell: dict | None = None
        self._caption: list[str] | None = None
        self._skip_tag: str | None = None
        self._skip_depth = 0

    @staticmethod
    def _int(value: str | None) -> int:
        m = re.match(r"\s*(\d+)", value or "")
        return max(1, min(int(m.group(1)), 500)) if m else 1

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if self._skip_tag:
            if tag == self._skip_tag:
                self._skip_depth += 1
            return
        style = a.get("style", "").replace(" ", "").lower()
        if tag in ("sup", "style", "script") or "display:none" in style:
            if tag not in VOID_TAGS:
                self._skip_tag, self._skip_depth = tag, 1
            return
        if tag == "table":
            self._stack.append({"caption": "", "rows": [], "classes": a.get("class", "")})
        elif not self._stack:
            return
        elif tag == "caption":
            self._caption = []
        elif tag == "tr":
            self._stack[-1]["rows"].append([])
        elif tag in ("td", "th"):
            rows = self._stack[-1]["rows"]
            if not rows:
                rows.append([])
            self._cell = {"tag": tag, "parts": [], "rowspan": self._int(a.get("rowspan")), "colspan": self._int(a.get("colspan"))}
            rows[-1].append(self._cell)
        elif tag == "br" and self._cell is not None:
            self._cell["parts"].append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag == "br" and self._cell is not None and not self._skip_tag:
            self._cell["parts"].append("\n")

    def handle_endtag(self, tag):
        if self._skip_tag:
            if tag == self._skip_tag:
                self._skip_depth -= 1
                if self._skip_depth <= 0:
                    self._skip_tag = None
            return
        if tag == "table" and self._stack:
            table = self._stack.pop()
            for row in table["rows"]:
                for cell in row:
                    cell["text"] = _clean("".join(cell.pop("parts", [])))
            self.tables.append(table)
        elif tag == "caption" and self._caption is not None and self._stack:
            self._stack[-1]["caption"] = _clean("".join(self._caption))
            self._caption = None
        elif tag in ("td", "th"):
            self._cell = None

    def handle_data(self, data):
        if self._skip_tag:
            return
        if self._cell is not None:
            self._cell["parts"].append(data)
        elif self._caption is not None:
            self._caption.append(data)


def _clean(text: str) -> str:
    text = re.sub(r"\[[^\]]{0,12}\]", "", text)  # [a], [12], [note 1]
    lines = [re.sub(r"[ \t\xa0]+", " ", line).strip() for line in text.split("\n")]
    return "\n".join(line for line in lines if line)


def parse_tables(html: str) -> list[dict]:
    parser = _TableParser()
    parser.feed(html)
    parser.close()
    return [t for t in parser.tables if "wikitable" in t["classes"]]


def expand_grid(rows: list[list[dict]]) -> list[list[dict]]:
    """Razvij rowspan/colspan u pravokutnu mrežu (ista ćelija se ponavlja u svim poljima koja pokriva)."""
    grid: list[list[dict]] = []
    pending: dict[int, list] = {}  # stupac → [preostalo_redova, ćelija]
    for row in rows:
        out: list[dict] = []
        cells = iter(row)
        col = 0
        while True:
            if col in pending:
                remaining, cell = pending[col]
                out.append(cell)
                if remaining <= 1:
                    del pending[col]
                else:
                    pending[col][0] = remaining - 1
                col += 1
                continue
            cell = next(cells, None)
            if cell is None:
                break
            for _ in range(cell["colspan"]):
                out.append(cell)
                if cell["rowspan"] > 1:
                    pending[col] = [cell["rowspan"] - 1, cell]
                col += 1
        grid.append(out)
    return grid


# ----------------------------------------------------------------------------- datumi
def parse_tour_date(text: str, default_year: int | None) -> date | None:
    """'May 17, 2027' | '17 May 2027' | 'September 25' (+ godina iz zaglavlja) → date."""
    t = (text or "").split("\n")[0].strip()
    year = None
    m = re.match(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:\s*[–\-&]\s*\d{1,2})?(?:,?\s+(\d{4}))?\b", t)
    if m and m.group(1).lower() in MONTHS:
        month, day, year = MONTHS[m.group(1).lower()], int(m.group(2)), m.group(3)
    else:
        m = re.match(r"(\d{1,2})(?:\s*[–\-&]\s*\d{1,2})?\s+([A-Za-z]{3,9})\.?(?:,?\s+(\d{4}))?\b", t)
        if not (m and m.group(2).lower() in MONTHS):
            return None
        day, month, year = int(m.group(1)), MONTHS[m.group(2).lower()], m.group(3)
    year = int(year) if year else default_year
    if not year:
        return None
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _year_hint(text: str) -> int | None:
    m = re.search(r"\b(20\d{2})\b", text or "")
    return int(m.group(1)) if m else None


def _column(headers: list[str], *names: str) -> int | None:
    for i, h in enumerate(headers):
        key = normalize(h)
        if any(key.startswith(n) for n in names):
            return i
    return None


def parse_tour_html(html: str) -> list[dict]:
    """Svi koncerti iz tablica turneje: [{date, city, country, country_name, venue}]; preskače otkazane i zbrojne retke."""
    shows: list[dict] = []
    for table in parse_tables(html):
        if SKIP_CAPTION.search(table["caption"]):
            continue
        grid = expand_grid(table["rows"])
        if not grid:
            continue
        header_idx = next((i for i, r in enumerate(grid) if r and all(c["tag"] == "th" for c in r)), None)
        if header_idx is None:
            continue
        headers = [c["text"] for c in grid[header_idx]]
        i_date = _column(headers, "date")
        i_city = _column(headers, "city")
        i_country = _column(headers, "country")
        i_venue = _column(headers, "venue")
        i_location = _column(headers, "location")
        if i_date is None or (i_city is None and i_location is None):
            continue
        year = _year_hint(headers[i_date]) or _year_hint(table["caption"])
        for row in grid[header_idx + 1:]:
            texts = [c["text"] for c in row]
            if len(texts) <= i_date:
                continue
            if len({id(c) for c in row}) == 1:  # razdjelnik ("Leg 2 – Europe", "2027")
                year = _year_hint(texts[0]) or year
                continue
            when = parse_tour_date(texts[i_date], year)
            if when is None:
                continue
            year = when.year if _year_hint(texts[i_date]) else year
            pick = lambda i: texts[i].split("\n")[0].strip() if i is not None and i < len(texts) else ""  # noqa: E731
            city, country_name = pick(i_city), pick(i_country)
            if i_city is None and i_location is not None:
                parts = [p.strip() for p in pick(i_location).split(",")]
                city, country_name = parts[0], parts[-1] if len(parts) > 1 else ""
            shows.append({
                "date": when,
                "city": city,
                "country_name": country_name,
                "country": country_code(country_name),
                "venue": pick(i_venue),
            })
    return shows


# ----------------------------------------------------------------------------- naslovi i pregledi
def resolve_from_response(data: dict, requested: list[str]) -> dict[str, dict | None]:
    """Mapiraj tražene naslove → {'title', 'disambiguation', 'description', 'missing'} prateći normalizaciju i preusmjeravanja."""
    query = (data or {}).get("query") or {}
    normalized = {n["from"]: n["to"] for n in query.get("normalized", []) if "from" in n}
    redirects = {r["from"]: r["to"] for r in query.get("redirects", []) if "from" in r}
    pages = {}
    for page in query.get("pages", []) or []:
        props = page.get("pageprops") or {}
        pages[page.get("title")] = {
            "title": page.get("title"),
            "missing": bool(page.get("missing") or page.get("invalid")),
            "disambiguation": "disambiguation" in props,
            "description": props.get("wikibase-shortdesc") or "",
        }
    out: dict[str, dict | None] = {}
    for title in requested:
        t = normalized.get(title, title)
        for _ in range(3):
            if t in redirects:
                t = redirects[t]
        out[title] = pages.get(t)
    return out


def _acceptable(page: dict | None) -> bool:
    if not page or page["missing"] or page["disambiguation"]:
        return False
    desc = page.get("description") or ""
    return not desc or bool(MUSIC_RE.search(desc))


def trend_from_views(views: list[int], recent_days: int = 14) -> tuple[int | None, float | None]:
    """(prosjek zadnjih N dana, omjer prema prosjeku ranijeg razdoblja)."""
    if len(views) < recent_days + 14:
        return None, None
    recent, prior = views[-recent_days:], views[:-recent_days]
    avg_recent = sum(recent) / len(recent)
    avg_prior = sum(prior) / len(prior)
    if avg_prior <= 0:
        return round(avg_recent), None
    return round(avg_recent), round(avg_recent / avg_prior, 3)


def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def tour_artist(html: str) -> str | None:
    """Izvođač turneje: infookvir ("Tour by <izvođač>"), zatim kratki opis ("Concert tour by Don Omar"),
    zatim prva poveznica iza "tour by" u uvodu. Tribute showovi i festivali obično nemaju nijedno → None."""
    html = html or ""
    m = re.search(r'class="infobox-subheader"[^>]*>(.*?)</td>', html, re.S)
    block = m.group(1) if m else ""
    att = re.search(r'class="attendee"[^>]*>(.*?)</span>\s*(?:</td>|$)', block, re.S) or re.search(r'class="attendee"[^>]*>(.*)', block, re.S)
    if att:
        link = re.search(r"<a [^>]*>(.*?)</a>", att.group(1), re.S)
        text = _clean(link.group(1) if link else att.group(1))
        if text:
            return text
    short = re.search(r'class="shortdescription[^"]*"[^>]*>([^<]*)<', html)
    if short:
        by = re.search(r"\b(?:tour|concert|residency|shows?)\s+by\s+(.+)$", unescape(short.group(1)).strip(), re.I)
        if by and by.group(1).strip():
            return by.group(1).strip()
    # uvodni odlomak = prvi <p> s tekstom (preskače prazne "mw-empty-elt")
    first = next((m.group(1) for m in re.finditer(r"<p[^>]*>(.*?)</p>", html[:40000], re.S) if len(_clean(m.group(1))) > 20), "")
    lead = re.search(r"\btour\s+by\b(.{0,240}?)<a [^>]*>(.*?)</a>", first, re.S | re.I)
    if lead:
        return _clean(lead.group(2)) or None
    return None


def wiki_url(title: str) -> str:
    return "https://en.wikipedia.org/wiki/" + urllib.parse.quote(title.replace(" ", "_"))


class WikipediaProvider:
    name = "wikipedia"

    def __init__(self, http: HttpClient):
        self.http = http

    # --- naslovi
    def _query_titles(self, titles: list[str]) -> dict[str, dict | None]:
        out: dict[str, dict | None] = {}
        for i in range(0, len(titles), 50):
            chunk = titles[i:i + 50]
            data = self.http.get_json(
                API_URL,
                {
                    "action": "query", "format": "json", "formatversion": 2, "redirects": 1,
                    "prop": "pageprops", "ppprop": "disambiguation|wikibase-shortdesc", "titles": "|".join(chunk),
                },
                cache_ttl=TITLE_TTL,
            )
            out.update(resolve_from_response(data, chunk))
        return out

    def resolve_titles(self, artists: list[str]) -> dict[str, str | None]:
        """Izvođač → naslov članka (preskače stranice višeznačnosti; za njih proba '(band)', '(singer)'…)."""
        names = [a.strip() for a in dict.fromkeys(artists) if a and a.strip() and "|" not in a]
        first = self._query_titles(names)
        result: dict[str, str | None] = {}
        retry: list[str] = []
        for name in names:
            page = first.get(name)
            if _acceptable(page):
                result[name] = page["title"]
            else:
                retry.append(name)
        if retry:
            variants = [f"{name} {suffix}" for name in retry for suffix in TITLE_SUFFIXES]
            second = self._query_titles(variants)
            for name in retry:
                result[name] = next(
                    (second[v]["title"] for v in (f"{name} {s}" for s in TITLE_SUFFIXES) if _acceptable(second.get(v))),
                    None,
                )
        return result

    # --- pregledi
    def pageviews(self, title: str, end: date, days: int = 74) -> list[int]:
        start = end - timedelta(days=days - 1)
        url = PAGEVIEWS_URL.format(
            title=urllib.parse.quote(title.replace(" ", "_"), safe=""),
            start=start.strftime("%Y%m%d"),
            end=end.strftime("%Y%m%d"),
        )
        data = self.http.get_json(url, cache_ttl=PAGEVIEWS_TTL)
        items = sorted((data or {}).get("items") or [], key=lambda x: x.get("timestamp", ""))
        return [int(x.get("views") or 0) for x in items]

    def trend(self, title: str, now: datetime | None = None) -> tuple[int | None, float | None]:
        end = ((now or utcnow()) - timedelta(days=1)).date()
        return trend_from_views(self.pageviews(title, end))

    def enrich(self, events: list[Event], now: datetime | None = None, limit: int = 40) -> tuple[list[str], int]:
        """Popuni artist_trend/artist_pageviews za najviše `limit` izvođača. Vraća (upozorenja, broj s podacima)."""
        warnings: list[str] = []
        artists: list[str] = []
        for e in events:
            if e.segment == "music" and e.artist_trend is None and e.artist not in artists:
                artists.append(e.artist)
        artists = artists[:limit]
        if not artists:
            return warnings, 0
        try:
            titles = self.resolve_titles(artists)
        except ProviderError as exc:
            return [f"Wikipedia: {exc}"], 0
        stats: dict[str, tuple[int | None, float | None]] = {}
        failures = 0
        for artist, title in titles.items():
            if not title:
                continue
            try:
                stats[artist] = self.trend(title, now)
            except ProviderError as exc:
                failures += 1
                if failures == 1:
                    warnings.append(f"Wikimedia pregledi: {exc}")
                if failures >= 4:
                    break
        for e in events:
            if e.artist in stats:
                e.artist_pageviews, e.artist_trend = stats[e.artist]
        return warnings, sum(1 for v in stats.values() if v[1] is not None)

    # --- otkrivanje turneja (kategorije "2027 concert tours" itd.)
    def category_members(self, category: str) -> list[str]:
        titles: list[str] = []
        cont = None
        for _ in range(10):
            data = self.http.get_json(
                API_URL,
                {"action": "query", "list": "categorymembers", "cmtitle": category, "cmlimit": 500, "cmnamespace": 0,
                 "format": "json", "formatversion": 2, "cmcontinue": cont},
                cache_ttl=12 * 3600,
            )
            titles += [m["title"] for m in ((data or {}).get("query") or {}).get("categorymembers", []) if m.get("title")]
            cont = ((data or {}).get("continue") or {}).get("cmcontinue")
            if not cont:
                break
        return titles

    def revisions(self, titles: list[str]) -> dict[str, int]:
        """Zadnja revizija članaka (za preskakanje nepromijenjenih turneja pri osvježavanju)."""
        out: dict[str, int] = {}
        for i in range(0, len(titles), 50):
            chunk = titles[i:i + 50]
            data = self.http.get_json(
                API_URL,
                {"action": "query", "prop": "info", "titles": "|".join(chunk), "format": "json", "formatversion": 2, "redirects": 1},
                cache_ttl=3600,
            )
            query = (data or {}).get("query") or {}
            normalized = {n["from"]: n["to"] for n in query.get("normalized", []) if "from" in n}
            redirects = {r["from"]: r["to"] for r in query.get("redirects", []) if "from" in r}
            revs = {p.get("title"): p.get("lastrevid") for p in query.get("pages", []) if p.get("lastrevid")}
            for t in chunk:
                final = redirects.get(normalized.get(t, t), normalized.get(t, t))
                if final in revs:
                    out[t] = int(revs[final])
        return out

    # --- turneje
    def tour_html(self, title: str) -> str:
        data = self.http.get_json(
            API_URL,
            {"action": "parse", "page": title, "prop": "text", "format": "json", "formatversion": 2, "redirects": 1},
            cache_ttl=TOUR_TTL,
        )
        if isinstance(data, dict) and data.get("error"):
            raise ProviderError(f"Wikipedia '{title}': {data['error'].get('info', data['error'])}")
        return ((data or {}).get("parse") or {}).get("text") or ""

    def tour_events(
        self,
        title: str,
        artist: str,
        tags: list[str] | None = None,
        countries: list[str] | None = None,
        now: datetime | None = None,
        html: str | None = None,
    ) -> list[Event]:
        shows = parse_tour_html(html if html is not None else self.tour_html(title))
        return events_from_shows(shows, title, artist, tags, countries, now)


def events_from_shows(
    shows: list[dict],
    title: str,
    artist: str,
    tags: list[str] | None = None,
    countries: list[str] | None = None,
    now: datetime | None = None,
) -> list[Event]:
    """Pretvori retke turneje u događaje (samo budući, opcionalno samo zadane države)."""
    now = now or utcnow()
    wanted = {c.upper() for c in countries or []} - {"ALL"}
    future = [s for s in shows if s["country"] and datetime(s["date"].year, s["date"].month, s["date"].day, 23, 59) >= now]
    events: list[Event] = []
    for s in future:
        if wanted and s["country"] not in wanted:
            continue
        d = s["date"]
        ident = hashlib.sha1(f"{artist}|{s['venue']}|{d.isoformat()}".encode()).hexdigest()[:10]
        events.append(
            Event(
                id=f"wiki:{ident}",
                name=f"{artist} – {title}",
                artist=artist,
                venue=s["venue"],
                city=s["city"],
                country=s["country"],
                date=datetime(d.year, d.month, d.day, 20, 0),
                source="Wikipedia (turneja)",
                url=wiki_url(title),
                tags=list(tags or []),
                artist_upcoming_events=len(future),
                notes="Datum i dvorana s Wikipedije (tablica turneje). Status prodaje i cijene provjeri kod službenog prodavača.",
            )
        )
    return events
