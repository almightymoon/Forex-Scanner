const STORAGE_KEY = "fxnav_custom_pairs";

export function loadCustomPairs(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.map((s: string) => s.toUpperCase()) : [];
  } catch {
    return [];
  }
}

export function saveCustomPairs(symbols: string[]): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(symbols));
}

export function addCustomPair(symbol: string, current: string[]): string[] {
  const key = symbol.toUpperCase();
  if (current.includes(key)) return current;
  const next = [...current, key];
  saveCustomPairs(next);
  return next;
}

export function removeCustomPair(symbol: string, current: string[]): string[] {
  const next = current.filter((s) => s !== symbol.toUpperCase());
  saveCustomPairs(next);
  return next;
}
