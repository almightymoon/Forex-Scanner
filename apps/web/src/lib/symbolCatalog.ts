import { SYMBOLS, type SymbolInfo } from "./symbols";

export interface CatalogEntry extends SymbolInfo {
  in_default: boolean;
}

const DEFAULT_SYMBOLS = new Set(Object.keys(SYMBOLS));

const EXTRA: Array<[string, SymbolInfo["category"], string, string]> = [
  ["USDTRY", "exotic", "USD", "TRY"],
  ["EURTRY", "exotic", "EUR", "TRY"],
  ["USDZAR", "exotic", "USD", "ZAR"],
  ["USDMXN", "exotic", "USD", "MXN"],
  ["USDBRL", "exotic", "USD", "BRL"],
  ["USDCNH", "exotic", "USD", "CNH"],
  ["USDHKD", "exotic", "USD", "HKD"],
  ["USDSGD", "exotic", "USD", "SGD"],
  ["USDSEK", "exotic", "USD", "SEK"],
  ["USDNOK", "exotic", "USD", "NOK"],
  ["USDDKK", "exotic", "USD", "DKK"],
  ["USDPLN", "exotic", "USD", "PLN"],
  ["USDHUF", "exotic", "USD", "HUF"],
  ["USDCZK", "exotic", "USD", "CZK"],
  ["USDTHB", "exotic", "USD", "THB"],
  ["USDINR", "exotic", "USD", "INR"],
  ["USDILS", "exotic", "USD", "ILS"],
  ["USDKRW", "exotic", "USD", "KRW"],
  ["EURSEK", "exotic", "EUR", "SEK"],
  ["EURNOK", "exotic", "EUR", "NOK"],
  ["EURPLN", "exotic", "EUR", "PLN"],
  ["EURHUF", "exotic", "EUR", "HUF"],
  ["EURCZK", "exotic", "EUR", "CZK"],
  ["GBPSEK", "exotic", "GBP", "SEK"],
  ["GBPNOK", "exotic", "GBP", "NOK"],
  ["GBPPLN", "exotic", "GBP", "PLN"],
  ["CHFSEK", "exotic", "CHF", "SEK"],
  ["CADCHF", "minor", "CAD", "CHF"],
  ["CADNZD", "minor", "CAD", "NZD"],
  ["NZDCHF", "minor", "NZD", "CHF"],
  ["XPTUSD", "metal", "XPT", "USD"],
  ["XPDUSD", "metal", "XPD", "USD"],
  ["USOIL", "energy", "WTI", "USD"],
  ["UKOIL", "energy", "BRENT", "USD"],
  ["BTCUSD", "crypto", "BTC", "USD"],
  ["ETHUSD", "crypto", "ETH", "USD"],
];

const CURRENCY_NAMES: Record<string, string> = {
  EUR: "Euro", USD: "US Dollar", GBP: "British Pound", JPY: "Japanese Yen",
  CHF: "Swiss Franc", AUD: "Australian Dollar", CAD: "Canadian Dollar",
  NZD: "New Zealand Dollar", SEK: "Swedish Krona", NOK: "Norwegian Krone",
  DKK: "Danish Krone", PLN: "Polish Zloty", HUF: "Hungarian Forint",
  CZK: "Czech Koruna", TRY: "Turkish Lira", ZAR: "South African Rand",
  MXN: "Mexican Peso", BRL: "Brazilian Real", CNH: "Chinese Yuan Offshore",
  HKD: "Hong Kong Dollar", SGD: "Singapore Dollar", THB: "Thai Baht",
  INR: "Indian Rupee", KRW: "South Korean Won", ILS: "Israeli Shekel",
  XAU: "Gold", XAG: "Silver", XPT: "Platinum", XPD: "Palladium",
  WTI: "Crude Oil WTI", BRENT: "Brent Crude", BTC: "Bitcoin", ETH: "Ethereum",
};

const ALIASES: Record<string, string> = {
  gold: "XAUUSD", xau: "XAUUSD", auxusd: "XAUUSD",
  silver: "XAGUSD", xag: "XAGUSD",
  platinum: "XPTUSD", palladium: "XPDUSD",
  oil: "USOIL", wti: "USOIL", crude: "USOIL", brent: "UKOIL",
  bitcoin: "BTCUSD", btc: "BTCUSD", ethereum: "ETHUSD", eth: "ETHUSD",
  euro: "EURUSD", cable: "GBPUSD", pound: "GBPUSD", yen: "USDJPY",
  aussie: "AUDUSD", kiwi: "NZDUSD", loonie: "USDCAD",
  turkish: "USDTRY", lira: "USDTRY", rand: "USDZAR", peso: "USDMXN",
};

function pairName(base: string, quote: string): string {
  return `${CURRENCY_NAMES[base] ?? base} / ${CURRENCY_NAMES[quote] ?? quote}`;
}

function shortPair(symbol: string, base?: string, quote?: string): string {
  if (symbol === "USOIL") return "WTI/USD";
  if (symbol === "UKOIL") return "BRENT/USD";
  if (base && quote) return `${base}/${quote}`;
  if (symbol.length >= 6) return `${symbol.slice(0, 3)}/${symbol.slice(3)}`;
  return symbol;
}

function buildCatalog(): CatalogEntry[] {
  const entries: CatalogEntry[] = Object.values(SYMBOLS).map((s) => ({
    ...s,
    in_default: true,
  }));

  for (const [symbol, category, base, quote] of EXTRA) {
    if (!DEFAULT_SYMBOLS.has(symbol)) {
      entries.push({
        symbol,
        name: pairName(base, quote),
        short: shortPair(symbol, base, quote),
        category,
        in_default: false,
      });
    }
  }
  return entries;
}

export const CATALOG: CatalogEntry[] = buildCatalog();

export function searchCatalogLocal(query: string, limit = 12): CatalogEntry[] {
  const q = query.trim().toLowerCase();
  if (!q) return CATALOG.slice(0, limit);

  if (ALIASES[q]) {
    const hit = CATALOG.find((e) => e.symbol === ALIASES[q]);
    return hit ? [hit] : [];
  }

  const normalized = q.replace(/[^a-z]/g, "").toUpperCase();
  if (normalized.length >= 6) {
    const exact = CATALOG.find((e) => e.symbol === normalized);
    if (exact) return [exact];
    const fuzzy = fuzzySymbol(normalized);
    if (fuzzy) {
      const hit = CATALOG.find((e) => e.symbol === fuzzy);
      if (hit) return [hit];
    }
  }

  const scored = CATALOG.map((entry) => ({ entry, score: matchScore(q, entry) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score || a.entry.symbol.localeCompare(b.entry.symbol));

  return scored.slice(0, limit).map((x) => x.entry);
}

function fuzzySymbol(q: string): string | null {
  let best: string | null = null;
  let bestDist = 3;
  for (const entry of CATALOG) {
    if (entry.symbol.length !== q.length) continue;
    const dist = levenshtein(q, entry.symbol);
    if (dist > 0 && dist < bestDist) {
      bestDist = dist;
      best = entry.symbol;
    }
  }
  return best;
}

function levenshtein(a: string, b: string): number {
  const m = a.length;
  const n = b.length;
  const dp = Array.from({ length: m + 1 }, () => Array(n + 1).fill(0));
  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,
        dp[i][j - 1] + 1,
        dp[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
  }
  return dp[m][n];
}

function matchScore(q: string, entry: CatalogEntry): number {
  const sym = entry.symbol.toLowerCase();
  const short = entry.short.toLowerCase().replace("/", "");
  const name = entry.name.toLowerCase();
  const compact = q.replace(/[^a-z0-9]/g, "");

  if (sym === compact || short === compact) return 100;
  if (sym.startsWith(compact) || short.startsWith(compact)) return 80;
  if (sym.includes(compact) || short.includes(compact)) return 60;
  if (name.includes(q)) return 50;
  for (const part of name.split(/[\s/]+/)) {
    if (part.startsWith(q)) return 30;
  }
  return 0;
}
