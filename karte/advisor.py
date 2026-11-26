"""Generiranje konkretnih savjeta: kako kupiti, gdje i kada prodati, po kojoj cijeni."""

from __future__ import annotations

from karte import knowledge
from karte.knowledge import ModelConfig
from karte.links import price_links
from karte.models import Opportunity
from karte.util import add_days, fmt_date, fmt_datetime, fmt_eur, fmt_pct

NO_BOTS = (
    "Kupuj ručno, jedan uređaj po računu i unutar limita po kupcu. Botovi i zaobilaženje limita "
    "(više lažnih računa) krše uvjete prodaje, a u EU je preprodaja tako kupljenih ulaznica zabranjena "
    "(Omnibus direktiva; u HR Zakon o zaštiti potrošača)."
)


def _ladder(op: Opportunity, cfg: ModelConfig) -> list[dict]:
    best = op.best
    if best is None or op.buy_cost is None:
        return []
    start = best.list_price
    floor = best.break_even_price
    caps = [c for c in (op.legal.cap_price,) if c is not None]
    if best.capped:
        caps.append(best.list_price)
    cap = min(caps) if caps else None
    d = op.demand.score
    salvage = cfg.get("sell", "salvage_ratio", 0.5) * (op.face_ref or 0)

    if d >= 0.7:
        steps = [
            (None, start * 1.10, "Odmah (po rasprodaji primarne prodaje / kupnji)"),
            (30, start, "T-30 dana"),
            (14, max(floor, start * 0.92), "T-14 dana"),
            (7, max(floor, start * 0.85), "T-7 dana"),
            (2, floor, "T-2 dana – zadnja prilika (break-even)"),
        ]
    elif d >= 0.45:
        steps = [
            (None, start, "Odmah po kupnji"),
            (30, max(floor, start * 0.95), "T-30 dana"),
            (14, max(floor, start * 0.88), "T-14 dana"),
            (5, floor, "T-5 dana – break-even"),
            (1, max(salvage, floor * 0.8), "T-1 dan – smanji gubitak"),
        ]
    else:
        steps = [
            (None, max(floor, start), "Odmah"),
            (7, floor, "T-7 dana – break-even"),
            (1, salvage, "T-1 dan – prodaj u bescjenje"),
        ]

    rows = []
    for days_before, price, label in steps:
        if days_before is not None and days_before >= op.days_to_event:
            continue
        if cap is not None:
            price = min(price, cap)
        date = add_days(op.event.date, -days_before) if days_before is not None else None
        rows.append({
            "label": label,
            "date": fmt_date(date) if date else "odmah",
            "iso": date.date().isoformat() if date else None,
            "price": round(price, 2),
        })
    return rows


def safety_checks(op: Opportunity) -> list[dict]:
    """Sigurnosna provjera prije kupnje/prodaje: ok | warn | bad (vidi karte/data/guides/5_sigurnost.md)."""
    e = op.event
    out: list[dict] = []

    def add(level: str, text: str):
        out.append({"level": level, "text": text})

    if op.legal.sport_rule == "criminal":
        add("bad", "Neovlaštena preprodaja ulaznica za ovu utakmicu je kazneno djelo – bez obzira na cijenu.")
    elif op.legal.contract_prohibited:
        add("bad", "Uvjeti kluba/organizatora zabranjuju preprodaju: ulaznice se poništavaju, članstva trajno blokiraju "
                   "(npr. Liverpool 432 doživotne zabrane, Arsenal 17.500 članstava u sezoni).")
    elif op.legal.sport_rule == "official_marketplace":
        add("warn", f"Preprodaja samo na službenom tržištu ({op.legal.official_channel}) uz naknade; ulaznice s drugih stranica mogu biti poništene.")
    if e.segment == "sport":
        add("warn", "Kupuj samo na svoje ime i svoj račun/članstvo – tuđa ili lažna članstva klubovi otkrivaju i gase.")

    if op.legal.profit_prohibited:
        add("bad", f"Zakon ({op.legal.country_name}) ne dopušta preprodaju radi zarade – ne kupuj radi preprodaje.")
    elif op.legal.cap_price is not None:
        add("warn", f"Zakonski limit cijene: najviše ~{fmt_eur(op.legal.cap_price)} po ulaznici – ne oglašavaj iznad toga.")
    elif op.legal.planned_rule:
        add("warn", "Najavljeno je zakonsko ograničenje cijene – provjeri vrijedi li već na datum koncerta.")
    else:
        add("ok", "Zakon države ne ograničava cijenu preprodaje (vrijedi zabrana botova i zaobilaženja limita).")

    vendor = knowledge.vendor_info(e.primary_vendor)
    if vendor and vendor.get("transferable") is False:
        add("bad", f"{vendor.get('name')}: {vendor.get('resale', 'ulaznice se ne mogu preprodati.')}")
    if e.personalized is True:
        add("bad", "Ulaznice su personalizirane – kupac možda neće ući; prodaj samo ako organizator dopušta službenu promjenu imena.")
    elif e.personalized is None:
        add("warn", "Provjeri u uvjetima jesu li ulaznice na ime i može li se prenijeti/promijeniti ime – prije kupnje.")
    else:
        add("ok", "Ulaznice nisu personalizirane.")

    limit = e.ticket_limit
    add("ok" if limit else "warn",
        f"Kupuj s jednog računa i najviše {limit} kom (limit po kupcu). Narudžbe preko limita se poništavaju." if limit
        else "Limit po kupcu nije poznat – provjeri ga i kupuj s jednog računa (više računa = poništene narudžbe).")

    if op.phase == "NAJAVA":
        add("warn", "Ne oglašavaj prije nego ulaznice budu u tvom računu – spekulativni oglasi nose kazne.")
    if (e.primary_vendor or "") in ("ticketmaster", "eventim"):
        add("warn", "Mobilne ulaznice se često mogu prenijeti tek par dana prije koncerta – postavi takav rok isporuke u oglasu.")
    if op.best and "nakon" in op.best.payout.lower() and "događaj" in op.best.payout.lower():
        add("warn", f"{op.best.name}: novac stiže tek nakon koncerta – ne računaj na njega prije {fmt_date(e.date)}.")
    add("ok", "Kad se proda: odmah povuci oglase s ostalih platformi, prenesi službenim prijenosom i spremi screenshot potvrde.")
    if op.best and op.best.trust_risk >= 0.5:
        add("warn", "Privatna prodaja: novac na račun prije prijenosa ili osobna primopredaja; bez PayPal F&F i „potvrda uplate”.")
    if op.demand.confidence < 0.5:
        add("warn", "Malo podataka – prije kupnje ručno provjeri cijene i broj oglasa na viagogu.")
    return out


def build_advice(op: Opportunity, cfg: ModelConfig) -> dict:
    e = op.event
    best = op.best
    d = op.demand.score
    buy: list[str] = []
    sell: list[str] = []

    # ------------------------------------------------------------ sažetak
    risky = op.verdict == "RIZIČNO"
    if op.verdict in ("KUPI", "RAZMOTRI", "RIZIČNO") and best:
        summary = (
            f"{op.verdict}: očekivana neto dobit ~{fmt_eur(op.profit)} po ulaznici ako se proda "
            f"(očekivana vrijednost uz rizik {fmt_eur(op.expected_value)}, ROI {fmt_pct(op.roi)}), "
            f"potražnja {d * 100:.0f}/100. Preporuka: {op.suggested_qty} kom, prodaja preko: {best.name}."
        )
    else:
        summary = f"{op.verdict}: {op.verdict_reason}"

    # ------------------------------------------------------------ kupnja
    for note in op.legal.sport_notes:
        buy.append(f"[Prodaja] {note}")
    if op.phase == "NAJAVA":
        for p in sorted(e.presales, key=lambda x: x.start or e.date):
            if p.start:
                end = f" (do {fmt_datetime(p.end)})" if p.end else ""
                buy.append(f"Presale „{p.name}”: {fmt_datetime(p.start)}{end}.")
        if e.public_onsale:
            buy.append(f"Javna prodaja: {fmt_datetime(e.public_onsale)}.")
        buy.append(
            "Prijavi se unaprijed za presale: newsletter/fan klub izvođača, račun kod prodavača "
            f"({e.primary_vendor or 'službeni prodavač'}) s pohranjenom karticom, partnerski presaleovi (banke, telekomi)."
        )
        buy.append("U virtualni red uđi 10–15 min prije početka; ne osvježavaj stranicu u redu.")
    elif op.phase == "U PRODAJI":
        buy.append("Ulaznice su još u primarnoj prodaji – ako je preporuka KUPI, kupi što prije, prije nego jeftinije kategorije nestanu.")
    elif op.phase == "RASPRODANO":
        buy.append("Primarna prodaja rasprodana – kupnja na sekundarnom tržištu radi preprodaje rijetko je isplativa (dvostruke naknade).")
        buy.append("Prati službene kanale: često se puštaju dodatne ulaznice (production holds) 1–7 dana prije događaja.")
    elif op.phase == "NIJE U PRODAJI":
        buy.append("Ulaznice trenutno nisu u prodaji kod izvora (rasprodano ili prodaja zatvorena) – provjeri službenu stranicu.")

    if risky:
        buy.insert(0, "VISOK RIZIK: preprodaju zabranjuju uvjeti kluba/organizatora. Ulaznica može biti poništena, kupac odbijen na ulazu, "
                      "a tvoj račun ili članstvo blokirani – uloži samo novac koji možeš izgubiti.")
    if op.verdict in ("KUPI", "RAZMOTRI", "RIZIČNO"):
        if d >= 0.7:
            buy.append(
                "Ciljaj najjeftinije kategorije s dobrim pogledom i parter/stajanje – najveći postotni skok cijene i najbrža prodaja. "
                "Premium/VIP paketi samo uz vrlo jaku potražnju (veći kapital, manji postotak)."
            )
        else:
            buy.append("Ciljaj srednje kategorije s dobrim pogledom; izbjegavaj zaklonjene sjedalice i najskuplje pakete.")
        limit = f", limit po kupcu: {e.ticket_limit}" if e.ticket_limit else ""
        if op.suggested_qty == 1:
            buy.append(f"Količina: 1 kom – budžet ne pokriva par (parovi se prodaju najbrže); razmisli o jeftinijoj kategoriji{limit}.")
        else:
            buy.append(f"Količina: {op.suggested_qty} kom (u parovima – parovi se najbrže prodaju){limit}.")
        if best and op.buy_cost:
            p = best.p_sell
            salvage = 0.0 if e.personalized else cfg.get("sell", "salvage_ratio", 0.5) * (op.face_ref or 0)
            buy_roi = cfg.get("verdict", "buy_roi", 0.3)
            max_cost = (p * best.net_payout + (1 - p) * salvage) / (1 + buy_roi)
            buy.append(
                f"Ne plaćaj više od ~{fmt_eur(max_cost)} po ulaznici s naknadama – iznad toga očekivani ROI pada ispod {buy_roi * 100:.0f} %."
            )
    vendor = knowledge.vendor_info(e.primary_vendor)
    if vendor:
        tip = f"Službena prodaja: {vendor.get('name')}"
        domain = knowledge.vendor_domain(e.primary_vendor, e.country)
        tip += f" ({domain})" if domain else ""
        buy.append(f"{tip} – {vendor.get('queue', '')}".rstrip(" –"))
        if vendor.get("transfer"):
            buy.append(f"Prijenos ulaznica: {vendor['transfer']}")
    else:
        names = [v.get("name", k) for k, v in knowledge.vendors_for_country(e.country)[:4]]
        if names:
            buy.append(
                f"Službeni prodavači u državi {op.legal.country_name}: {', '.join(names)} – na stranici izvođača ili dvorane provjeri "
                "tko prodaje baš ovaj koncert (poveznice „Provjeri cijene” ispod)."
            )
    if op.verdict == "PROVJERI CIJENU":
        target = cfg.get("verdict", "buy_roi", 0.3) * 100
        tips = []
        if op.max_buy:
            tips.append(
                f"Kupi samo ako je nominalna cijena (prije naknada) najviše ~{fmt_eur(op.max_buy)} po ulaznici – tada je očekivani ROI ≥ {target:.0f} %."
            )
        if op.breakeven_buy:
            low = f"Između {fmt_eur(op.max_buy)} i {fmt_eur(op.breakeven_buy)}" if op.max_buy else f"Do {fmt_eur(op.breakeven_buy)}"
            tips.append(f"{low} zarada je mala i rizična; iznad ~{fmt_eur(op.breakeven_buy)} očekuješ gubitak.")
        tips.append("Nominalnu cijenu pogledaj kod službenog prodavača (poveznica na događaj), pa je upiši u Kalkulator za puni plan prodaje.")
        buy[:0] = tips
        sec = e.secondary
        if sec and sec.lowest:
            seen = f", zabilježeno {sec.observed}" if sec.observed else ""
            sell.append(
                f"Referenca s preprodaje: najniža oglašena cijena {sec.lowest:g} {sec.currency} ({sec.source}{seen}). "
                f"Oglašene cijene uključuju kupčeve naknade – realna prodajna cijena za tebe je ~{fmt_eur(op.expected_resale)} prije naknade prodavatelja."
            )
        sell.append(
            "Prije kupnje provjeri aktualne oglase iste kategorije – agregatori često prikazuju zastarjelu ili najlošiju (najjeftiniju) ponudu."
        )
    elif op.verdict == "NEMA CIJENE":
        buy.append(
            "Nominalna cijena nije poznata: provjeri je kod službenog prodavača i najnižu cijenu iste kategorije na viagogu, "
            "pa oboje upiši u Kalkulator."
        )
    buy.append(
        "Prije kupnje provjeri uvjete: personalizacija/promjena imena, prijenos kroz aplikaciju, pravila organizatora o preprodaji."
    )
    buy.append(NO_BOTS)

    # ------------------------------------------------------------ prodaja
    if best:
        backups = [o for o in op.platforms[1:3]]
        sell.append(
            f"Glavni kanal: {best.name} – oglasi oko {fmt_eur(best.list_price)}, neto ~{fmt_eur(best.net_payout)} "
            f"po ulaznici (naknada prodavatelja ~{best.fee_pct * 100:.0f} %, break-even {fmt_eur(best.break_even_price)})."
        )
        if backups:
            sell.append(
                "Rezervni kanali: "
                + "; ".join(f"{o.name} (neto ~{fmt_eur(o.net_payout)})" for o in backups)
                + "."
            )
        if d >= 0.7:
            sell.append(
                "Oglasi odmah nakon rasprodaje primarne prodaje – prvih 24–72 h cijene su najviše. "
                "Drži cijenu do ~T-14 dana, zatim spuštaj postupno prema cjeniku."
            )
        elif d >= 0.45:
            sell.append(
                "Oglasi odmah po kupnji, malo ispod konkurencije. Kod srednje potražnje cijene uglavnom padaju prema datumu – "
                "ne čekaj zadnji tjedan."
            )
        else:
            sell.append("Potražnja je slaba – ne kupuj radi preprodaje. Ako već imaš ulaznice, prodaj što prije, makar po nominalnoj cijeni.")
        sell.append("Prati najniži oglas iste kategorije i budi 1–3 % ispod njega; ne spuštaj ispod break-evena prije T-7 dana.")
        if best.capped:
            sell.append(f"Cijena je ograničena (zakon ili pravila platforme) na ~{fmt_eur(best.list_price)}.")
        if "nakon" in best.payout.lower():
            sell.append(f"Napomena ({best.name}): {best.payout} Datum događaja: {fmt_date(e.date)}")
        sell.append("Ulaznice prenosi samo službenim prijenosom (aplikacija prodavača) – nikad screenshot/PDF više kupaca.")

    prohibited = op.legal.profit_prohibited or (op.legal.contract_prohibited and not risky)
    if risky:
        sell.insert(0, "Kupcu jasno napiši da ulaznica glasi na ime ako je tako – skrivanje toga vodi do odbijanja na ulazu i kazne platforme.")
        if op.legal.official_channel:
            sell.append(f"Siguran izlaz bez zarade: {op.legal.official_channel}.")
    if prohibited and e.segment == "sport":
        buy = [f"[Prodaja] {note}" for note in op.legal.sport_notes] + [
            "Kupuj samo ako sam ideš na utakmicu – na svoje ime, svojim računom/članstvom i unutar limita.",
            NO_BOTS,
        ]
        label = op.legal.official_channel or "službena razmjena kluba/organizatora"
        sell = [
            "Preprodaja radi zarade za ovu utakmicu nije dopuštena – ne kupuj radi preprodaje.",
            f"Ako ne možeš ići: {label} (u pravilu po nominalnoj cijeni) – tako vraćaš novac bez rizika.",
            "Ne oglašavaj na viagogu, Njuškalu ni Facebooku: kupcu može biti odbijen ulaz, a tebi poništene ulaznice, "
            "blokirano članstvo i kazna platforme.",
        ]

    if vendor and vendor.get("resale"):
        sell.append(f"Pravila službenog prodavača ({vendor.get('name')}): {vendor['resale']}")

    pravno = [op.legal.summary] if op.legal.summary else []
    if op.legal.cap_price is not None:
        pravno.append(f"Najviša dopuštena cijena po ulaznici (procjena): {fmt_eur(op.legal.cap_price)}.")

    return {
        "summary": summary,
        "buy": buy,
        "sell": sell,
        "ladder": [] if (prohibited and e.segment == "sport") else _ladder(op, cfg),
        "platforms": [
            {
                "name": o.name,
                "list_price": round(o.list_price, 2),
                "net": round(o.net_payout, 2),
                "p_sell": round(o.p_sell, 2),
                "ev": round(o.expected_value, 2),
                "capped": o.capped,
            }
            for o in op.platforms[:5]
        ],
        "risks": list(op.risk_flags) + list(op.demand.notes),
        "legal": pravno,
        "legal_sources": op.legal.sources,
        "safety": safety_checks(op),
        "links": price_links(e, allow_profit=not prohibited and not op.legal.profit_prohibited),
    }
