export interface SymbolInfo {
  symbol: string;
  name: string;
  short: string;
  category: "major" | "minor" | "exotic" | "metal" | "energy" | "crypto";
}

export const SYMBOLS: Record<string, SymbolInfo> = {
  EURUSD: { symbol: "EURUSD", name: "Euro / US Dollar", short: "EUR/USD", category: "major" },
  GBPUSD: { symbol: "GBPUSD", name: "British Pound / US Dollar", short: "GBP/USD", category: "major" },
  USDJPY: { symbol: "USDJPY", name: "US Dollar / Japanese Yen", short: "USD/JPY", category: "major" },
  USDCHF: { symbol: "USDCHF", name: "US Dollar / Swiss Franc", short: "USD/CHF", category: "major" },
  AUDUSD: { symbol: "AUDUSD", name: "Australian Dollar / US Dollar", short: "AUD/USD", category: "major" },
  USDCAD: { symbol: "USDCAD", name: "US Dollar / Canadian Dollar", short: "USD/CAD", category: "major" },
  NZDUSD: { symbol: "NZDUSD", name: "New Zealand Dollar / US Dollar", short: "NZD/USD", category: "major" },
  EURGBP: { symbol: "EURGBP", name: "Euro / British Pound", short: "EUR/GBP", category: "minor" },
  EURJPY: { symbol: "EURJPY", name: "Euro / Japanese Yen", short: "EUR/JPY", category: "minor" },
  GBPJPY: { symbol: "GBPJPY", name: "British Pound / Japanese Yen", short: "GBP/JPY", category: "minor" },
  EURCHF: { symbol: "EURCHF", name: "Euro / Swiss Franc", short: "EUR/CHF", category: "minor" },
  EURAUD: { symbol: "EURAUD", name: "Euro / Australian Dollar", short: "EUR/AUD", category: "minor" },
  EURCAD: { symbol: "EURCAD", name: "Euro / Canadian Dollar", short: "EUR/CAD", category: "minor" },
  EURNZD: { symbol: "EURNZD", name: "Euro / New Zealand Dollar", short: "EUR/NZD", category: "minor" },
  GBPCHF: { symbol: "GBPCHF", name: "British Pound / Swiss Franc", short: "GBP/CHF", category: "minor" },
  GBPAUD: { symbol: "GBPAUD", name: "British Pound / Australian Dollar", short: "GBP/AUD", category: "minor" },
  GBPCAD: { symbol: "GBPCAD", name: "British Pound / Canadian Dollar", short: "GBP/CAD", category: "minor" },
  GBPNZD: { symbol: "GBPNZD", name: "British Pound / New Zealand Dollar", short: "GBP/NZD", category: "minor" },
  AUDJPY: { symbol: "AUDJPY", name: "Australian Dollar / Japanese Yen", short: "AUD/JPY", category: "minor" },
  AUDCHF: { symbol: "AUDCHF", name: "Australian Dollar / Swiss Franc", short: "AUD/CHF", category: "minor" },
  AUDCAD: { symbol: "AUDCAD", name: "Australian Dollar / Canadian Dollar", short: "AUD/CAD", category: "minor" },
  AUDNZD: { symbol: "AUDNZD", name: "Australian Dollar / New Zealand Dollar", short: "AUD/NZD", category: "minor" },
  CADJPY: { symbol: "CADJPY", name: "Canadian Dollar / Japanese Yen", short: "CAD/JPY", category: "minor" },
  CHFJPY: { symbol: "CHFJPY", name: "Swiss Franc / Japanese Yen", short: "CHF/JPY", category: "minor" },
  NZDJPY: { symbol: "NZDJPY", name: "New Zealand Dollar / Japanese Yen", short: "NZD/JPY", category: "minor" },
  NZDCAD: { symbol: "NZDCAD", name: "New Zealand Dollar / Canadian Dollar", short: "NZD/CAD", category: "minor" },
  XAUUSD: { symbol: "XAUUSD", name: "Gold / US Dollar", short: "XAU/USD", category: "metal" },
  XAGUSD: { symbol: "XAGUSD", name: "Silver / US Dollar", short: "XAG/USD", category: "metal" },
};

export function getCategoryLabel(category: SymbolInfo["category"]): string {
  const labels: Record<SymbolInfo["category"], string> = {
    major: "Major",
    minor: "Minor",
    metal: "Metal",
    exotic: "Exotic",
    energy: "Energy",
    crypto: "Crypto",
  };
  return labels[category] ?? category;
}

const runtimeSymbols: Record<string, SymbolInfo> = {};

export function registerSymbol(info: {
  symbol: string;
  name: string;
  short: string;
  category: string;
}): void {
  const key = info.symbol.toUpperCase();
  const cat = (["major", "minor", "exotic", "metal", "energy", "crypto"].includes(info.category)
    ? info.category
    : "minor") as SymbolInfo["category"];
  runtimeSymbols[key] = { symbol: key, name: info.name, short: info.short, category: cat };
}

export function getSymbol(symbol: string): SymbolInfo {
  const key = symbol.toUpperCase();
  if (runtimeSymbols[key]) return runtimeSymbols[key];
  return SYMBOLS[key] ?? {
    symbol: key,
    name: formatPairName(key),
    short: formatPairShort(key),
    category: "minor",
  };
}

export function getSymbolName(symbol: string): string {
  return getSymbol(symbol).name;
}

export function getSymbolShort(symbol: string): string {
  return getSymbol(symbol).short;
}

function formatPairName(symbol: string): string {
  if (symbol.length >= 6) {
    return `${symbol.slice(0, 3)} / ${symbol.slice(3)}`;
  }
  return symbol;
}

function formatPairShort(symbol: string): string {
  if (symbol.length >= 6) {
    return `${symbol.slice(0, 3)}/${symbol.slice(3)}`;
  }
  return symbol;
}
