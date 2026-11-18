"""Last.fm API – popularnost izvođača (broj slušatelja) kao signal potražnje.

Ključ: https://www.last.fm/api/account/create (besplatno). Rezultati se cacheiraju 7 dana.
"""

from __future__ import annotations

from karte.models import Event
from karte.net import HttpClient, ProviderError
from karte.util import normalize

BASE_URL = "https://ws.audioscrobbler.com/2.0/"
CACHE_TTL = 7 * 24 * 3600


def parse_listeners(data: dict) -> int | None:
    if not data or "error" in data:
        return None
    stats = (data.get("artist") or {}).get("stats") or {}
    try:
        return int(stats.get("listeners")) if stats.get("listeners") is not None else None
    except (TypeError, ValueError):
        return None


class LastFmProvider:
    name = "lastfm"

    def __init__(self, api_key: str, http: HttpClient):
        self.api_key = api_key
        self.http = http

    def listeners(self, artist: str) -> int | None:
        data = self.http.get_json(
            BASE_URL,
            {"method": "artist.getinfo", "artist": artist, "api_key": self.api_key, "format": "json", "autocorrect": 1},
            cache_ttl=CACHE_TTL,
        )
        return parse_listeners(data)

    def enrich(self, events: list[Event]) -> list[str]:
        """Popuni artist_listeners gdje nedostaje. Vraća popis upozorenja."""
        warnings: list[str] = []
        cache: dict[str, int | None] = {}
        for event in events:
            if event.artist_listeners:
                continue
            key = normalize(event.artist)
            if not key:
                continue
            if key not in cache:
                try:
                    cache[key] = self.listeners(event.artist)
                except ProviderError as exc:
                    warnings.append(f"Last.fm: {exc}")
                    cache[key] = None
            event.artist_listeners = cache[key]
        return warnings
