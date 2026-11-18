"""Jednostavan HTTP klijent (samo standardna biblioteka) s retry logikom, ograničenjem brzine i cacheom."""

from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from karte import __version__

SECRET_PARAMS = {"apikey", "api_key", "client_id", "client_secret", "key", "token"}


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

    def get_json(self, url: str, params: dict[str, Any] | None = None, cache_ttl: float | None = None) -> Any:
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
                headers={"User-Agent": f"karte/{__version__}", "Accept": "application/json"},
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                if self.cache is not None:
                    self.cache.set(full_url, data)
                return data
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    self._sleep(2 ** attempt)
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
