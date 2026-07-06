"""Symbol registry for the market data collector."""

from dataclasses import dataclass
from typing import Optional

from services.data_collector.config import get_collector_config

DEFAULT_SYMBOL_METADATA: dict[str, dict[str, str]] = {
    "EURUSD": {"name": "Euro / US Dollar", "category": "major", "base": "EUR", "quote": "USD"},
    "GBPUSD": {"name": "British Pound / US Dollar", "category": "major", "base": "GBP", "quote": "USD"},
    "USDJPY": {"name": "US Dollar / Japanese Yen", "category": "major", "base": "USD", "quote": "JPY"},
    "AUDUSD": {"name": "Australian Dollar / US Dollar", "category": "major", "base": "AUD", "quote": "USD"},
    "NZDUSD": {"name": "New Zealand Dollar / US Dollar", "category": "major", "base": "NZD", "quote": "USD"},
    "USDCAD": {"name": "US Dollar / Canadian Dollar", "category": "major", "base": "USD", "quote": "CAD"},
    "USDCHF": {"name": "US Dollar / Swiss Franc", "category": "major", "base": "USD", "quote": "CHF"},
    "XAUUSD": {"name": "Gold / US Dollar", "category": "metal", "base": "XAU", "quote": "USD"},
    "XAGUSD": {"name": "Silver / US Dollar", "category": "metal", "base": "XAG", "quote": "USD"},
    "BTCUSD": {"name": "Bitcoin / US Dollar", "category": "crypto", "base": "BTC", "quote": "USD"},
    "ETHUSD": {"name": "Ethereum / US Dollar", "category": "crypto", "base": "ETH", "quote": "USD"},
    "NAS100": {"name": "NASDAQ 100", "category": "index", "base": "NAS", "quote": "USD"},
    "US30": {"name": "Dow Jones 30", "category": "index", "base": "US30", "quote": "USD"},
    "SPX500": {"name": "S&P 500", "category": "index", "base": "SPX", "quote": "USD"},
    "GER40": {"name": "DAX 40", "category": "index", "base": "GER", "quote": "EUR"},
}


@dataclass(frozen=True)
class SymbolInfo:
    symbol: str
    name: str
    category: str
    base_currency: str
    quote_currency: str
    is_active: bool = True


class SymbolRegistry:
    """Configurable symbol registry backed by config/data_collector.yaml."""

    def __init__(self, symbols: Optional[tuple[str, ...]] = None):
        cfg = get_collector_config()
        self._symbols = symbols or cfg.symbols

    @property
    def symbols(self) -> tuple[str, ...]:
        return self._symbols

    def get(self, symbol: str) -> Optional[SymbolInfo]:
        sym = symbol.upper().replace("/", "")
        meta = DEFAULT_SYMBOL_METADATA.get(sym)
        if not meta:
            if sym not in self._symbols:
                return None
            return SymbolInfo(
                symbol=sym,
                name=sym,
                category="exotic",
                base_currency=sym[:3],
                quote_currency=sym[3:],
            )
        return SymbolInfo(
            symbol=sym,
            name=meta["name"],
            category=meta["category"],
            base_currency=meta["base"],
            quote_currency=meta["quote"],
        )

    def all(self) -> list[SymbolInfo]:
        return [info for s in self._symbols if (info := self.get(s)) is not None]

    def is_registered(self, symbol: str) -> bool:
        return symbol.upper().replace("/", "") in self._symbols

    def normalize(self, symbol: str) -> str:
        return symbol.upper().replace("/", "")
