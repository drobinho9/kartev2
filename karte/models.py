"""Podatkovni modeli."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Presale:
    name: str
    start: datetime | None = None
    end: datetime | None = None


@dataclass
class SecondaryMarket:
    """Stanje sekundarnog tržišta (oglašene cijene) za događaj."""

    source: str
    lowest: float | None = None
    median: float | None = None
    average: float | None = None
    listing_count: int | None = None
    currency: str = "EUR"
    observed: str | None = None  # kad je cijena zabilježena (YYYY-MM-DD) – stare cijene treba provjeriti


@dataclass
class Event:
    id: str
    name: str
    artist: str
    venue: str
    city: str
    country: str  # ISO 3166-1 alpha-2
    date: datetime
    source: str
    url: str | None = None
    face_min: float | None = None
    face_max: float | None = None
    currency: str = "EUR"
    # onsale | announced | soldout | offsale | cancelled | postponed | rescheduled
    status: str = "onsale"
    public_onsale: datetime | None = None
    presales: list[Presale] = field(default_factory=list)
    capacity: int | None = None
    capacity_estimated: bool = False
    ticket_limit: int | None = None
    personalized: bool | None = None
    tags: list[str] = field(default_factory=list)
    secondary: SecondaryMarket | None = None
    artist_listeners: int | None = None  # Last.fm slušatelji
    artist_fans: int | None = None  # Deezer fanovi (bez ključa) – zamjena kad nema Last.fm podatka
    artist_trend: float | None = None  # Wikipedia: prosjek pregleda zadnjih 14 dana / prethodnih 60 dana
    artist_pageviews: int | None = None  # Wikipedia: prosječni dnevni pregledi (zadnjih 14 dana)
    artist_upcoming_events: int | None = None
    shows_in_region: int = 1
    primary_vendor: str | None = None
    notes: str | None = None
    region: str | None = None  # savezna država / pokrajina (npr. "NY", "ON", "NSW")
    segment: str = "music"  # "music" (koncert) | "sport"
    sport: str | None = None  # football, american_football, basketball, baseball, hockey, tennis, motorsport, other
    league: str | None = None  # natjecanje / liga (npr. "Premier League", "UEFA Champions League", "NFL")

    @property
    def has_face_value(self) -> bool:
        return self.face_min is not None or self.face_max is not None


@dataclass
class PlatformOption:
    """Procjena prodaje jedne ulaznice na određenoj platformi."""

    key: str
    name: str
    list_price: float
    net_payout: float
    p_sell: float
    expected_value: float
    fee_pct: float
    capped: bool
    break_even_price: float
    payout: str
    notes: str
    trust_risk: float


@dataclass
class DemandResult:
    score: float
    confidence: float
    components: dict[str, float]
    notes: list[str] = field(default_factory=list)


@dataclass
class LegalResult:
    country: str
    country_name: str
    rule: str
    summary: str
    cap_price: float | None
    planned_applied: bool
    planned_rule: str | None
    risk: float
    profit_prohibited: bool
    sources: list[str] = field(default_factory=list)
    sport_rule: str | None = None  # pravilo iz sport.toml (criminal, club_terms, official_only, …)
    contract_prohibited: bool = False  # uvjeti kluba/organizatora zabranjuju preprodaju
    official_channel: str | None = None  # službeni kanal preprodaje (UEFA, razmjena kluba, FIFA tržište)
    sport_notes: list[str] = field(default_factory=list)  # kako klubovi/organizatori prodaju ulaznice


@dataclass
class Opportunity:
    event: Event
    phase: str
    days_to_event: int
    days_to_onsale: int | None
    demand: DemandResult
    face_ref: float | None
    buy_cost: float | None
    multiplier: float | None
    multiplier_source: str
    expected_resale: float | None
    legal: LegalResult
    platforms: list[PlatformOption]
    best: PlatformOption | None
    profit: float | None
    expected_value: float | None
    roi: float | None
    risk: float
    risk_flags: list[str]
    verdict: str
    verdict_reason: str
    suggested_qty: int
    advice: dict = field(default_factory=dict)
    # kad nominalna cijena nije poznata, ali postoje cijene s preprodaje:
    max_buy: float | None = None  # najviša nominalna cijena (EUR) uz koju je očekivani ROI ≥ cilj (verdict.buy_roi)
    breakeven_buy: float | None = None  # nominalna cijena (EUR) uz koju je očekivana dobit 0

    @property
    def listings_share(self) -> float | None:
        """Broj oglasa na sekundarnom tržištu kao udio kapaciteta (intenzitet preprodaje)."""
        sec = self.event.secondary
        if sec is None or not sec.listing_count or not self.event.capacity:
            return None
        return sec.listing_count / self.event.capacity

    @property
    def total_expected_value(self) -> float:
        if self.expected_value is None:
            return 0.0
        return self.expected_value * max(self.suggested_qty, 0)
