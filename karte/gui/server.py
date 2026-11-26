"""Lokalno grafičko sučelje: mali HTTP server (samo standardna biblioteka) + jednostranična web aplikacija.

Pokretanje: `karte gui` → otvara http://127.0.0.1:8765 u pregledniku.
Server sluša SAMO na 127.0.0.1 (nije dostupan s mreže) i odbija zahtjeve s tuđih web stranica (provjera Origin zaglavlja).
"""

from __future__ import annotations

import json
import mimetypes
import threading
import traceback
import urllib.parse
import webbrowser

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path

from karte import __version__, legal
from karte.categories import KINDS
from karte.journal import STATUSES, Journal, default_path
from karte.knowledge import ModelConfig, expand_countries, laws, markets, regions, vendors
from karte.markdown import render, title_of
from karte.net import FileCache, HttpClient, ProviderError
from karte.pipeline import ScanOptions, run_scan
from karte.platforms import load_platforms
from karte.providers.deezer import DeezerProvider
from karte.providers.lastfm import LastFmProvider
from karte.providers.wikipedia import WikipediaProvider
from karte.report import RENDERERS
from karte.scoring import CATEGORIES
from karte.sport import SPORT_LABELS
from karte.service import calculate, categories, market_rows, opportunity_dict
from karte.settings import Settings
from karte.snapshot import load_snapshot
from karte.util import parse_float, parse_int

MAX_BODY = 5 * 1024 * 1024
TAGS = {
    "farewell": "Oproštajna turneja",
    "reunion": "Reunion / povratak benda",
    "first_visit": "Prvi put u državi",
    "added_date": "Dodatni datum (prvi rasprodan)",
    "regional_star": "Regionalna zvijezda",
    "anniversary": "Obljetnička turneja",
    "new_album": "Novi album",
    "festival_headliner": "Headliner festivala",
    "derby": "Sport: derbi",
    "final": "Sport: finale",
    "playoff": "Sport: doigravanje / nokaut",
    "rivalry": "Sport: rivalstvo",
    "big_match": "Sport: velika utakmica",
    "title_decider": "Sport: odlučuje o naslovu",
    "legend_farewell": "Sport: oproštaj legende",
}
def vendor_options() -> dict[str, str]:
    """Primarni prodavači iz vendors.toml: ključ → 'Naziv (države)'; domaći prvi."""
    items = []
    for key, info in vendors().items():
        countries = info.get("countries", [])
        label = f"{info.get('name', key)} ({', '.join(countries[:5])}{'…' if len(countries) > 5 else ''})"
        items.append((0 if "HR" in countries else 1, label.lower(), key, label))
    return {**{key: label for _, _, key, label in sorted(items)}, "": "Ostalo / ne znam"}
CATEGORY_LABELS = {"cheap": "Najjeftinija kategorija", "mid": "Srednja", "premium": "Najskuplja"}


def guide_list() -> list[dict]:
    folder = resources.files("karte.data").joinpath("guides")
    out = []
    for item in sorted(folder.iterdir(), key=lambda p: p.name):
        if item.name.endswith(".md"):
            text = item.read_text(encoding="utf-8")
            slug = item.name[:-3]
            out.append({"slug": slug, "title": title_of(text), "html": render(text)})
    return out


class App:
    def __init__(self, settings: Settings, journal_path: Path | None = None, model_path: str | None = None, fixtures: bool = False):
        self.settings = settings
        self.model_path = model_path
        self.fixtures = fixtures  # dohvaćaj raspored nogometnih utakmica (mreža) – uključeno u `karte gui`
        self.journal = Journal(journal_path or default_path())
        self._http = HttpClient(cache=FileCache(settings.cache_dir, ttl_seconds=6 * 3600))

    # ------------------------------------------------------------ meta
    def meta(self) -> dict:
        names = {code: info.get("name", code) for code, info in laws().items() if code != "default" and "-" not in code}
        for code, info in markets().items():
            names.setdefault(code, info.get("name", code))
        subdivisions = sorted(code for code in laws() if "-" in code)
        return {
            "version": __version__,
            "regions": regions(),
            "countries": [{"code": c, "name": n} for c, n in sorted(names.items(), key=lambda t: t[1])],
            "subdivisions": subdivisions,
            "categories": CATEGORY_LABELS,
            "tags": TAGS,
            "vendors": vendor_options(),
            "kinds": {k: v[0] for k, v in KINDS.items()},
            "sports": SPORT_LABELS,
            "statuses": STATUSES,
            "platforms": sorted({p.name for p in load_platforms().values()}),
            "snapshot": self._snapshot_info(),
            "settings": {
                "ticketmaster": bool(self.settings.ticketmaster_api_key),
                "lastfm": bool(self.settings.lastfm_api_key),
                "seatgeek": bool(self.settings.seatgeek_client_id),
                "serpapi": bool(self.settings.serpapi_key),
                "predicthq": bool(self.settings.predicthq_token),
                "api_football": bool(self.settings.api_football_key),
                "live_sources": self.settings.live_sources,
                "seller_country": self.settings.seller_country,
                "countries": ",".join(self.settings.countries),
                "budget": self.settings.budget,
                "journal_path": str(self.journal.path),
            },
        }

    @staticmethod
    def _snapshot_info() -> dict | None:
        try:
            _, info, _ = load_snapshot()
            return info.as_dict()
        except Exception:  # noqa: BLE001 – oštećena korisnička snimka ne smije srušiti sučelje
            return None

    # ------------------------------------------------------------ scan
    def _scan_options(self, body: dict) -> ScanOptions:
        csv_texts = []
        if (body.get("csv_text") or "").strip():
            csv_texts.append((body.get("csv_name") or "upload.csv", body["csv_text"]))
        return ScanOptions(
            days=parse_int(body.get("days")) or 60,
            onsale_days=parse_int(body.get("onsale_days")) if body.get("onsale_days") not in (None, "") else 30,
            countries=expand_countries(body.get("countries") or self.settings.countries),
            budget=parse_float(body.get("budget")) or self.settings.budget,
            category=body.get("category") if body.get("category") in CATEGORIES else "cheap",
            strict=bool(body.get("strict")),
            demo=body.get("source") == "demo" or bool(body.get("demo")),
            snapshot=body.get("source") == "snapshot",
            csv_texts=csv_texts,
            show_all=bool(body.get("show_all")),
            seller_country=(body.get("seller_country") or self.settings.seller_country).upper(),
            max_artists=parse_int(body.get("max_artists")) or 300,
            segment=body.get("segment") if body.get("segment") in ("music", "sport", "all") else "all",
            model_path=self.model_path,
            use_fixtures=self.fixtures and body.get("fixtures") is not False,
            football_all=bool(body.get("football_all")),
            football_risk=self.settings.football_risk,
            use_learned=self.fixtures,
        )

    def _source(self, body: dict) -> dict:
        """Paketi/Nogomet: bez odabira izvora → živi izvori ako postoje ključevi, inače snimka stvarnih događaja."""
        if body.get("source") not in ("live", "snapshot", "demo"):
            body = {**body, "source": "live" if self.settings.live_sources else "snapshot"}
        return body

    def packages(self, body: dict) -> dict:
        from karte.service import packages

        return packages(self._scan_options(self._source(body)), self.settings)

    def football(self, body: dict) -> dict:
        from karte.service import football_matches

        body = self._source(body)
        if not body.get("countries"):
            body["countries"] = "europa"
        return football_matches(self._scan_options(body), self.settings)

    def scan(self, body: dict) -> dict:
        result = run_scan(self._scan_options(body), self.settings)
        return {
            "generated_at": result.generated_at.isoformat(),
            "is_demo": result.is_demo,
            "is_snapshot": result.is_snapshot,
            "snapshot": result.snapshot,
            "countries": result.options.countries,
            "sources": result.sources,
            "warnings": result.warnings,
            "opportunities": [opportunity_dict(op) for op in result.opportunities],
        }

    def plan(self, body: dict) -> dict:
        from karte.portfolio import build_plan

        opts = self._scan_options(body)
        result = run_scan(opts, self.settings)
        plan = build_plan(result.opportunities, opts.budget, result.evaluator)
        return {
            **plan.as_dict(),
            "is_snapshot": result.is_snapshot,
            "is_demo": result.is_demo,
            "sources": result.sources,
            "warnings": result.warnings,
        }

    def report(self, body: dict) -> tuple[str, str, str]:
        fmt = body.get("format") if body.get("format") in ("html", "md", "csv", "json") else "html"
        result = run_scan(self._scan_options(body), self.settings)
        text = RENDERERS[fmt](result)
        ctype = {"html": "text/html", "md": "text/markdown", "csv": "text/csv", "json": "application/json"}[fmt]
        return text, f"{ctype}; charset=utf-8", f"izvjestaj.{fmt}"

    # ------------------------------------------------------------ ostalo
    def calc(self, body: dict) -> dict:
        return {"opportunity": opportunity_dict(calculate(body, self.settings, self.model_path))}

    def cats(self, body: dict) -> dict:
        return categories(body.get("event") or {}, body.get("categories") or [], self.settings, self.model_path)

    def listeners(self, artist: str) -> dict:
        if not self.settings.lastfm_api_key:
            return {"listeners": None, "error": "LASTFM_API_KEY nije postavljen u .env"}
        try:
            return {"listeners": LastFmProvider(self.settings.lastfm_api_key, self._http).listeners(artist)}
        except ProviderError as exc:
            return {"listeners": None, "error": str(exc)}

    def popularity(self, artist: str) -> dict:
        """Deezer fanovi + Wikipedia trend (bez ključeva)."""
        artist = (artist or "").strip()
        if not artist:
            return {"error": "Upiši izvođača."}
        out: dict = {"artist": artist}
        try:
            found = DeezerProvider(self._http).lookup(artist)
            out["fans"] = found["fans"] if found else None
            out["deezer_name"] = found["name"] if found else None
        except ProviderError as exc:
            out["fans"], out["error"] = None, str(exc)
        try:
            wp = WikipediaProvider(self._http)
            title = wp.resolve_titles([artist]).get(artist)
            out["wiki_title"] = title
            if title:
                out["pageviews"], out["trend"] = wp.trend(title)
        except ProviderError as exc:
            out.setdefault("error", str(exc))
        return out

    def announcements(self, days: int, region: str) -> dict:
        from karte.announcements import fetch_announcements
        from karte.snapshot import data_dir

        items, warnings = fetch_announcements(self._http, days=days, data_dir=data_dir())
        minimum = {"hr": 3, "regija": 2, "europa": 1, "sve": 0}.get(region, 1)
        shown = [a.as_dict() for a in items if a.region_score >= minimum]
        return {"items": shown, "warnings": warnings, "total": len(items)}

    @staticmethod
    def announcements_seen(body: dict) -> dict:
        from karte.announcements import mark_seen
        from karte.snapshot import data_dir

        links = [str(x) for x in body.get("links") or []][:2000]
        mark_seen(data_dir(), links)
        return {"marked": len(links)}

    @staticmethod
    def announcements_source(body: dict) -> dict:
        from karte.announcements import add_source, load_sources
        from karte.snapshot import data_dir

        added, source = add_source(data_dir(), str(body.get("url") or ""), str(body.get("naziv") or ""),
                                   "turneje" if body.get("samo_koncerti") else "opcenito")
        return {"added": added, "source": source, "count": len(load_sources(data_dir() / "najave.toml"))}

    @staticmethod
    def capture_parse(body: dict) -> dict:
        from karte.capture import decode_payload, event_rows

        payload = body.get("payload")
        if isinstance(payload, str):
            payload = decode_payload(payload)
        if not isinstance(payload, dict):
            raise ValueError("neispravni podaci za uvoz")
        return {"rows": event_rows(payload), "url": payload.get("url", "")}

    @staticmethod
    def my_events(port: int) -> dict:
        from karte.capture import bookmarklet
        from karte.snapshot import _row_key, list_user_events, user_dir

        rows = [{**r, "key": _row_key(r)} for r in list_user_events()]
        return {"rows": rows, "bookmarklet": bookmarklet(port), "path": str(user_dir() / "dogadaji.csv")}

    def my_events_save(self, body: dict, port: int) -> dict:
        from karte.snapshot import save_user_events

        rows = [r for r in body.get("rows") or [] if isinstance(r, dict)]
        added, updated = save_user_events(rows)
        return {"added": added, "updated": updated, **self.my_events(port)}

    def law(self, code: str) -> dict:
        country, _, region = code.upper().partition("-")
        info = legal.country_info(country, region or None)
        return {"code": code.upper(), **{k: v for k, v in info.items() if not k.startswith("_")}}

    def journal_data(self) -> dict:
        return {
            "trades": [t.to_row() for t in self.journal.list()],
            "stats": self.journal.stats(ModelConfig.load(self.model_path)),
        }


class Handler(BaseHTTPRequestHandler):
    app: App
    server_version = f"karte/{__version__}"

    def log_message(self, fmt, *args):  # tiši log
        if getattr(self.server, "verbose", False):
            super().log_message(fmt, *args)

    # ------------------------------------------------------------ helpers
    def _send(self, status: int, body: bytes, ctype: str, extra: dict | None = None):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass  # preglednik je zatvorio vezu (npr. promjena kartice) – nije greška

    def _json(self, obj, status: int = 200):
        self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"), "application/json; charset=utf-8")

    def _error(self, status: int, message: str):
        self._json({"error": message}, status)

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        if not origin:
            return True
        host = self.headers.get("Host", "")
        return origin in (f"http://{host}", f"http://127.0.0.1:{self.server.server_port}", f"http://localhost:{self.server.server_port}")

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            raise ValueError("Zahtjev je prevelik.")
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def _static(self, name: str):
        name = name or "index.html"
        if "/" in name or name.startswith("."):
            return self._error(404, "Nema datoteke.")
        try:
            data = resources.files("karte.gui").joinpath("static", name).read_bytes()
        except (FileNotFoundError, OSError):
            return self._error(404, "Nema datoteke.")
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, data, ctype, {"Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:"})

    def _guard(self, fn):
        try:
            fn()
        except (ValueError, KeyError, TypeError) as exc:
            self._error(400, f"Neispravan zahtjev: {exc}")
        except Exception as exc:  # noqa: BLE001 – sučelje ne smije pasti
            traceback.print_exc()
            self._error(500, f"Greška: {exc}")

    # ------------------------------------------------------------ rute
    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(url.query)
        path = url.path
        app = self.app

        def run():
            if path in ("/", "/index.html"):
                return self._static("index.html")
            if path.startswith("/static/"):
                return self._static(path[len("/static/"):])
            if path == "/api/meta":
                return self._json(app.meta())
            if path == "/api/markets":
                return self._json({"rows": market_rows()})
            if path == "/api/laws":
                return self._json(app.law((q.get("code") or ["HR"])[0]))
            if path == "/api/listeners":
                return self._json(app.listeners((q.get("artist") or [""])[0]))
            if path == "/api/popularity":
                return self._json(app.popularity((q.get("artist") or [""])[0]))
            if path == "/api/najave":
                return self._json(app.announcements(parse_int((q.get("dana") or ["21"])[0]) or 21, (q.get("regija") or ["europa"])[0]))
            if path == "/api/moji":
                return self._json(app.my_events(self.server.server_port))
            if path == "/api/guides":
                return self._json({"guides": guide_list()})
            if path == "/api/journal":
                return self._json(app.journal_data())
            if path == "/api/journal/export":
                return self._send(200, app.journal.export_csv().encode("utf-8"), "text/csv; charset=utf-8",
                                  {"Content-Disposition": 'attachment; filename="moje_prodaje.csv"'})
            if path == "/api/health":
                return self._json({"ok": True})
            return self._error(404, "Nepoznata ruta.")

        self._guard(run)

    def do_POST(self):
        if not self._origin_ok():
            return self._error(403, "Zahtjev s druge stranice nije dopušten.")
        path = urllib.parse.urlparse(self.path).path
        app = self.app

        def run():
            body = self._body()
            if path == "/api/scan":
                return self._json(app.scan(body))
            if path == "/api/report":
                text, ctype, fname = app.report(body)
                return self._send(200, text.encode("utf-8"), ctype, {"Content-Disposition": f'attachment; filename="{fname}"'})
            if path == "/api/calc":
                return self._json(app.calc(body))
            if path == "/api/plan":
                return self._json(app.plan(body))
            if path == "/api/paketi":
                return self._json(app.packages(body))
            if path == "/api/nogomet":
                return self._json(app.football(body))
            if path == "/api/najave/procitano":
                return self._json(app.announcements_seen(body))
            if path == "/api/najave/izvor":
                return self._json(app.announcements_source(body))
            if path == "/api/uvoz/parse":
                return self._json(app.capture_parse(body))
            if path == "/api/moji":
                return self._json(app.my_events_save(body, self.server.server_port))
            if path == "/api/categories":
                return self._json(app.cats(body))
            if path == "/api/journal":
                trade = app.journal.upsert(body)
                return self._json({"trade": trade.to_row(), **app.journal_data()})
            if path == "/api/journal/import":
                n = app.journal.import_csv(body.get("csv_text") or "")
                return self._json({"imported": n, **app.journal_data()})
            return self._error(404, "Nepoznata ruta.")

        self._guard(run)

    def do_DELETE(self):
        if not self._origin_ok():
            return self._error(403, "Zahtjev s druge stranice nije dopušten.")
        url = urllib.parse.urlparse(self.path)
        path = url.path
        if path == "/api/moji":
            from karte.snapshot import delete_user_event

            key = (urllib.parse.parse_qs(url.query).get("kljuc") or [""])[0]
            ok = delete_user_event(key)
            return self._json({"deleted": ok, **self.app.my_events(self.server.server_port)}, 200 if ok else 404)
        if path.startswith("/api/journal/"):
            ok = self.app.journal.delete(path.rsplit("/", 1)[-1])
            return self._json({"deleted": ok, **self.app.journal_data()}, 200 if ok else 404)
        return self._error(404, "Nepoznata ruta.")


def make_server(app: App, host: str = "127.0.0.1", port: int = 8765, tries: int = 10) -> ThreadingHTTPServer:
    handler = type("KarteHandler", (Handler,), {"app": app})
    last: OSError | None = None
    for p in range(port, port + tries):
        try:
            server = ThreadingHTTPServer((host, p), handler)
            server.daemon_threads = True
            return server
        except OSError as exc:
            last = exc
    raise OSError(f"Nema slobodnog porta {port}–{port + tries - 1}: {last}")


def serve(settings: Settings, port: int = 8765, open_browser: bool = True, journal_path: Path | None = None,
          model_path: str | None = None, verbose: bool = False) -> None:
    app = App(settings, journal_path, model_path, fixtures=True)
    server = make_server(app, port=port)
    server.verbose = verbose
    url = f"http://127.0.0.1:{server.server_port}/"
    print(f"karte {__version__} – grafičko sučelje radi na {url}")
    print(f"Dnevnik prodaja: {app.journal.path}")
    print("Zaustavi s Ctrl+C.")
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nZaustavljeno.")
    finally:
        server.server_close()



