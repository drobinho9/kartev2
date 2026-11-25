"""Uvoz događaja s bilo koje web stranice (zamjena za Ticketmaster API, radi u tvom pregledniku).

Stranice prodavača i platformi (Ticketmaster, Eventim, Entrio, viagogo, StubHub…) za Google objavljuju
strukturirane podatke o događaju (schema.org `Event` u JSON-LD obliku): naziv, datum, dvoranu, grad,
državu, izvođača i ponudu (cijena od–do, valuta, dostupnost, početak prodaje).

Dva načina:
1. **Gumb u pregledniku (bookmarklet)** – na stranici događaja klikneš „karte: spremi”; gumb pročita
   JSON-LD s otvorene stranice i otvori lokalnu aplikaciju s tim podacima (ništa ne ide na tuđi server).
2. **Spremljena stranica** – Ctrl+S → `karte uvoz stranica.html`.

Na stranici prodavača cijena je nominalna, a na platformi za preprodaju (viagogo, StubHub…) to je cijena
s preprodaje – aplikacija to razlikuje po adresi stranice.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.parse
from datetime import date, datetime
from html.parser import HTMLParser

from karte import knowledge
from karte.geo import country_code
from karte.util import normalize, parse_datetime, parse_float

EVENT_TYPES = re.compile(r"(Event|Festival|Concert)$", re.I)
SOLD_OUT = re.compile(r"SoldOut|OutOfStock", re.I)
PRESALE = re.compile(r"PreOrder|PreSale", re.I)
STATUS = {"EventCancelled": "otkazano", "EventPostponed": "odgođeno", "EventRescheduled": "odgođeno"}
# države prema domeni kad stranica ne navodi državu
TLD_COUNTRY = {
    "hr": "HR", "si": "SI", "rs": "RS", "ba": "BA", "me": "ME", "hu": "HU", "at": "AT", "de": "DE", "ch": "CH", "cz": "CZ",
    "sk": "SK", "pl": "PL", "it": "IT", "es": "ES", "fr": "FR", "nl": "NL", "be": "BE", "ie": "IE", "uk": "GB", "se": "SE",
    "no": "NO", "dk": "DK", "fi": "FI", "pt": "PT", "ro": "RO", "bg": "BG", "gr": "GR", "ca": "CA", "au": "AU", "nz": "NZ", "mx": "MX",
}
FIELDS = [
    "izvodjac", "naziv", "dvorana", "grad", "drzava", "datum", "vrijeme", "cijena_min", "cijena_max", "valuta", "status",
    "prodaja_od", "kapacitet", "limit", "personalizirano", "oznake", "sek_najniza", "sek_medijan", "sek_izvor", "sek_valuta",
    "sek_datum", "prodavac", "url", "biljeske",
]


class _LdParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self.meta: dict[str, str] = {}
        self.title = ""
        self._ld: list[str] | None = None
        self._in_title = False

    def handle_starttag(self, tag, attrs):
        a = {k: (v or "") for k, v in attrs}
        if tag == "script" and "ld+json" in a.get("type", "").lower():
            self._ld = []
        elif tag == "meta":
            key = a.get("property") or a.get("name")
            if key and key.lower() in ("og:title", "og:url", "og:description") and a.get("content"):
                self.meta[key.lower()] = a["content"]
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        if tag == "script" and self._ld is not None:
            self.blocks.append("".join(self._ld))
            self._ld = None
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data):
        if self._ld is not None:
            self._ld.append(data)
        elif self._in_title:
            self.title += data


def payload_from_html(html: str, url: str = "") -> dict:
    """Isti oblik podataka kao gumb u pregledniku, ali iz spremljene HTML datoteke."""
    p = _LdParser()
    p.feed(html)
    p.close()
    return {
        "v": 1,
        "url": url or p.meta.get("og:url", ""),
        "title": p.title.strip(),
        "ogTitle": p.meta.get("og:title", ""),
        "ogDesc": p.meta.get("og:description", ""),
        "ld": p.blocks,
    }


def decode_payload(text: str) -> dict:
    """Base64 (iz adrese ili međuspremnika) ili čisti JSON → rječnik."""
    text = (text or "").strip()
    if text.startswith("{"):
        return json.loads(text)
    padded = text + "=" * (-len(text) % 4)
    raw = base64.b64decode(padded.replace("-", "+").replace("_", "/"))
    return json.loads(raw.decode("utf-8"))


def _loads(block: str):
    block = block.strip()
    block = re.sub(r"^\s*(<!--|//\s*<!\[CDATA\[)", "", block)
    block = re.sub(r"(-->|//\s*\]\]>)\s*$", "", block)
    try:
        return json.loads(block)
    except ValueError:
        try:  # neke stranice imaju više objekata zaredom ili zareze na kraju
            return json.loads(re.sub(r",\s*([}\]])", r"\1", block))
        except ValueError:
            return None


def _walk(node):
    if isinstance(node, list):
        for x in node:
            yield from _walk(x)
    elif isinstance(node, dict):
        yield node
        for key in ("@graph", "itemListElement", "item", "subEvent", "event", "events", "mainEntity"):
            if key in node:
                yield from _walk(node[key])


def _types(obj: dict) -> list[str]:
    t = obj.get("@type") or []
    return [str(x).split("/")[-1] for x in (t if isinstance(t, list) else [t])]


def _first(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _text(value) -> str:
    value = _first(value)
    if isinstance(value, dict):
        return str(value.get("name") or value.get("@id") or "").strip()
    return str(value or "").strip()


def _domain(url: str) -> str:
    return (urllib.parse.urlparse(url).netloc or "").lower().removeprefix("www.")


def _resale_platform(domain: str) -> str | None:
    """Naziv platforme za preprodaju ako je stranica s nje (viagogo, StubHub…), inače None."""
    for key, raw in knowledge.platforms().items():
        if key in ("lokalni_oglasnik", "facebook_grupe", "ticketmaster_resale"):
            continue
        host = _domain(raw.get("url", ""))
        base = host.split(".")[0] if host else ""
        if base and (domain == host or domain.endswith("." + host) or domain.split(".")[0] == base):
            return raw.get("name", key)
    return None


def _country(address, domain: str) -> str | None:
    if isinstance(address, dict):
        c = address.get("addressCountry")
        c = _text(c)
        if len(c) == 2 and c.isalpha():
            return c.upper()
        code = country_code(c)
        if code:
            return code
    elif isinstance(address, str) and address:
        code = country_code(address.split(",")[-1])
        if code:
            return code
    tld = domain.rsplit(".", 1)[-1] if domain else ""
    return TLD_COUNTRY.get(tld)


def _artist(obj: dict, name: str) -> str:
    performer = obj.get("performer") or obj.get("performers")
    if performer:
        names = [_text(p) for p in (performer if isinstance(performer, list) else [performer]) if _text(p)]
        if names:
            return names[0]
    return re.split(r"\s+[-–|@:]\s+|:\s+", name, maxsplit=1)[0].strip()


def _offers(obj: dict) -> dict:
    offers = obj.get("offers")
    out = {"low": None, "high": None, "currency": None, "available": None, "valid_from": None, "url": None, "seller": None}
    for offer in offers if isinstance(offers, list) else [offers]:
        if not isinstance(offer, dict):
            continue
        low = parse_float(offer.get("lowPrice")) or parse_float(offer.get("price"))
        high = parse_float(offer.get("highPrice")) or parse_float(offer.get("price"))
        if low is not None:
            out["low"] = low if out["low"] is None else min(out["low"], low)
        if high is not None:
            out["high"] = high if out["high"] is None else max(out["high"], high)
        out["currency"] = out["currency"] or offer.get("priceCurrency")
        out["available"] = out["available"] or str(offer.get("availability") or "")
        out["valid_from"] = out["valid_from"] or offer.get("validFrom") or offer.get("availabilityStarts")
        out["url"] = out["url"] or offer.get("url")
        out["seller"] = out["seller"] or _text(offer.get("seller"))
    return out


def event_rows(payload: dict, today: date | None = None) -> list[dict]:
    """Kandidati za "Moje događaje" (stupci kao u CSV-u snimke)."""
    today = today or date.today()
    url = payload.get("url") or ""
    domain = _domain(url)
    resale = _resale_platform(domain)
    vendor = None if resale else knowledge.vendor_key_for(domain)
    rows: list[dict] = []
    seen: set[str] = set()
    for block in payload.get("ld") or []:
        data = _loads(block) if isinstance(block, str) else block
        for obj in _walk(data):
            if not any(EVENT_TYPES.search(t) for t in _types(obj)):
                continue
            name = _text(obj.get("name")) or payload.get("ogTitle") or payload.get("title") or ""
            start = _local_dt(obj.get("startDate"))
            if not name or start is None:
                continue
            location = _first(obj.get("location")) or {}
            venue = _text(location) if isinstance(location, dict) else str(location or "")
            address = location.get("address") if isinstance(location, dict) else None
            address = _first(address)
            if isinstance(address, dict):
                city = _text(address.get("addressLocality"))
            else:  # "Zagreb, Croatia"
                parts = [x.strip() for x in str(address or "").split(",") if x.strip()]
                city = parts[0] if len(parts) > 1 else ""
            offer = _offers(obj)
            status = STATUS.get(_text(obj.get("eventStatus")).split("/")[-1], "u prodaji")
            if offer["available"] and SOLD_OUT.search(offer["available"]) and status == "u prodaji":
                status = "rasprodano"
            onsale = _local_dt(offer["valid_from"]) if offer["valid_from"] else None
            if onsale and onsale.date() > today and status == "u prodaji":
                status = "najava"
            row = dict.fromkeys(FIELDS, "")
            row.update({
                "izvodjac": _artist(obj, name),
                "naziv": name,
                "dvorana": venue,
                "grad": city,
                "drzava": _country(address, domain) or "",
                "datum": start.date().isoformat(),
                "vrijeme": start.strftime("%H:%M") if (start.hour or start.minute) else "",
                "valuta": (offer["currency"] or "EUR").upper(),
                "status": status,
                "prodaja_od": onsale.strftime("%Y-%m-%d %H:%M") if onsale and onsale.date() > today else "",
                "url": _text(obj.get("url")) or url,
                "biljeske": f"Uvezeno s {domain or 'stranice'} {today.isoformat()} (schema.org podaci stranice).",
            })
            if resale:
                row.update({
                    "sek_najniza": _num(offer["low"]), "sek_valuta": (offer["currency"] or "").upper(),
                    "sek_izvor": resale, "sek_datum": today.isoformat(),
                })
            else:
                row.update({"cijena_min": _num(offer["low"]), "cijena_max": _num(offer["high"]), "prodavac": vendor or ""})
            key = event_key_row(row)
            if key not in seen:
                seen.add(key)
                rows.append(row)
    if not rows:  # nema strukturiranih podataka – predložak za ručno dopunjavanje
        row = dict.fromkeys(FIELDS, "")
        row.update({
            "naziv": payload.get("ogTitle") or payload.get("title") or "",
            "url": url,
            "drzava": TLD_COUNTRY.get(domain.rsplit(".", 1)[-1], "") if domain else "",
            "biljeske": f"Stranica {domain or ''} nema schema.org podatke o događaju – dopuni datum i cijene ručno.",
        })
        if resale:
            row["sek_izvor"] = resale
        elif vendor:
            row["prodavac"] = vendor
        rows.append(row)
    return rows


def _local_dt(value) -> datetime | None:
    """Lokalno vrijeme događaja kako piše na stranici ("2027-06-27T20:00:00+02:00" → 20:00, ne 18:00 UTC)."""
    text = _text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return parse_datetime(text)


def _num(value) -> str:
    if value is None:
        return ""
    return f"{value:.2f}".rstrip("0").rstrip(".")


def event_key_row(row: dict) -> str:
    return f"{normalize(row.get('izvodjac') or row.get('naziv'))}|{row.get('datum', '')}|{normalize(row.get('grad'))}"


def bookmarklet(port: int) -> str:
    """JavaScript za gumb u traci oznaka: pročita JSON-LD sa stranice i otvori lokalnu aplikaciju s podacima."""
    code = (
        "(()=>{try{"
        "const L=[...document.querySelectorAll('script[type=\"application/ld+json\"]')].map(s=>s.textContent)"
        ".filter(t=>/Event|Offer/i.test(t)).map(t=>t.slice(0,60000)).slice(0,8);"
        "const m=n=>{const e=document.querySelector('meta[property=\"'+n+'\"],meta[name=\"'+n+'\"]');return e?e.content:''};"
        "const d={v:1,url:location.href,title:document.title,ogTitle:m('og:title'),ogDesc:m('og:description'),ld:L};"
        "const s=btoa(unescape(encodeURIComponent(JSON.stringify(d))));"
        f"const w=window.open('http://127.0.0.1:{port}/#uvoz='+s,'_blank');"
        "if(!w){(navigator.clipboard?navigator.clipboard.writeText(s):Promise.reject()).then("
        "()=>alert('karte: skočni prozor je blokiran – podaci su kopirani. U aplikaciji: Najave i uvoz → Zalijepi.'),"
        "()=>prompt('karte: kopiraj ovaj tekst i zalijepi ga u aplikaciju (Najave i uvoz → Zalijepi):',s));}"
        "}catch(e){alert('karte: '+e)}})()"
    )
    return "javascript:" + urllib.parse.quote(code, safe="(){}[]=>;:,.'!*/?$&+@")
