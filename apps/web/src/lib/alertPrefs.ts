const STORAGE_KEY = "fxnav_alert_prefs";

export interface AlertPrefs {
  /** Symbols that should surface a local alert when they print a setup. */
  symbols: string[];
  minScore: number;
}

const DEFAULTS: AlertPrefs = {
  symbols: [],
  minScore: 70,
};

export function loadAlertPrefs(): AlertPrefs {
  if (typeof window === "undefined") return { ...DEFAULTS };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { ...DEFAULTS };
    const parsed = JSON.parse(raw) as Partial<AlertPrefs>;
    return {
      symbols: Array.isArray(parsed.symbols)
        ? parsed.symbols.map((s) => String(s).toUpperCase())
        : [],
      minScore:
        typeof parsed.minScore === "number" && parsed.minScore >= 0
          ? parsed.minScore
          : DEFAULTS.minScore,
    };
  } catch {
    return { ...DEFAULTS };
  }
}

function save(prefs: AlertPrefs): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
}

export function setAlertSymbol(symbol: string, enabled: boolean, current: AlertPrefs): AlertPrefs {
  const key = symbol.toUpperCase();
  const symbols = enabled
    ? current.symbols.includes(key)
      ? current.symbols
      : [...current.symbols, key]
    : current.symbols.filter((s) => s !== key);
  const next = { ...current, symbols };
  save(next);
  return next;
}

export function pruneAlertSymbols(watchlist: string[], current: AlertPrefs): AlertPrefs {
  const allowed = new Set(watchlist.map((s) => s.toUpperCase()));
  const symbols = current.symbols.filter((s) => allowed.has(s));
  if (symbols.length === current.symbols.length) return current;
  const next = { ...current, symbols };
  save(next);
  return next;
}
