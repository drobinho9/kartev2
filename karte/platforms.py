"""Platforme za preprodaju i izračun neto isplate."""

from __future__ import annotations

from dataclasses import dataclass, field

from karte import knowledge


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

    @classmethod
    def from_dict(cls, key: str, d: dict) -> "Platform":
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
        )

    def display_name(self, country: str | None = None) -> str:
        if country and country.upper() in self.names:
            return f"{self.names[country.upper()]} ({self.name.lower()})"
        return self.name

    def available_for(self, country: str | None, vendor: str | None) -> bool:
        if self.requires_vendor and self.requires_vendor != vendor:
            return False
        return "*" in self.countries or (country or "").upper() in self.countries

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


def available_platforms(country: str | None, vendor: str | None) -> list[Platform]:
    return [p for p in load_platforms().values() if p.available_for(country, vendor)]
