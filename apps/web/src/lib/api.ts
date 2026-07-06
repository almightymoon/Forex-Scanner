import { searchCatalogLocal } from "./symbolCatalog";

export interface ScoreBreakdown {
  trend: number;
  smc: number;
  momentum: number;
  support_resistance: number;
  volume_volatility: number;
  mtf_alignment: number;
  news_risk: number;
}

export interface DecisionFactor {
  category: string;
  score: number;
  max_score: number;
  confidence: number;
  reasons: string[];
}

export interface DetectedPattern {
  id: string;
  label: string;
  direction: string;
}

export interface ScoreDelta {
  text: string;
  delta: number;
  sign: string;
}

export interface Explainability {
  score: number;
  confidence: number;
  confidence_pct: number;
  session: string;
  categories: Array<{ label: string; score: number; max_score: number }>;
  detected_patterns: DetectedPattern[];
  score_deltas: ScoreDelta[];
  historical?: HistoricalEvidence;
  evidence?: EvidenceItem[];
  adjustments?: string[];
}

export interface EvidenceItem {
  label: string;
  passed: boolean;
  category: string;
}

export interface EngineOutput {
  name: string;
  score: number;
  max_score: number;
  confidence: number;
  direction: string;
  reasons: string[];
  metadata?: Record<string, unknown>;
  warnings?: string[];
}

export interface HistoricalEvidence {
  sample_size: number;
  win_rate: number;
  avg_rr: number;
  avg_duration_bars: number;
  avg_duration_hours?: number;
  similar_setups?: string[];
  best_session?: string;
  worst_session?: string;
}

export interface ScannerSignal {
  symbol: string;
  timeframe: string;
  direction: "buy" | "sell" | "neutral";
  score: number;
  rating: "ignore" | "moderate" | "good" | "strong" | "elite";
  trend: "bullish" | "bearish" | "ranging";
  risk_level: "low" | "medium" | "high" | "extreme";
  score_breakdown: ScoreBreakdown;
  technical_reasons: string[];
  smc_reasons: string[];
  confidence?: number;
  session?: string;
  decision_factors?: DecisionFactor[];
  detected_patterns?: DetectedPattern[];
  score_deltas?: ScoreDelta[];
  explainability?: Explainability;
  engine_outputs?: EngineOutput[];
  score_breakdown_v2?: Record<string, number>;
  warnings?: string[];
  trade_type?: string;
  expected_duration?: string;
  historical_evidence?: HistoricalEvidence;
  market_features?: Record<string, unknown>;
  entry_zone_low?: number;
  entry_zone_high?: number;
  stop_loss?: number;
  take_profit_1?: number;
  take_profit_2?: number;
  take_profit_3?: number;
  risk_reward?: number;
  ai_explanation?: string;
  created_at: string;
}

export interface SymbolInfo {
  symbol: string;
  name: string;
  short: string;
  price: number;
  category: string;
  live?: boolean;
  in_default?: boolean;
  base?: string;
  quote?: string;
}

export interface SymbolSearchResult {
  symbol: string;
  name: string;
  short: string;
  category: string;
  in_default: boolean;
  price?: number;
  live?: boolean;
}

// Browser: use same-origin proxy (/api → backend). Server: can use explicit URL.
const API_BASE =
  typeof window !== "undefined"
    ? ""
    : process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001";

const DEV_EMAIL = process.env.NEXT_PUBLIC_DEV_EMAIL || "dev@fxnav.local";
const DEV_PASSWORD = process.env.NEXT_PUBLIC_DEV_PASSWORD || "dev123456";

let sessionPromise: Promise<void> | null = null;

/** Register or log in a dev user when no JWT is stored (local dashboard use). */
export async function ensureSession(): Promise<void> {
  if (typeof window === "undefined") return;
  if (localStorage.getItem("fxnav_token")) return;

  if (!sessionPromise) {
    sessionPromise = (async () => {
      const register = await fetch(`${API_BASE}/api/v1/auth/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "Dev User", email: DEV_EMAIL, password: DEV_PASSWORD }),
      });

      if (register.ok) {
        const data = await register.json();
        localStorage.setItem("fxnav_token", data.access_token);
        if (data.refresh_token) {
          localStorage.setItem("fxnav_refresh_token", data.refresh_token);
        }
        return;
      }

      await login(DEV_EMAIL, DEV_PASSWORD);
    })().catch((err) => {
      sessionPromise = null;
      throw err;
    });
  }

  await sessionPromise;
}

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const url = `${API_BASE}${path}`;
  const headers = new Headers(init?.headers);
  if (typeof window !== "undefined") {
    await ensureSession();
    const token = localStorage.getItem("fxnav_token");
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
  }
  try {
    let res = await fetch(url, { ...init, headers });

    // Token stale after API restart (in-memory user store cleared)
    if (res.status === 401 && typeof window !== "undefined") {
      localStorage.removeItem("fxnav_token");
      localStorage.removeItem("fxnav_refresh_token");
      sessionPromise = null;
      await ensureSession();
      const retryHeaders = new Headers(init?.headers);
      const token = localStorage.getItem("fxnav_token");
      if (token) retryHeaders.set("Authorization", `Bearer ${token}`);
      res = await fetch(url, { ...init, headers: retryHeaders });
    }

    return res;
  } catch (err) {
    throw new Error(
      `Cannot reach API at ${path}. Start it with: ./scripts/run-api.sh`,
      { cause: err },
    );
  }
}

export async function login(email: string, password: string): Promise<void> {
  const res = await apiFetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error("Login failed");
  const data = await res.json();
  if (typeof window !== "undefined") {
    localStorage.setItem("fxnav_token", data.access_token);
    if (data.refresh_token) {
      localStorage.setItem("fxnav_refresh_token", data.refresh_token);
    }
  }
}

export interface BacktestResult {
  symbol: string;
  timeframe: string;
  total_trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  avg_rr: number;
  max_drawdown: number;
  avg_score: number;
}

export interface DashboardData {
  stats: { total_scans: number; elite_setups: number; scans_today: number };
  signals: ScannerSignal[];
  calendar: Array<{ currency: string; title: string; impact: string; event_time: string }>;
  heatmap: Array<{ symbol: string; score: number; direction: string; trend: string }>;
  market_status: { live: boolean; pairs_with_prices: number; source: string };
  count: number;
  scanned_at: string;
}

export async function fetchDashboard(
  minScore = 60,
  extraSymbols: string[] = [],
  limit = 30,
): Promise<DashboardData> {
  const params = new URLSearchParams({
    min_score: String(minScore),
    limit: String(limit),
  });
  if (extraSymbols.length > 0) {
    params.set("symbols", extraSymbols.join(","));
  }
  const res = await apiFetch(`/api/v1/dashboard?${params}`, { cache: "no-store" });
  if (!res.ok) {
    let detail = "Failed to fetch dashboard";
    try {
      const body = await res.json();
      detail = body.message || body.detail || detail;
    } catch {
      // ignore parse errors
    }
    throw new Error(detail);
  }
  return res.json();
}

export async function fetchLiveScanner(minScore = 60, extraSymbols: string[] = []): Promise<ScannerSignal[]> {
  const params = new URLSearchParams({ min_score: String(minScore) });
  if (extraSymbols.length > 0) {
    params.set("symbols", extraSymbols.join(","));
  }
  const res = await apiFetch(`/api/v1/scanner/live?${params}`, {
    cache: "no-store",
  });
  if (!res.ok) throw new Error("Failed to fetch scanner data");
  const data = await res.json();
  return data.signals;
}

export async function searchSymbols(query: string, limit = 12): Promise<SymbolSearchResult[]> {
  try {
    const params = new URLSearchParams({ q: query, limit: String(limit) });
    const res = await apiFetch(`/api/v1/symbols/search?${params}`, { cache: "no-store" });
    if (res.ok) {
      const data = await res.json();
      if (data.results?.length) return data.results;
    }
  } catch {
    // fall through to local search
  }

  return searchCatalogLocal(query, limit).map((e) => ({
    symbol: e.symbol,
    name: e.name,
    short: e.short,
    category: e.category,
    in_default: e.in_default,
  }));
}

export async function fetchSymbols(): Promise<SymbolInfo[]> {
  const res = await apiFetch(`/api/v1/symbols`, { next: { revalidate: 60 } });
  if (!res.ok) throw new Error("Failed to fetch symbols");
  return res.json();
}

export async function fetchLivePrices(): Promise<Record<string, number>> {
  const res = await apiFetch(`/api/v1/market/live`, { next: { revalidate: 60 } });
  if (!res.ok) return {};
  const data = await res.json();
  return data.prices || {};
}

export async function fetchCalendar(): Promise<{ events: Array<{ currency: string; title: string; impact: string; event_time: string }> }> {
  const res = await apiFetch(`/api/v1/calendar`, { next: { revalidate: 300 } });
  if (!res.ok) throw new Error("Failed to fetch calendar");
  return res.json();
}

export async function fetchStats(): Promise<{ total_scans: number; elite_setups: number; scans_today: number }> {
  const res = await apiFetch(`/health`, { next: { revalidate: 30 } });
  if (!res.ok) return { total_scans: 0, elite_setups: 0, scans_today: 0 };
  const data = await res.json();
  return data.stats || { total_scans: 0, elite_setups: 0, scans_today: 0 };
}

export async function fetchCandles(symbol: string, timeframe = "H1"): Promise<Array<{ timestamp: string; open: number; high: number; low: number; close: number }>> {
  const res = await apiFetch(`/api/v1/market/${symbol}/candles?timeframe=${timeframe}&count=100`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.candles || [];
}

export interface Plan {
  id: string;
  name: string;
  price_monthly: number;
  features: string[];
}

export async function fetchBacktest(symbol: string, timeframe = "H1"): Promise<BacktestResult | null> {
  const res = await apiFetch(`/api/v1/backtest/${symbol}?timeframe=${timeframe}`);
  if (!res.ok) return null;
  return res.json();
}

export async function fetchPlans(): Promise<Plan[]> {
  const res = await apiFetch(`/api/v1/billing/plans`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.plans || [];
}
