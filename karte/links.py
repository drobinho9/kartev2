"""Poveznice za brzu ručnu provjeru cijena i dostupnosti na domaćim i stranim stranicama.

Aplikacija NE dohvaća te stranice (uvjeti korištenja, zaštita od botova) – samo slaže poveznice
koje otvaraš u pregledniku: službeni prodavači u državi događaja, platforme za preprodaju,
usporedbe cijena i lokalni oglasnici. Koristi se Google pretraga ograničena na stranicu
(`site:`), jer radi uvijek, bez obzira na to kako stranica slaže svoje adrese.
"""

from __future__ import annotations

import urllib.parse

from karte import knowledge
from karte.models import Event

# Usporedbe cijena (agregatori "od" cijena na više platformi)
AGGREGATORS = [("SeatPick", "seatpick.com"), ("Stereoboard", "stereoboard.com"), ("karlobag.eu", "karlobag.eu")]
SKIP_PLATFORMS = {"facebook_grupe", "lokalni_oglasnik"}
FACE_VALUE_CAPS = {"face", "percent"}


def google(domain: str, terms: str) -> str:
    query = f"site:{domain} {terms}" if domain else terms
    return "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)


def _domain(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc or url
    return host.removeprefix("www.")


def price_links(event: Event, allow_profit: bool = True, limit_vendors: int = 4) -> list[dict]:
    """[{group, label, url}] – službena prodaja, preprodaja, usporedba cijena, oglasnici."""
    terms = " ".join(x for x in (f'"{event.artist}"', event.city) if x)
    country = (event.country or "").upper()
    links: list[dict] = []

    def add(group: str, label: str, url: str) -> None:
        if url and all(link["url"] != url for link in links):
            links.append({"group": group, "label": label, "url": url})

    if event.url:
        add("Događaj", "Izvor / stranica događaja", event.url)

    vendors: list[tuple[str, dict]] = []
    if event.primary_vendor and knowledge.vendor_info(event.primary_vendor):
        vendors.append((event.primary_vendor, knowledge.vendor_info(event.primary_vendor)))
    for key, info in knowledge.vendors_for_country(country):
        if key not in {k for k, _ in vendors}:
            vendors.append((key, info))
    for key, info in vendors[: limit_vendors + (1 if event.primary_vendor else 0)]:
        domain = knowledge.vendor_domain(key, country)
        terms_vendor = terms if domain else f"{info.get('name', key)} {terms}"
        add("Službena prodaja", f"{info.get('name', key)}{' (' + domain + ')' if domain else ''}", google(domain, terms_vendor))

    platforms = knowledge.platforms()
    for key, raw in platforms.items():
        if key in SKIP_PLATFORMS:
            continue
        countries = [c.upper() for c in raw.get("countries", ["*"])]
        if "*" not in countries and country not in countries:
            continue
        if raw.get("requires_vendor") and raw.get("requires_vendor") != event.primary_vendor:
            continue
        cap = ((raw.get("overrides") or {}).get(country) or {}).get("cap", raw.get("cap", "none"))
        if not allow_profit and cap not in FACE_VALUE_CAPS:
            continue
        domain = _domain(raw.get("url", ""))
        if key == "ticketmaster_resale":
            domain = knowledge.vendor_domain("ticketmaster", country) or domain
        if domain:
            add("Preprodaja", raw.get("name", key), google(domain, terms))

    if allow_profit:
        for name, domain in AGGREGATORS:
            add("Usporedba cijena", name, google(domain, terms))
        local = platforms.get("lokalni_oglasnik", {})
        domain = (local.get("domains") or {}).get(country)
        if domain:
            add("Oglasnik", (local.get("names") or {}).get(country, domain), google(domain, terms))
    return links
