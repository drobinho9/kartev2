import json
from datetime import datetime
from pathlib import Path

import pytest

from karte.models import Event

FIXTURES = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 18, 10, 0, 0)


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def _bez_rasporeda(monkeypatch):
    """Testovi rade bez mreže: raspored nogometnih utakmica (fixturedownload.com) se ne dohvaća."""
    monkeypatch.setenv("KARTE_BEZ_RASPOREDA", "1")


@pytest.fixture
def now():
    return NOW


@pytest.fixture
def make_event():
    def _make(**kw) -> Event:
        base = dict(
            id="t1",
            name="Test",
            artist="Test Artist",
            venue="Arena Zagreb",
            city="Zagreb",
            country="HR",
            date=datetime(2027, 1, 20, 20, 0),
            source="test",
            face_min=50.0,
            face_max=100.0,
            currency="EUR",
            status="onsale",
            capacity=16000,
            personalized=False,
            artist_listeners=1_000_000,
            artist_upcoming_events=20,
            primary_vendor="entrio",
        )
        base.update(kw)
        return Event(**base)

    return _make


class FakeHttp:
    """Zamjena za HttpClient: vraća fixture prema URL-u i bilježi pozive."""

    def __init__(self, routes: dict[str, object]):
        self.routes = routes
        self.calls: list[tuple[str, dict]] = []
        self.headers: list[dict] = []

    def get_json(self, url, params=None, cache_ttl=None, headers=None, cache_if=None):
        self.calls.append((url, dict(params or {})))
        self.headers.append(dict(headers or {}))
        for prefix, payload in self.routes.items():
            if url.startswith(prefix):
                return payload(params) if callable(payload) else payload
        raise AssertionError(f"Neočekivan URL {url}")

    def get_text(self, url, params=None, cache_ttl=None, headers=None, max_bytes=None):
        self.calls.append((url, dict(params or {})))
        for prefix, payload in self.routes.items():
            if url.startswith(prefix):
                result = payload(params) if callable(payload) else payload
                if isinstance(result, Exception):
                    raise result
                return result
        raise AssertionError(f"Neočekivan URL {url}")
