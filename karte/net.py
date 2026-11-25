"""Jednostavan HTTP klijent (samo standardna biblioteka) s retry logikom, ograničenjem brzine i cacheom."""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from karte import __version__

SECRET_PARAMS = {"apikey", "api_key", "client_id", "client_secret", "key", "token"}


def user_agent() -> str:
    """User-Agent za sve zahtjeve. Wikimedia traži kontakt (e-mail ili URL) – postavi KARTE_USER_AGENT u .env."""
    return os.environ.get("KARTE_USER_AGENT") or f"karte/{__version__} (osobni alat za analizu ulaznica)"


class ProviderError(RuntimeError):
    pass


def redact(url: str) -> str:
    """Ukloni API ključeve iz URL-a prije ispisa u poruke/logove."""
    pattern = r"(?i)(" + "|".join(SECRET_PARAMS) + r")=[^&]+"
    return re.sub(pattern, r"\1=***", url)


class FileCache:
    def __init__(self, directory: Path, ttl_seconds: float):
        self.directory = Path(directory)
        self.ttl = ttl_seconds

    def _path(self, key: str) -> Path:
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
        return self.directory / f"{digest}.json"

    def get(self, key: str, ttl: float | None = None) -> Any | None:
        path = self._path(key)
        if not path.is_file():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        max_age = self.ttl if ttl is None else ttl
        if time.time() - payload.get("ts", 0) > max_age:
            return None
        return payload.get("data")

    def set(self, key: str, data: Any) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            self._path(key).write_text(json.dumps({"ts": time.time(), "data": data}), encoding="utf-8")
        except OSError:
            pass  # cache nije kritičan


class HttpClient:
    def __init__(
        self,
        cache: FileCache | None = None,
        timeout: float = 20.0,
        retries: int = 3,
        min_interval: float = 0.25,
        sleep=time.sleep,
    ):
        self.cache = cache
        self.timeout = timeout
        self.retries = retries
        self.min_interval = min_interval
        self._last_request = 0.0
        self._sleep = sleep

    def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        cache_ttl: float | None = None,
        headers: dict[str, str] | None = None,
        cache_if=None,
    ) -> Any:
        """GET + JSON. headers – dodatna zaglavlja (npr. Authorization); cache_if(data) → spremi u cache samo valjane odgovore."""
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
        full_url = f"{url}?{query}" if query else url
        if self.cache is not None:
            cached = self.cache.get(full_url, cache_ttl)
            if cached is not None:
                return cached

        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                self._sleep(wait)
            self._last_request = time.monotonic()
            request = urllib.request.Request(
                full_url,
                headers={"User-Agent": user_agent(), "Accept": "application/json", **(headers or {})},
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if self.cache is not None and (cache_if is None or cache_if(data)):
                    self.cache.set(full_url, data)
                return data
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    # poštuj Retry-After (Wikipedia/Wikimedia ga šalju uz 429), inače eksponencijalno čekanje
                    try:
                        delay = float(exc.headers.get("Retry-After")) if exc.headers else None
                    except (TypeError, ValueError):
                        delay = None
                    if delay is None:
                        delay = 2 ** (attempt + 1) if exc.code == 429 else 2 ** attempt
                    self._sleep(min(delay, 30))
                    continue
                body = ""
                try:
                    body = exc.read().decode("utf-8", "replace")[:300]
                except Exception:  # noqa: BLE001
                    pass
                raise ProviderError(f"HTTP {exc.code} za {redact(full_url)} {body}".strip()) from None
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                last_error = exc
                if attempt < self.retries:
                    self._sleep(2 ** attempt)
                    continue
        raise ProviderError(f"Neuspio zahtjev {redact(full_url)}: {last_error}")

    def get_text(self, url: str, params: dict[str, Any] | None = None, cache_ttl: float | None = None,
                 headers: dict[str, str] | None = None, max_bytes: int = 3_000_000) -> str:
        """GET tekstualnog sadržaja (npr. RSS/XML) s istim cacheom, ograničenjem brzine i ponovnim pokušajima."""
        query = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None}, doseq=True)
        full_url = f"{url}?{query}" if query else url
        key = "text:" + full_url
        if self.cache is not None:
            cached = self.cache.get(key, cache_ttl)
            if isinstance(cached, dict) and "text" in cached:
                return cached["text"]
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            wait = self.min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                self._sleep(wait)
            self._last_request = time.monotonic()
            request = urllib.request.Request(
                full_url,
                headers={"User-Agent": user_agent(), "Accept": "application/rss+xml, application/xml, text/xml, */*", **(headers or {})},
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    raw = resp.read(max_bytes + 1)[:max_bytes]
                    charset = resp.headers.get_content_charset() or "utf-8"
                text = raw.decode(charset, "replace")
                if self.cache is not None:
                    self.cache.set(key, {"text": text})
                return text
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    self._sleep(min(2 ** (attempt + 1), 30))
                    continue
                raise ProviderError(f"HTTP {exc.code} za {redact(full_url)}") from None
            except (urllib.error.URLError, TimeoutError, ValueError) as exc:
                last_error = exc
                if attempt < self.retries:
                    self._sleep(2 ** attempt)
                    continue
        raise ProviderError(f"Neuspio zahtjev {redact(full_url)}: {last_error}")
