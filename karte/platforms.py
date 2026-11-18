"""Platforme za preprodaju i izračun neto isplate."""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from karte import knowledge

# Koliko lokalni kanal (oglasnik, Facebook) vrijedi kad je događaj izvan države prodavatelja
LOCAL_ABROAD_REACH = 0.35
LOCAL_ABROAD_TRUST_PENALTY = 0.15
LOCAL_ABROAD_PRICE_FACTOR = 0.9


@dataclass
class Platform:
    key: str
    name: str
    url: str
    seller_fee_pct: float
    seller_fee_fixed: float
    cap: str
    cap_pct: float
    cap_basis: str
    reach: float
    price_factor: float
    trust_risk: float
    countries: list[str]
    requires_vendor: str | None
    payout: str
    notes: str
    names: dict[str, str] = field(default_factory=dict)
    seller_countries: list[str] | None = None
    local: bool = False
    overrides: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, key: str, d: dict) -> "Platform":
        seller = d.get("seller_countries")
        return cls(
            key=key,
            name=d.get("name", key),
            url=d.get("url", ""),
            seller_fee_pct=float(d.get("seller_fee_pct", 0.0)),
            seller_fee_fixed=float(d.get("seller_fee_fixed", 0.0)),
            cap=d.get("cap", "none"),
            cap_pct=float(d.get("cap_pct", 0.0)),
            cap_basis=d.get("cap_basis", "face"),
            reach=float(d.get("reach", 0.5)),
            price_factor=float(d.get("price_factor", 1.0)),
            trust_risk=float(d.get("trust_risk", 0.3)),
            countries=[c.upper() if c != "*" else c for c in d.get("countries", ["*"])],
            requires_vendor=d.get("requires_vendor"),
            payout=d.get("payout", ""),
            notes=d.get("notes", ""),
            names=dict(d.get("names", {})),
            seller_countries=[c.upper() for c in seller] if seller else None,
            local=bool(d.get("local", False)),
            overrides={k.upper(): v for k, v in d.get("overrides", {}).items()},
        )

    def for_event(self, country: str | None, seller_country: str | None = None) -> "Platform":
        """Kopija s pravilima za državu događaja i korekcijom za lokalne kanale u inozemstvu."""
        p = self
        code = (country or "").upper()
        if code in self.overrides:
            changes = {k: v for k, v in self.overrides[code].items() if k in {f.name for f in dataclasses.fields(Platform)}}
            p = dataclasses.replace(p, **changes)
        if p.local and seller_country and code and code != seller_country.upper():
            p = dataclasses.replace(
                p,
                reach=p.reach * LOCAL_ABROAD_REACH,
                price_factor=p.price_factor * LOCAL_ABROAD_PRICE_FACTOR,
                trust_risk=min(1.0, p.trust_risk + LOCAL_ABROAD_TRUST_PENALTY),
            )
        return p

    def display_name(self, country: str | None = None) -> str:
        if country and country.upper() in self.names:
            return f"{self.names[country.upper()]} ({self.name.lower()})"
        return self.name

    def serves_event(self, country: str | None, vendor: str | None) -> bool:
        if self.requires_vendor and self.requires_vendor != vendor:
            return False
        return "*" in self.countries or (country or "").upper() in self.countries

    def accepts_seller(self, seller_country: str | None) -> bool:
        return not self.seller_countries or not seller_country or seller_country.upper() in self.seller_countries

    def available_for(self, country: str | None, vendor: str | None, seller_country: str | None = None) -> bool:
        return self.serves_event(country, vendor) and self.accepts_seller(seller_country)

    def cap_price(self, face_ref: float, buy_cost: float) -> float | None:
        if self.cap == "none":
            return None
        base = buy_cost if self.cap_basis == "paid" else face_ref
        if self.cap == "face":
            return base
        if self.cap == "percent":
            return base * (1 + self.cap_pct)
        return None

    def net(self, list_price: float) -> float:
        return list_price * (1 - self.seller_fee_pct) - self.seller_fee_fixed

    def break_even(self, buy_cost: float) -> float:
        """Oglasna cijena pri kojoj je neto isplata jednaka trošku kupnje."""
        return (buy_cost + self.seller_fee_fixed) / (1 - self.seller_fee_pct)

    @property
    def pays_after_event(self) -> bool:
        return "nakon" in self.payout.lower() and "događaj" in self.payout.lower()


def load_platforms() -> dict[str, Platform]:
    return {key: Platform.from_dict(key, d) for key, d in knowledge.platforms().items()}


def available_platforms(country: str | None, vendor: str | None, seller_country: str | None = None) -> list[Platform]:
    return [
        p.for_event(country, seller_country)
        for p in load_platforms().values()
        if p.available_for(country, vendor, seller_country)
    ]


def blocked_for_seller(country: str | None, vendor: str | None, seller_country: str | None) -> list[Platform]:
    """Platforme koje bi radile za događaj, ali ne primaju prodavatelje iz tvoje države."""
    return [p for p in load_platforms().values() if p.serves_event(country, vendor) and not p.accepts_seller(seller_country)]
