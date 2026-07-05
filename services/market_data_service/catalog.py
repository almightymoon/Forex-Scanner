"""Searchable symbol catalog — forex, metals, exotics, and more."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Category = Literal["major", "minor", "exotic", "metal", "energy", "crypto"]

CURRENCY_NAMES: dict[str, str] = {
    "EUR": "Euro",
    "USD": "US Dollar",
    "GBP": "British Pound",
    "JPY": "Japanese Yen",
    "CHF": "Swiss Franc",
    "AUD": "Australian Dollar",
    "CAD": "Canadian Dollar",
    "NZD": "New Zealand Dollar",
    "SEK": "Swedish Krona",
    "NOK": "Norwegian Krone",
    "DKK": "Danish Krone",
    "PLN": "Polish Zloty",
    "HUF": "Hungarian Forint",
    "CZK": "Czech Koruna",
    "TRY": "Turkish Lira",
    "ZAR": "South African Rand",
    "MXN": "Mexican Peso",
    "BRL": "Brazilian Real",
    "CNH": "Chinese Yuan Offshore",
    "CNY": "Chinese Yuan",
    "HKD": "Hong Kong Dollar",
    "SGD": "Singapore Dollar",
    "THB": "Thai Baht",
    "INR": "Indian Rupee",
    "KRW": "South Korean Won",
    "ILS": "Israeli Shekel",
    "RON": "Romanian Leu",
    "XAU": "Gold",
    "XAG": "Silver",
    "XPT": "Platinum",
    "XPD": "Palladium",
    "WTI": "Crude Oil WTI",
    "BRENT": "Brent Crude",
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
}

SEARCH_ALIASES: dict[str, str] = {
    "gold": "XAUUSD",
    "auxusd": "XAUUSD",
    "aux": "XAUUSD",
    "silver": "XAGUSD",
    "xag": "XAGUSD",
    "platinum": "XPTUSD",
    "palladium": "XPDUSD",
    "oil": "USOIL",
    "wti": "USOIL",
    "crude": "USOIL",
    "brent": "UKOIL",
    "bitcoin": "BTCUSD",
    "btc": "BTCUSD",
    "ethereum": "ETHUSD",
    "eth": "ETHUSD",
    "euro": "EURUSD",
    "cable": "GBPUSD",
    "pound": "GBPUSD",
    "sterling": "GBPUSD",
    "yen": "USDJPY",
    "franc": "USDCHF",
    "aussie": "AUDUSD",
    "kiwi": "NZDUSD",
    "loonie": "USDCAD",
    "turkish": "USDTRY",
    "lira": "USDTRY",
    "rand": "USDZAR",
    "peso": "USDMXN",
}

# Pairs beyond the default scan list — searchable and addable
EXTRA_PAIRS: list[tuple[str, Category]] = [
    # Exotics vs USD
    ("USDTRY", "exotic"), ("EURTRY", "exotic"), ("USDZAR", "exotic"),
    ("USDMXN", "exotic"), ("USDBRL", "exotic"), ("USDCNH", "exotic"),
    ("USDHKD", "exotic"), ("USDSGD", "exotic"), ("USDSEK", "exotic"),
    ("USDNOK", "exotic"), ("USDDKK", "exotic"), ("USDPLN", "exotic"),
    ("USDHUF", "exotic"), ("USDCZK", "exotic"), ("USDTHB", "exotic"),
    ("USDINR", "exotic"), ("USDILS", "exotic"), ("USDKRW", "exotic"),
    # Crosses
    ("EURSEK", "exotic"), ("EURNOK", "exotic"), ("EURPLN", "exotic"),
    ("EURHUF", "exotic"), ("EURCZK", "exotic"), ("GBPSEK", "exotic"),
    ("GBPNOK", "exotic"), ("GBPPLN", "exotic"), ("CHFSEK", "exotic"),
    ("CADCHF", "minor"), ("CADNZD", "minor"), ("NZDCHF", "minor"),
    # More metals
    ("XPTUSD", "metal"), ("XPDUSD", "metal"),
    # Energy & crypto (simulated pricing)
    ("USOIL", "energy"), ("UKOIL", "energy"),
    ("BTCUSD", "crypto"), ("ETHUSD", "crypto"),
]


@dataclass(frozen=True)
class CatalogEntry:
    symbol: str
    name: str
    short: str
    category: Category
    base: str
    quote: str


SPECIAL_PAIRS: dict[str, tuple[str, str]] = {
    "USOIL": ("WTI", "USD"),
    "UKOIL": ("BRENT", "USD"),
}


def normalize_symbol(raw: str) -> str | None:
    """Convert user input like 'eur/usd' or 'EUR-USD' to 'EURUSD'."""
    if not raw or not raw.strip():
        return None
    cleaned = re.sub(r"[^A-Za-z]", "", raw.strip().upper())
    if cleaned in SPECIAL_PAIRS:
        return cleaned
    if len(cleaned) < 6 or len(cleaned) > 7:
        return None
    return cleaned


def parse_pair_currencies(symbol: str) -> tuple[str, str]:
    if symbol in SPECIAL_PAIRS:
        return SPECIAL_PAIRS[symbol]
    if len(symbol) >= 6:
        return symbol[:3], symbol[3:6]
    return symbol[:3], symbol[3:] if len(symbol) > 3 else "USD"


def short_pair(symbol: str) -> str:
    if symbol in SPECIAL_PAIRS:
        base, quote = SPECIAL_PAIRS[symbol]
        return f"{base}/{quote}"
    if len(symbol) >= 6:
        return f"{symbol[:3]}/{symbol[3:]}"
    return symbol


def pair_name(symbol: str, base: str | None = None, quote: str | None = None) -> str:
    if base is None or quote is None:
        base, quote = parse_pair_currencies(symbol)
    base_name = CURRENCY_NAMES.get(base, base)
    quote_name = CURRENCY_NAMES.get(quote, quote)
    return f"{base_name} / {quote_name}"


def category_for(symbol: str, override: Category | None = None) -> Category:
    if override:
        return override
    if symbol.startswith(("XAU", "XAG", "XPT", "XPD")):
        return "metal"
    if symbol in ("USOIL", "UKOIL"):
        return "energy"
    if symbol in ("BTCUSD", "ETHUSD"):
        return "crypto"
    majors = {"EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"}
    if symbol in majors:
        return "major"
    if symbol.startswith("USD") or symbol.endswith("USD"):
        return "exotic" if symbol not in majors else "major"
    return "minor"


def build_entry(symbol: str, category: Category | None = None) -> CatalogEntry:
    base, quote = parse_pair_currencies(symbol)
    cat = category_for(symbol, category)
    return CatalogEntry(
        symbol=symbol,
        name=pair_name(symbol, base, quote),
        short=short_pair(symbol),
        category=cat,
        base=base,
        quote=quote,
    )


def _build_catalog() -> dict[str, CatalogEntry]:
    from .provider import FOREX_PAIRS, METAL_PAIRS, SYMBOL_CATEGORIES

    catalog: dict[str, CatalogEntry] = {}
    for sym in FOREX_PAIRS:
        cat: Category = SYMBOL_CATEGORIES.get(sym, "minor")  # type: ignore[assignment]
        if sym in METAL_PAIRS:
            cat = "metal"
        catalog[sym] = build_entry(sym, cat)

    for sym, cat in EXTRA_PAIRS:
        if sym not in catalog:
            catalog[sym] = build_entry(sym, cat)

    return catalog


CATALOG: dict[str, CatalogEntry] = _build_catalog()


def get_catalog_entry(symbol: str) -> CatalogEntry | None:
    return CATALOG.get(symbol.upper())


def entry_to_dict(entry: CatalogEntry, *, in_default: bool = False, price: float = 0, live: bool = False) -> dict:
    return {
        "symbol": entry.symbol,
        "name": entry.name,
        "short": entry.short,
        "category": entry.category,
        "base": entry.base,
        "quote": entry.quote,
        "in_default": in_default,
        "price": price,
        "live": live,
    }


def search_symbols(query: str, limit: int = 20) -> list[dict]:
    """Search catalog by symbol, pair code, name, currency, or alias."""
    from .provider import FOREX_PAIRS

    q = query.strip().lower()
    if not q:
        return [
            entry_to_dict(e, in_default=e.symbol in FOREX_PAIRS)
            for e in list(CATALOG.values())[:limit]
        ]

    # Direct alias match (e.g. "gold" -> XAUUSD)
    if q in SEARCH_ALIASES:
        sym = SEARCH_ALIASES[q]
        entry = CATALOG.get(sym)
        if entry:
            return [entry_to_dict(entry, in_default=sym in FOREX_PAIRS)]

    # Normalize typed pair (eurusd, eur/usd)
    normalized = normalize_symbol(query)
    if normalized and normalized in CATALOG:
        entry = CATALOG[normalized]
        return [entry_to_dict(entry, in_default=normalized in FOREX_PAIRS)]

    results: list[tuple[int, CatalogEntry]] = []
    for entry in CATALOG.values():
        score = _match_score(q, entry)
        if score > 0:
            results.append((score, entry))

    results.sort(key=lambda x: (-x[0], x[1].symbol))
    if results:
        return [
            entry_to_dict(e, in_default=e.symbol in FOREX_PAIRS)
            for _, e in results[:limit]
        ]

    # Fuzzy match for typos like AUXUSD -> XAUUSD
    fuzzy = _fuzzy_symbol(q.upper().replace("/", ""))
    if fuzzy and fuzzy in CATALOG:
        entry = CATALOG[fuzzy]
        return [entry_to_dict(entry, in_default=fuzzy in FOREX_PAIRS)]

    return []


def _match_score(q: str, entry: CatalogEntry) -> int:
    sym = entry.symbol.lower()
    short = entry.short.lower().replace("/", "")
    name = entry.name.lower()
    base_name = CURRENCY_NAMES.get(entry.base, "").lower()
    quote_name = CURRENCY_NAMES.get(entry.quote, "").lower()

    if sym == q or short == q.replace("/", ""):
        return 100
    if sym.startswith(q) or short.startswith(q.replace("/", "")):
        return 80
    if q in sym or q in short.replace("/", ""):
        return 60
    if q in name:
        return 50
    if q in base_name or q in quote_name:
        return 40
    # Word-start match
    for part in name.split():
        if part.startswith(q):
            return 30
    return 0


def _fuzzy_symbol(q: str) -> str | None:
    if len(q) < 5:
        return None
    best: str | None = None
    best_dist = 3
    for sym in CATALOG:
        if abs(len(sym) - len(q)) > 1:
            continue
        dist = _levenshtein(q, sym)
        if 0 < dist < best_dist:
            best_dist = dist
            best = sym
    return best


def _levenshtein(a: str, b: str) -> int:
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, n + 1):
            temp = dp[j]
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = temp
    return dp[n]


def merge_scan_symbols(default: list[str], extra: list[str] | None) -> list[str]:
    """Default pairs + user additions, deduped, order preserved."""
    seen: set[str] = set()
    merged: list[str] = []
    for sym in default + (extra or []):
        key = sym.upper()
        if key not in seen and key in CATALOG:
            seen.add(key)
            merged.append(key)
    return merged
