"""Nazivi država (engleski, kako ih pišu Wikipedia, Google Events i PredictHQ) → ISO 3166-1 alpha-2."""

from __future__ import annotations

from karte.util import normalize

_NAMES = {
    "AD": ["Andorra"],
    "AE": ["United Arab Emirates", "UAE"],
    "AL": ["Albania"],
    "AR": ["Argentina"],
    "AT": ["Austria", "Österreich", "Osterreich"],
    "AU": ["Australia"],
    "BA": ["Bosnia and Herzegovina", "Bosnia & Herzegovina", "Bosnia", "BiH"],
    "BE": ["Belgium", "België", "Belgique"],
    "BG": ["Bulgaria"],
    "BH": ["Bahrain"],
    "BR": ["Brazil", "Brasil"],
    "BY": ["Belarus"],
    "CA": ["Canada"],
    "CH": ["Switzerland", "Schweiz", "Suisse"],
    "CL": ["Chile"],
    "CN": ["China", "People's Republic of China"],
    "CO": ["Colombia"],
    "CR": ["Costa Rica"],
    "CY": ["Cyprus"],
    "CZ": ["Czech Republic", "Czechia", "Česko"],
    "DE": ["Germany", "Deutschland"],
    "DK": ["Denmark", "Danmark"],
    "DO": ["Dominican Republic"],
    "EC": ["Ecuador"],
    "EE": ["Estonia"],
    "EG": ["Egypt"],
    "ES": ["Spain", "España"],
    "FI": ["Finland", "Suomi"],
    "FR": ["France"],
    "GB": ["United Kingdom", "UK", "Great Britain", "England", "Scotland", "Wales", "Northern Ireland"],
    "GE": ["Georgia (country)"],
    "GR": ["Greece"],
    "GT": ["Guatemala"],
    "HK": ["Hong Kong"],
    "HR": ["Croatia", "Hrvatska"],
    "HU": ["Hungary", "Magyarország"],
    "ID": ["Indonesia"],
    "IE": ["Ireland", "Republic of Ireland"],
    "IL": ["Israel"],
    "IN": ["India"],
    "IS": ["Iceland"],
    "IT": ["Italy", "Italia"],
    "JP": ["Japan"],
    "KR": ["South Korea", "Korea, South", "Republic of Korea", "Korea"],
    "KW": ["Kuwait"],
    "LT": ["Lithuania"],
    "LU": ["Luxembourg"],
    "LV": ["Latvia"],
    "MA": ["Morocco"],
    "MC": ["Monaco"],
    "ME": ["Montenegro", "Crna Gora"],
    "MK": ["North Macedonia", "Macedonia"],
    "MT": ["Malta"],
    "MX": ["Mexico", "México"],
    "MY": ["Malaysia"],
    "NL": ["Netherlands", "The Netherlands", "Nederland", "Holland"],
    "NO": ["Norway", "Norge"],
    "NZ": ["New Zealand"],
    "PA": ["Panama"],
    "PE": ["Peru"],
    "PH": ["Philippines"],
    "PL": ["Poland", "Polska"],
    "PR": ["Puerto Rico"],
    "PT": ["Portugal"],
    "PY": ["Paraguay"],
    "QA": ["Qatar"],
    "RO": ["Romania"],
    "RS": ["Serbia", "Srbija"],
    "SA": ["Saudi Arabia"],
    "SE": ["Sweden", "Sverige"],
    "SG": ["Singapore"],
    "SI": ["Slovenia", "Slovenija"],
    "SK": ["Slovakia", "Slovensko"],
    "TH": ["Thailand"],
    "TR": ["Turkey", "Türkiye", "Turkiye"],
    "TW": ["Taiwan"],
    "UA": ["Ukraine"],
    "US": ["United States", "United States of America", "USA", "U.S.", "US"],
    "UY": ["Uruguay"],
    "VN": ["Vietnam"],
    "ZA": ["South Africa"],
}

COUNTRY_CODES: dict[str, str] = {}
for _code, _names in _NAMES.items():
    for _name in _names:
        COUNTRY_CODES[normalize(_name)] = _code
    COUNTRY_CODES.setdefault(_code.lower(), _code)

# Savezne države SAD-a i kanadske pokrajine (Google Events piše "Austin, TX")
US_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY", "DC",
}
CA_PROVINCES = {"AB", "BC", "MB", "NB", "NL", "NS", "NT", "NU", "ON", "PE", "QC", "SK", "YT"}


def country_code(name: str | None) -> str | None:
    """'Czech Republic' → 'CZ', 'England' → 'GB'; vraća None ako naziv nije poznat."""
    if not name:
        return None
    key = normalize(name)
    if key in COUNTRY_CODES:
        return COUNTRY_CODES[key]
    if key.startswith("the ") and key[4:] in COUNTRY_CODES:
        return COUNTRY_CODES[key[4:]]
    return None
