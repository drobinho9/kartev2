"""Model procjene potražnje, cijene preprodaje, očekivane zarade i rizika.

Model je namjerno jednostavan i transparentan: svaki korak je objašnjen u docs/MODEL.md
i svi parametri su u karte/data/model.toml (mogu se kalibrirati vlastitim podacima).
"""

from __future__ import annotations

import math
from datetime import datetime

from karte import legal
from karte.knowledge import ModelConfig
from karte.models import DemandResult, Event, Opportunity, PlatformOption
from karte.platforms import Platform, available_platforms
from karte.util import clamp, days_between, log_scale, utcnow

VERDICT_ORDER = {
    "KUPI": 0,
    "RAZMOTRI": 1,
    "RASPRODANO": 2,
    "PRESKOČI": 3,
    "ZAKONSKI OGRANIČENO": 4,
    "NEMA CIJENE": 5,
    "OTKAZANO": 6,
}

CATEGORIES = ("cheap", "mid", "premium")


class Evaluator:
    def __init__(
        self,
        config: ModelConfig | None = None,
        budget: float = 1000.0,
        category: str = "cheap",
        strict: bool = False,
        now: datetime | None = None,
    ):
        if category not in CATEGORIES:
            raise ValueError(f"Nepoznata kategorija '{category}', dopušteno: {', '.join(CATEGORIES)}")
        self.cfg = config or ModelConfig.load()
        self.budget = budget
        self.category = category
        self.strict = strict
        self.now = now or utcnow()

    # ------------------------------------------------------------------ cijene
    def face_reference(self, event: Event) -> float | None:
        fmin = self.cfg.to_eur(event.face_min, event.currency)
        fmax = self.cfg.to_eur(event.face_max, event.currency)
        if fmin is None and fmax is None:
            return None
        if self.category == "cheap":
            return fmin if fmin is not None else fmax
        if self.category == "premium":
            return fmax if fmax is not None else fmin
        if fmin is not None and fmax is not None:
            return (fmin + fmax) / 2
        return fmin if fmin is not None else fmax

    def secondary_reference(self, event: Event) -> tuple[float | None, float | None]:
        """(sirova oglašena cijena, realna očekivana prodavateljeva cijena) u EUR.

        Oglašene cijene na viagogu/StubHubu uključuju kupčeve naknade, pa se umanjuju za buyer_fee_share
        (osim kad je izvor lokalni oglasnik bez naknada), a zatim za haircut (oglas ≠ prodaja).
        """
        sec = event.secondary
        if sec is None:
            return None, None
        r = self.cfg.section("resale")
        lowest = self.cfg.to_eur(sec.lowest, sec.currency)
        median = self.cfg.to_eur(sec.median, sec.currency)
        average = self.cfg.to_eur(sec.average, sec.currency)
        source = (sec.source or "").lower()
        fee_free = any(k in source for k in ("njuškalo", "njuskalo", "oglas", "facebook", "lokal"))
        net_of_fees = 1.0 if fee_free else 1 - r.get("buyer_fee_share", 0.0)
        if self.category == "cheap":
            if lowest:
                return lowest, lowest * net_of_fees * r["haircut_lowest"]
            if median:
                return median, median * net_of_fees * r["haircut_median"]
        else:
            for value in (median, average):
                if value:
                    return value, value * net_of_fees * r["haircut_median"]
            if lowest:
                return lowest, lowest * net_of_fees * r["haircut_lowest"]
        return None, None

    # --------------------------------------------------------------- potražnja
    def demand(self, event: Event, face_ref: float | None) -> DemandResult:
        d = self.cfg.section("demand")
        notes: list[str] = []
        listeners = event.artist_listeners

        popularity = log_scale(listeners, d["listeners_low"], d["listeners_high"])
        if popularity is None:
            popularity = d["default_popularity"]
            notes.append("Nema podatka o popularnosti izvođača (Last.fm) – korištena zadana vrijednost.")

        capacity = event.capacity
        if not capacity:
            capacity = d["default_capacity"]
            notes.append(f"Nepoznat kapacitet dvorane – pretpostavljeno {capacity}.")
        shows = max(1, event.shows_in_region)
        if listeners:
            scarcity = log_scale(listeners / (capacity * shows), d["ratio_low"], d["ratio_high"])
            scarcity = d["default_scarcity"] if scarcity is None else scarcity
        else:
            scarcity = d["default_scarcity"]
        if shows > 1:
            word = "koncerta" if shows in (2, 3, 4) else "koncerata"
            notes.append(f"Izvođač ima {shows} {word} u istoj državi – veća ponuda, manja rijetkost.")

        if event.artist_upcoming_events:
            small, large = d["tour_small"], d["tour_large"]
            tour = clamp(1 - (event.artist_upcoming_events - small) / (large - small))
        else:
            tour = d["default_tour"]

        buzz_cfg = self.cfg.section("buzz")
        buzz = sum(float(buzz_cfg.get(tag, 0.0)) for tag in event.tags)
        if event.status == "soldout":
            buzz += float(buzz_cfg.get("soldout", 0.0))
        buzz = clamp(buzz)

        weights = {"popularity": d["weight_popularity"], "scarcity": d["weight_scarcity"], "tour": d["weight_tour"]}
        comps = {"popularity": popularity, "scarcity": scarcity, "tour": tour}
        base = sum(comps[k] * w for k, w in weights.items()) / sum(weights.values())
        comps["buzz"] = buzz
        base = base + d["buzz_strength"] * buzz * (1 - base)
        score = base

        raw_secondary, realistic_secondary = self.secondary_reference(event)
        if realistic_secondary and face_ref:
            # realni (prodavateljev) multiplikator: 0.7× → 0, 2.0× → 1
            observed = realistic_secondary / face_ref
            secondary_signal = clamp((observed - 0.7) / 1.3)
            comps["secondary"] = secondary_signal
            w = d["secondary_weight"]
            score = (1 - w) * base + w * secondary_signal

        confidence = 0.15
        confidence += 0.35 if listeners else 0.0
        confidence += 0.15 if (event.capacity and not event.capacity_estimated) else (0.10 if event.capacity else 0.0)
        confidence += 0.15 if face_ref else 0.0
        confidence += 0.20 if raw_secondary else 0.0
        comps["base"] = base
        return DemandResult(score=clamp(score), confidence=clamp(confidence), components=comps, notes=notes)

    # ------------------------------------------------------------------- faza
    def phase(self, event: Event) -> tuple[str, int | None]:
        starts = [p.start for p in event.presales if p.start] + ([event.public_onsale] if event.public_onsale else [])
        first_sale = min(starts) if starts else None
        days_to_onsale = days_between(self.now, first_sale) if first_sale and first_sale > self.now else None
        status = event.status
        if status == "cancelled":
            return "OTKAZANO", days_to_onsale
        if status in ("postponed", "rescheduled"):
            return "ODGOĐENO", days_to_onsale
        if status == "soldout":
            return "RASPRODANO", days_to_onsale
        if first_sale and first_sale > self.now:
            return "NAJAVA", days_to_onsale
        if status == "offsale":
            return "NIJE U PRODAJI", days_to_onsale
        return "U PRODAJI", days_to_onsale

    # --------------------------------------------------------------- evaluacija
    def evaluate(self, event: Event) -> Opportunity:
        cfg = self.cfg
        face_ref = self.face_reference(event)
        demand = self.demand(event, face_ref)
        phase, days_to_onsale = self.phase(event)
        days_to_event = days_between(self.now, event.date)

        pct, fixed = cfg.primary_fee(event.primary_vendor)
        buy_cost = face_ref * (1 + pct) + fixed if face_ref is not None else None

        multiplier = None
        multiplier_source = "—"
        expected_resale = None
        if face_ref:
            _, realistic = self.secondary_reference(event)
            r = cfg.section("resale")
            if realistic:
                multiplier = realistic / face_ref
                multiplier_source = f"sekundarno tržište ({event.secondary.source})"
            else:
                multiplier = r["base_multiplier"] + r["demand_slope"] * demand.score ** r["demand_exponent"]
                multiplier_source = "model (procjena iz potražnje)"
            if days_to_event <= r["late_days"] and demand.score < r["late_decay_max_demand"]:
                multiplier *= r["late_decay"]
            expected_resale = face_ref * multiplier

        legal_result = legal.evaluate(event.country, face_ref, buy_cost, strict=self.strict)

        options: list[PlatformOption] = []
        best: PlatformOption | None = None
        best_platform: Platform | None = None
        if face_ref and buy_cost and expected_resale:
            ranked: list[tuple[float, PlatformOption, Platform]] = []
            for platform in available_platforms(event.country, event.primary_vendor):
                option = self._platform_option(platform, event, face_ref, buy_cost, expected_resale, legal_result.cap_price, demand.score)
                options.append(option)
                rank = option.expected_value - platform.trust_risk * 0.05 * buy_cost
                ranked.append((rank, option, platform))
            ranked.sort(key=lambda t: t[0], reverse=True)
            options = [o for _, o, _ in ranked]
            if ranked:
                _, best, best_platform = ranked[0]

        profit = best.net_payout - buy_cost if best and buy_cost else None
        ev = best.expected_value if best else None
        roi = ev / buy_cost if (ev is not None and buy_cost) else None

        risk, flags = self._risk(event, demand, legal_result, best_platform, days_to_event, phase)
        verdict, reason = self._verdict(event, phase, face_ref, legal_result, roi, demand.score, risk)
        if phase == "NIJE U PRODAJI" and verdict in ("KUPI", "RAZMOTRI"):
            reason += " Napomena: izvor trenutno ne prodaje ulaznice (možda rasprodano) – provjeri dostupnost."
        qty = self._quantity(verdict, event, buy_cost, demand.score)

        return Opportunity(
            event=event,
            phase=phase,
            days_to_event=days_to_event,
            days_to_onsale=days_to_onsale,
            demand=demand,
            face_ref=face_ref,
            buy_cost=buy_cost,
            multiplier=multiplier,
            multiplier_source=multiplier_source,
            expected_resale=expected_resale,
            legal=legal_result,
            platforms=options,
            best=best,
            profit=profit,
            expected_value=ev,
            roi=roi,
            risk=risk,
            risk_flags=flags,
            verdict=verdict,
            verdict_reason=reason,
            suggested_qty=qty,
        )

    def _platform_option(
        self,
        platform: Platform,
        event: Event,
        face_ref: float,
        buy_cost: float,
        expected_resale: float,
        legal_cap: float | None,
        demand: float,
    ) -> PlatformOption:
        s = self.cfg.section("sell")
        list_price = expected_resale * platform.price_factor
        capped = False
        if legal_cap is not None and list_price > legal_cap:
            list_price, capped = legal_cap, True
        platform_cap = platform.cap_price(face_ref, buy_cost)
        if platform_cap is not None and list_price > platform_cap:
            list_price, capped = platform_cap, True
        net = platform.net(list_price)
        p_sell = clamp(s["p_base"] + s["p_slope"] * demand)
        p_sell *= s["reach_floor"] + (1 - s["reach_floor"]) * platform.reach
        if event.secondary is not None:
            p_sell += s.get("secondary_bonus", 0.0)
        if capped:
            p_sell += s.get("capped_bonus", 0.0)
        p_sell = min(p_sell, s.get("p_max", 0.97))
        salvage = 0.0 if event.personalized else s["salvage_ratio"] * face_ref
        expected_value = p_sell * net + (1 - p_sell) * salvage - buy_cost
        return PlatformOption(
            key=platform.key,
            name=platform.display_name(event.country),
            list_price=list_price,
            net_payout=net,
            p_sell=p_sell,
            expected_value=expected_value,
            fee_pct=platform.seller_fee_pct,
            capped=capped,
            break_even_price=platform.break_even(buy_cost),
            payout=platform.payout,
            notes=platform.notes,
            trust_risk=platform.trust_risk,
        )

    def _risk(self, event, demand, legal_result, best_platform, days_to_event, phase) -> tuple[float, list[str]]:
        r = self.cfg.section("risk")
        risk = 0.0
        flags: list[str] = []
        if event.personalized is True:
            risk += r["personalized"]
            flags.append("Personalizirane ulaznice (ime na ulaznici) – preprodaja može biti nemoguća ili traži službenu promjenu imena.")
        elif event.personalized is None:
            risk += r["unknown_personalization"]
            flags.append("Nije poznato jesu li ulaznice personalizirane – provjeri uvjete prodaje prije kupnje.")
        risk += legal_result.risk * r["legal_weight"]
        if legal_result.risk >= 0.5:
            flags.append(f"Pravni rizik ({legal_result.country_name}): {legal.RULE_LABELS.get(legal_result.rule, legal_result.rule)}.")
        if legal_result.planned_rule and not legal_result.planned_applied:
            flags.append(
                f"Najavljeno zakonsko ograničenje u državi {legal_result.country_name} "
                f"({legal.RULE_LABELS.get(legal_result.planned_rule, legal_result.planned_rule)}) – pokreni s --strict za konzervativan izračun."
            )
        if demand.confidence < 0.5:
            risk += r["low_confidence"] * (1 - demand.confidence)
            flags.append("Malo ulaznih podataka – procjena je nepouzdana; ručno provjeri cijene na sekundarnom tržištu.")
        if days_to_event > r["far_event_days"]:
            risk += r["far_event"]
            flags.append("Događaj je daleko – kapital je dugo zarobljen, veći rizik otkazivanja ili pada potražnje.")
        if best_platform is not None and best_platform.pays_after_event:
            risk += r["payout_after_event"]
            flags.append(f"{best_platform.name}: isplata tek nakon događaja.")
        if phase == "ODGOĐENO":
            risk += r["postponed"]
            flags.append("Događaj je odgođen – neizvjestan novi datum i potražnja.")
        risk += r["low_demand"] * (1 - demand.score)
        return clamp(risk), flags

    def _verdict(self, event, phase, face_ref, legal_result, roi, demand, risk) -> tuple[str, str]:
        v = self.cfg.section("verdict")
        if phase == "OTKAZANO":
            return "OTKAZANO", "Događaj je otkazan."
        if face_ref is None:
            return "NEMA CIJENE", "Izvor ne daje nominalnu cijenu – unesi je ručno (CSV) za izračun zarade."
        if legal_result.profit_prohibited:
            return "ZAKONSKI OGRANIČENO", f"{legal_result.country_name}: {legal.RULE_LABELS.get(legal_result.rule, legal_result.rule)} – preprodaja radi zarade nije dopuštena."
        if phase == "RASPRODANO":
            return "RASPRODANO", "Primarna prodaja je rasprodana – po nominalnoj cijeni se više ne može kupiti. Ako već imaš ulaznice, slijedi plan prodaje."
        if roi is None:
            return "PRESKOČI", "Nema dostupne platforme za izračun."
        if roi >= v["buy_roi"] and demand >= v["buy_min_demand"] and risk <= v["buy_max_risk"]:
            return "KUPI", "Visok očekivani povrat uz jaku potražnju i prihvatljiv rizik."
        if roi >= v["consider_roi"]:
            why = []
            if roi < v["buy_roi"]:
                why.append("umjeren povrat")
            if demand < v["buy_min_demand"]:
                why.append("potražnja nije dovoljno jaka")
            if risk > v["buy_max_risk"]:
                why.append("povišen rizik")
            return "RAZMOTRI", "Pozitivan očekivani povrat, ali: " + ", ".join(why) + "."
        return "PRESKOČI", "Očekivani povrat nakon naknada i rizika je prenizak."

    def _quantity(self, verdict: str, event: Event, buy_cost: float | None, demand: float) -> int:
        if not buy_cost or verdict not in ("KUPI", "RAZMOTRI"):
            return 0
        s = self.cfg.section("sizing")
        budget_cap = math.floor(self.budget * s["max_budget_share"] / buy_cost)
        limit = event.ticket_limit or s["max_qty"]
        if verdict == "KUPI":
            wanted = s["max_qty"] if demand >= 0.75 else s["default_qty"]
        else:
            wanted = s["default_qty"]
        qty = max(0, min(wanted, limit, s["max_qty"], budget_cap))
        if qty >= 2 and qty % 2 == 1:
            qty -= 1
        return qty


def sort_key(op: Opportunity):
    return (VERDICT_ORDER.get(op.verdict, 9), -op.total_expected_value, -(op.roi or -9), op.event.date)
