"use client";

import { useEffect, useRef, useState } from "react";
import { SignalCard } from "@/components/SignalCard";
import { EconomicCalendar } from "@/components/EconomicCalendar";
import { Heatmap } from "@/components/Heatmap";
import type { ScannerSignal, BacktestResult, ValidationReportPayload, HealthPayload } from "@/lib/api";
import { fetchDashboard, fetchCandles, fetchBacktest, fetchValidation, fetchHealth } from "@/lib/api";
import { DetailPanel } from "@/components/DetailPanel";
import { PairSearch } from "@/components/PairSearch";
import { ScrollReveal } from "@/components/ScrollReveal";
import { loadCustomPairs, addCustomPair, removeCustomPair } from "@/lib/watchlist";
import {
  loadAlertPrefs,
  setAlertSymbol,
  pruneAlertSymbols,
  type AlertPrefs,
} from "@/lib/alertPrefs";
import { useHeaderHeight } from "@/hooks/useHeaderHeight";
import { useScrollEffects } from "@/hooks/useScrollEffects";

interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export default function Dashboard() {
  useHeaderHeight();
  const { scrolled } = useScrollEffects();
  const [signals, setSignals] = useState<ScannerSignal[]>([]);
  const [selected, setSelected] = useState<ScannerSignal | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [backtest, setBacktest] = useState<BacktestResult | null>(null);
  const [events, setEvents] = useState<Array<{ currency: string; title: string; impact: string; event_time: string }>>([]);
  const [minScore, setMinScore] = useState(70);
  const [loading, setLoading] = useState(true);
  const [lastScan, setLastScan] = useState<string>("");
  const [stats, setStats] = useState({ total_scans: 0, elite_setups: 0, scans_today: 0 });
  const [customPairs, setCustomPairs] = useState<string[]>(() => loadCustomPairs());
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [currencyFilter, setCurrencyFilter] = useState<string | null>(null);
  const [directionFilter, setDirectionFilter] = useState<"all" | "buy" | "sell">("all");
  const [timeframeFilter, setTimeframeFilter] = useState<string>("all");
  const [validation, setValidation] = useState<ValidationReportPayload | null>(null);
  const [health, setHealth] = useState<HealthPayload | null>(null);
  const [alertPrefs, setAlertPrefs] = useState<AlertPrefs>(() => loadAlertPrefs());
  const [alertHits, setAlertHits] = useState<ScannerSignal[]>([]);
  const seenAlerts = useRef<Set<string>>(new Set());

  const filteredSignals = signals.filter((s) => {
    if (currencyFilter) {
      const hit =
        s.symbol.startsWith(currencyFilter) || s.symbol.slice(3).startsWith(currencyFilter);
      if (!hit) return false;
    }
    if (directionFilter !== "all" && s.direction !== directionFilter) return false;
    if (timeframeFilter !== "all" && String(s.timeframe) !== timeframeFilter) return false;
    return true;
  });

  const loadSignals = async () => {
    // Avoid stacking refreshes while a long scan is in flight.
    if (loading && signals.length > 0) return;
    setLoading(true);
    setFetchError(null);
    try {
      const dashboard = await fetchDashboard(minScore, customPairs);
      setSignals(dashboard.signals);
      setStats(dashboard.stats);
      setEvents(dashboard.calendar || []);
      setLastScan(
        dashboard.scanned_at
          ? new Date(dashboard.scanned_at).toLocaleTimeString()
          : new Date().toLocaleTimeString(),
      );

      const prefs = loadAlertPrefs();
      const hits = dashboard.signals.filter(
        (s) =>
          prefs.symbols.includes(s.symbol.toUpperCase()) &&
          s.score >= prefs.minScore,
      );
      setAlertHits(hits);
      for (const hit of hits) {
        const key = `${hit.symbol}-${hit.timeframe}-${hit.direction}-${hit.score}`;
        if (seenAlerts.current.has(key)) continue;
        seenAlerts.current.add(key);
        if (typeof window !== "undefined" && "Notification" in window) {
          if (Notification.permission === "granted") {
            new Notification(`${hit.symbol} ${hit.direction.toUpperCase()}`, {
              body: `Score ${hit.score} · ${hit.timeframe} · ${hit.rating}`,
            });
          }
        }
      }
    } catch (err) {
      console.error("Scanner fetch failed:", err);
      setFetchError(err instanceof Error ? err.message : "Failed to load scanner data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;

    const run = async () => {
      if (cancelled || inFlight) return;
      inFlight = true;
      try {
        await loadSignals();
      } finally {
        inFlight = false;
      }
    };

    run();
    // Full-universe scans are slow; don't hammer the API every 30s.
    const interval = setInterval(run, 120000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [minScore, customPairs]);

  useEffect(() => {
    setAlertPrefs((prev) => pruneAlertSymbols(customPairs, prev));
  }, [customPairs]);

  useEffect(() => {
    if (!selected) { setCandles([]); setBacktest(null); return; }
    fetchCandles(selected.symbol, selected.timeframe).then(setCandles).catch(() => setCandles([]));
    fetchBacktest(selected.symbol, selected.timeframe).then(setBacktest).catch(() => setBacktest(null));
  }, [selected]);

  useEffect(() => {
    let cancelled = false;
    fetchValidation()
      .then((report) => {
        if (!cancelled) setValidation(report);
      })
      .catch(() => {
        if (!cancelled) setValidation(null);
      });
    return () => {
      cancelled = true;
    };
  }, [lastScan]);

  useEffect(() => {
    let cancelled = false;
    const loadHealth = () => {
      fetchHealth()
        .then((payload) => {
          if (!cancelled) setHealth(payload);
        })
        .catch(() => {
          if (!cancelled) setHealth(null);
        });
    };
    loadHealth();
    const interval = setInterval(loadHealth, 60000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    if (!selected) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSelected(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);

  useEffect(() => {
    document.body.style.overflow = selected ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [selected]);

  const buyCount = filteredSignals.filter((s) => s.direction === "buy").length;
  const sellCount = filteredSignals.filter((s) => s.direction === "sell").length;
  const eliteCount = filteredSignals.filter((s) => s.rating === "elite").length;
  const healthStatus = health?.status || (fetchError ? "down" : "unknown");
  const healthLabel =
    healthStatus === "healthy"
      ? "Live"
      : healthStatus === "warning"
        ? health?.simulated
          ? "Simulated"
          : health?.provider_status === "rate_limited"
            ? "Rate limited"
            : "Warning"
        : healthStatus === "degraded"
          ? "Degraded"
          : healthStatus === "down"
            ? "Offline"
            : "Checking";
  const healthTitle = [
    health?.provider ? `Provider: ${health.provider}` : null,
    health?.provider_status ? `Status: ${health.provider_status}` : null,
    health?.pipeline_version ? `Pipeline: ${health.pipeline_version}` : null,
    health?.validation_store?.backend
      ? `Outcomes: ${health.validation_store.backend}`
      : null,
    health?.paper_broker?.enabled
      ? `Paper: ${health.paper_broker.open ?? 0} open / ${health.paper_broker.closed ?? 0} closed`
      : null,
    health?.broker_venue
      ? `Venue: ${health.broker_venue.selected || health.broker_venue.venue}${health.broker_venue.orders_armed ? " (armed)" : ""}`
      : null,
    health?.h5_accrual
      ? `H5: ${health.h5_accrual.unique_bars ?? "?"}/${health.h5_accrual.required_bars ?? 1400}${health.h5_accrual.passed ? " ready" : ""}`
      : null,
    health?.warning || null,
  ]
    .filter(Boolean)
    .join(" · ");

  const paper = health?.paper_broker;
  const paperClosed = paper?.closed ?? 0;
  const paperOpen = paper?.open ?? 0;
  const h5 = health?.h5_accrual;

  return (
    <div className="app-shell">
      <header className={`header${scrolled ? " is-scrolled" : ""}`}>
        <div className="header-brand">
          <div className="logo-mark" aria-hidden>FX</div>
          <div>
            <h1>FX Navigators</h1>
            <p className="subtitle">Project Atlas · Live Scanner</p>
          </div>
        </div>

        <div className="header-actions">
          <PairSearch
            customPairs={customPairs}
            onAdd={(sym) => setCustomPairs((prev) => addCustomPair(sym, prev))}
            onRemove={(sym) => {
              setCustomPairs((prev) => removeCustomPair(sym, prev));
              setAlertPrefs((prev) => setAlertSymbol(sym, false, prev));
            }}
            alertSymbols={alertPrefs.symbols}
            onToggleAlert={(sym, enabled) => {
              setAlertPrefs((prev) => setAlertSymbol(sym, enabled, prev));
              if (enabled && typeof window !== "undefined" && "Notification" in window) {
                if (Notification.permission === "default") {
                  void Notification.requestPermission();
                }
              }
            }}
          />
          <div className="header-controls">
            <div
              className={`live-pill live-pill-${healthStatus === "healthy" ? "ok" : healthStatus === "warning" ? "warn" : healthStatus === "degraded" || healthStatus === "down" ? "bad" : "pending"}`}
              title={healthTitle || undefined}
            >
              <span className="live-dot" />
              {healthLabel}
            </div>
            <div className="filter-group">
              <label htmlFor="min-score">Min score</label>
              <select id="min-score" value={minScore} onChange={(e) => setMinScore(Number(e.target.value))}>
                <option value={60}>60+</option>
                <option value={70}>70+ Good</option>
                <option value={80}>80+ Strong</option>
                <option value={90}>90+ Elite</option>
              </select>
            </div>
            <div className="filter-group">
              <label htmlFor="direction-filter">Direction</label>
              <select
                id="direction-filter"
                value={directionFilter}
                onChange={(e) => setDirectionFilter(e.target.value as "all" | "buy" | "sell")}
              >
                <option value="all">All</option>
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
            </div>
            <div className="filter-group">
              <label htmlFor="tf-filter">Timeframe</label>
              <select
                id="tf-filter"
                value={timeframeFilter}
                onChange={(e) => setTimeframeFilter(e.target.value)}
              >
                <option value="all">All</option>
                <option value="M15">M15</option>
                <option value="H1">H1</option>
                <option value="H4">H4</option>
                <option value="D1">D1</option>
              </select>
            </div>
            <button type="button" className="btn-primary" onClick={loadSignals} disabled={loading}>
              {loading ? (
                <><span className="btn-spinner" /> Scanning</>
              ) : (
                "Refresh"
              )}
            </button>
            {lastScan && <span className="last-scan">Updated {lastScan}</span>}
          </div>
        </div>
      </header>

      <main className="dashboard">
        {fetchError && (
          <div className="state-message" style={{ marginBottom: "1rem", color: "#f87171" }}>
            <p>{fetchError}</p>
            <span>Check API logs or try Refresh. If using Twelve Data free tier, enable Polygon fallback.</span>
          </div>
        )}

        {alertHits.length > 0 && (
          <ScrollReveal delayMs={40}>
            <div className="alert-banner" role="status">
              <span className="alert-banner-label">Watch alerts</span>
              <div className="alert-banner-list">
                {alertHits.slice(0, 6).map((hit) => (
                  <button
                    key={`${hit.symbol}-${hit.timeframe}-${hit.direction}`}
                    type="button"
                    className="alert-banner-chip"
                    onClick={() => setSelected(hit)}
                  >
                    {hit.symbol} {hit.direction.toUpperCase()} · {hit.score}
                  </button>
                ))}
              </div>
              <button
                type="button"
                className="alert-banner-dismiss"
                onClick={() => setAlertHits([])}
                aria-label="Dismiss alerts"
              >
                Dismiss
              </button>
            </div>
          </ScrollReveal>
        )}

        <ScrollReveal as="section" className="stats-bar" delayMs={60}>
          <div className="stat-card">
            <span className="stat-value accent">{filteredSignals.length}</span>
            <span className="stat-label">Active signals</span>
          </div>
          <div className="stat-card">
            <span className="stat-value">{stats.scans_today}</span>
            <span className="stat-label">Scans today</span>
          </div>
          <div className="stat-card">
            <span className="stat-value buy">{buyCount}</span>
            <span className="stat-label">Buy setups</span>
          </div>
          <div className="stat-card">
            <span className="stat-value sell">{sellCount}</span>
            <span className="stat-label">Sell setups</span>
          </div>
          {eliteCount > 0 && (
            <div className="stat-card stat-elite">
              <span className="stat-value elite">{eliteCount}</span>
              <span className="stat-label">Elite</span>
            </div>
          )}
        </ScrollReveal>

        {validation?.metrics && (validation.metrics.closed_signals ?? 0) > 0 && (
          <ScrollReveal as="section" className="validation-strip" delayMs={100} aria-label="Validation summary">
            <div className="validation-strip-main">
              <span className="validation-strip-label">Tracked outcomes</span>
              <span className="validation-strip-metric">
                <strong>
                  {validation.metrics.win_rate != null
                    ? `${validation.metrics.win_rate}%`
                    : "—"}
                </strong>{" "}
                win rate
              </span>
              <span className="validation-strip-sep" aria-hidden>
                ·
              </span>
              <span className="validation-strip-metric">
                {validation.metrics.wins ?? 0}W / {validation.metrics.losses ?? 0}L
                <span className="validation-strip-muted">
                  {" "}
                  ({validation.metrics.closed_signals} closed)
                </span>
              </span>
            </div>
            {validation.recommendations?.[0] ? (
              <p className="validation-strip-note">{validation.recommendations[0]}</p>
            ) : null}
          </ScrollReveal>
        )}

        {paper?.enabled && (paperClosed > 0 || paperOpen > 0) && (
          <ScrollReveal as="section" className="validation-strip paper-strip" delayMs={110} aria-label="Paper broker summary">
            <div className="validation-strip-main">
              <span className="validation-strip-label">Paper book</span>
              <span className="validation-strip-metric">
                <strong>
                  {paper.metrics?.expectancy != null
                    ? `${paper.metrics.expectancy >= 0 ? "+" : ""}${paper.metrics.expectancy}`
                    : "—"}
                </strong>{" "}
                E[R]
              </span>
              <span className="validation-strip-sep" aria-hidden>
                ·
              </span>
              <span className="validation-strip-metric">
                {paper.metrics?.wins ?? 0}W / {paper.metrics?.losses ?? 0}L
                <span className="validation-strip-muted">
                  {" "}
                  ({paperClosed} closed · {paperOpen} open)
                </span>
              </span>
              {paper.metrics?.win_rate != null ? (
                <>
                  <span className="validation-strip-sep" aria-hidden>
                    ·
                  </span>
                  <span className="validation-strip-metric">{paper.metrics.win_rate}% win</span>
                </>
              ) : null}
            </div>
          </ScrollReveal>
        )}

        {h5 && !h5.passed && (
          <ScrollReveal as="section" className="validation-strip h5-strip" delayMs={115} aria-label="H5 accrual status">
            <div className="validation-strip-main">
              <span className="validation-strip-label">H5 accrual</span>
              <span className="validation-strip-metric">
                <strong>{h5.unique_bars ?? "—"}</strong>
                <span className="validation-strip-muted">
                  {" "}
                  / {h5.required_bars ?? 1400} bars
                </span>
              </span>
              <span className="validation-strip-sep" aria-hidden>
                ·
              </span>
              <span className="validation-strip-metric">
                {h5.bars_remaining ?? "—"} remaining
              </span>
              {h5.latest_utc ? (
                <>
                  <span className="validation-strip-sep" aria-hidden>
                    ·
                  </span>
                  <span className="validation-strip-metric validation-strip-muted">
                    tip {String(h5.latest_utc).slice(0, 10)}
                  </span>
                </>
              ) : null}
            </div>
            <p className="validation-strip-note">
              Drop a fresh MT5 post-2026H1 export in MT5-scripts/ to unblock prospective shadow.
            </p>
          </ScrollReveal>
        )}

        {filteredSignals.length > 0 && (
          <ScrollReveal as="section" className="panel heatmap-section" delayMs={120}>
            <div className="panel-header">
              <h2>Market heatmap</h2>
              <span className="panel-hint">{filteredSignals.length} pairs · click to inspect</span>
            </div>
            <Heatmap
              signals={filteredSignals}
              selectedSymbol={selected?.symbol}
              onSelect={setSelected}
            />
          </ScrollReveal>
        )}

        {currencyFilter && (
          <div className="calendar-filter-banner">
            <span>Showing pairs affected by <strong>{currencyFilter}</strong> news</span>
            <button type="button" className="calendar-filter-clear" onClick={() => setCurrencyFilter(null)}>
              Clear filter
            </button>
          </div>
        )}

        <div className="main-content">
          <ScrollReveal as="section" className="signals-section" delayMs={140}>
            <div className="panel-header">
              <h2>Scanner feed</h2>
              <span className="panel-hint">Sorted by confidence score</span>
            </div>

            <div className="signals-grid">
              {loading && signals.length === 0 ? (
                <div className="state-message loading-state">
                  <span className="btn-spinner large" />
                  <p>Scanning {28 + customPairs.length}+ pairs including Gold/USD…</p>
                </div>
              ) : filteredSignals.length === 0 ? (
                <div className="state-message empty-state">
                  <p>
                    {currencyFilter
                      ? `No setups above ${minScore} for ${currencyFilter} pairs right now.`
                      : directionFilter !== "all" || timeframeFilter !== "all"
                        ? `No setups match the current filters (score ${minScore}+).`
                        : `No setups above ${minScore} points right now.`}
                  </p>
                  <span>
                    {currencyFilter
                      ? "Clear the calendar filter or lower the minimum score."
                      : directionFilter !== "all" || timeframeFilter !== "all"
                        ? "Clear direction/timeframe filters or lower the minimum score."
                        : "Try lowering the minimum score filter."}
                  </span>
                </div>
              ) : (
                filteredSignals.map((signal, index) => (
                  <ScrollReveal
                    key={`${signal.symbol}-${signal.timeframe}`}
                    className="scroll-reveal-card"
                    delayMs={Math.min(index * 45, 360)}
                  >
                    <SignalCard
                      signal={signal}
                      selected={selected?.symbol === signal.symbol}
                      watched={customPairs.includes(signal.symbol.toUpperCase())}
                      onSelect={setSelected}
                    />
                  </ScrollReveal>
                ))
              )}
            </div>
          </ScrollReveal>

          <ScrollReveal as="aside" className="side-panel scroll-reveal-fade" delayMs={180}>
            <div className="calendar-panel panel">
              <div className="panel-header">
                <h2>Economic calendar</h2>
                <span className="panel-hint">Upcoming events</span>
              </div>
              <EconomicCalendar
                events={events}
                activeCurrency={currencyFilter}
                onFilterCurrency={setCurrencyFilter}
              />
            </div>
          </ScrollReveal>
        </div>
      </main>

      {selected && (
        <div className="detail-sheet" role="dialog" aria-label="Signal details">
          <DetailPanel
            signal={selected}
            candles={candles}
            backtest={backtest}
            onClose={() => setSelected(null)}
            onSignalChange={setSelected}
            customPairs={customPairs}
            onWatchlistAdd={(sym) => setCustomPairs((prev) => addCustomPair(sym, prev))}
            onWatchlistRemove={(sym) => setCustomPairs((prev) => removeCustomPair(sym, prev))}
          />
        </div>
      )}
    </div>
  );
}
