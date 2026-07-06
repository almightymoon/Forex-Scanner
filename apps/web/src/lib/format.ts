/** Format OHLC / level prices for display. */
export function formatPrice(symbol: string, price: number): string {
  if (symbol.includes("JPY")) return price.toFixed(3);
  if (symbol.startsWith("XAU") || symbol.startsWith("XAG")) return price.toFixed(2);
  return price.toFixed(5);
}

export function formatPriceRange(symbol: string, low: number, high: number): string {
  return `${formatPrice(symbol, low)} – ${formatPrice(symbol, high)}`;
}

export function formatSession(session: string): string {
  return session.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
