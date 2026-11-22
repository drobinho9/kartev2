"""Deezer – broj fanova izvođača kao signal popularnosti. Radi BEZ API ključa.

Javni endpoint: https://api.deezer.com/search/artist?q=<izvođač> (ograničenje ~50 zahtjeva / 5 s).
Pretraga zna vratiti krivog izvođača na prvom mjestu (npr. 'Sting' → mali istoimeni profil),
zato se bira točno podudaranje imena s NAJVIŠE fanova.

Deezer fanovi ≠ Last.fm slušatelji: model ih skalira zasebno (model.toml: fans_low / fans_high).
Deezer je jak u Europi (posebno FR, DE, Balkan), slabiji u SAD-u – za američke izvođače radije koristi Last.fm.
"""

from __future__ import annotations

from karte.models import Event
from karte.net import HttpClient, ProviderError
from karte.util import normalize

BASE_URL = "https://api.deezer.com/search/artist"
CACHE_TTL = 7 * 24 * 3600


def _valid(data) -> bool:
    return isinstance(data, dict) and "error" not in data


def best_match(data: dict | None, artist: str) -> dict | None:
    """Kandidat s točno istim (normaliziranim) imenom i najviše fanova; None ako ga nema."""
    want = normalize(artist)
    if not want or not isinstance(data, dict):
        return None
    candidates = [a for a in data.get("data") or [] if isinstance(a, dict) and normalize(a.get("name")) == want]
    if not candidates:
        return None
    return max(candidates, key=lambda a: int(a.get("nb_fan") or 0))


class DeezerProvider:
    name = "deezer"

    def __init__(self, http: HttpClient):
        self.http = http

    def lookup(self, artist: str) -> dict | None:
        data = self.http.get_json(BASE_URL, {"q": artist, "limit": 10}, cache_ttl=CACHE_TTL, cache_if=_valid)
        if isinstance(data, dict) and "error" in data:
            err = data["error"] if isinstance(data["error"], dict) else {"message": str(data["error"])}
            raise ProviderError(f"Deezer: {err.get('message') or err}")
        match = best_match(data, artist)
        if not match:
            return None
        return {
            "id": match.get("id"),
            "name": match.get("name"),
            "fans": int(match.get("nb_fan") or 0),
            "link": match.get("link"),
        }

    def fans(self, artist: str) -> int | None:
        info = self.lookup(artist)
        return info["fans"] if info else None

    def enrich(self, events: list[Event], limit: int = 300) -> tuple[list[str], int]:
        """Popuni artist_fans gdje nedostaje. Vraća (upozorenja, broj pronađenih izvođača)."""
        warnings: list[str] = []
        cache: dict[str, int | None] = {}
        failures = 0
        for event in events:
            if event.artist_fans or event.segment != "music":
                continue
            key = normalize(event.artist)
            if not key:
                continue
            if key not in cache:
                if len(cache) >= limit:
                    continue
                try:
                    cache[key] = self.fans(event.artist)
                except ProviderError as exc:
                    failures += 1
                    cache[key] = None
                    if failures <= 2:
                        warnings.append(str(exc))
                    if failures >= 5:
                        warnings.append("Deezer: previše grešaka – prekidam obogaćivanje.")
                        break
            event.artist_fans = cache[key]
        found = sum(1 for v in cache.values() if v)
        return warnings, found
