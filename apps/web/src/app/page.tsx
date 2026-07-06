"use client";

import { useEffect, useState } from "react";
import { SignalCard } from "@/components/SignalCard";
import { EconomicCalendar } from "@/components/EconomicCalendar";
import { Heatmap } from "@/components/Heatmap";
import type { ScannerSignal, BacktestResult } from "@/lib/api";
import { fetchDashboard, fetchCandles, fetchBacktest } from "@/lib/api";
import { DetailPanel } from "@/components/DetailPanel";
import { PairSearch } from "@/components/PairSearch";
import { loadCustomPairs, addCustomPair, removeCustomPair } from "@/lib/watchlist";
import { useHeaderHeight } from "@/hooks/useHeaderHeight";

interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export default function Dashboard() {
  useHeaderHeight();
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

  const filteredSignals = currencyFilter
    ? signals.filter(
        (s) => s.symbol.startsWith(currencyFilter) || s.symbol.slice(3).startsWith(currencyFilter),
      )
    : signals;

  const loadSignals = async () => {
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
    } catch (err) {
      console.error("Scanner fetch failed:", err);
      setSignals([]);
      setFetchError(err instanceof Error ? err.message : "Failed to load scanner data");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSignals();
    const interval = setInterval(loadSignals, 30000);
    return () => clearInterval(interval);
  }, [minScore, customPairs]);

  useEffect(() => {
    if (!selected) { setCandles([]); setBacktest(null); return; }
    fetchCandles(selected.symbol, selected.timeframe).then(setCandles).catch(() => setCandles([]));
    fetchBacktest(selected.symbol, selected.timeframe).then(setBacktest).catch(() => setBacktest(null));
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

  return (
    <div className="app-shell">
      <header className="header">
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
            onRemove={(sym) => setCustomPairs((prev) => removeCustomPair(sym, prev))}
          />
          <div className="header-controls">
            <div className="live-pill">
              <span className="live-dot" />
              Live
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
        <section className="stats-bar">
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
        </section>

        {filteredSignals.length > 0 && (
          <section className="panel heatmap-section">
            <div className="panel-header">
              <h2>Market heatmap</h2>
              <span className="panel-hint">{filteredSignals.length} pairs · click to inspect</span>
            </div>
            <Heatmap
              signals={filteredSignals}
              selectedSymbol={selected?.symbol}
              onSelect={setSelected}
            />
          </section>
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
          <section className="signals-section">
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
                      : `No setups above ${minScore} points right now.`}
                  </p>
                  <span>
                    {currencyFilter
                      ? "Clear the calendar filter or lower the minimum score."
                      : "Try lowering the minimum score filter."}
                  </span>
                </div>
              ) : (
                filteredSignals.map((signal) => (
                  <SignalCard
                    key={`${signal.symbol}-${signal.timeframe}`}
                    signal={signal}
                    selected={selected?.symbol === signal.symbol}
                    onSelect={setSelected}
                  />
                ))
              )}
            </div>
          </section>

          <aside className="side-panel">
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
          </aside>
        </div>
      </main>

      {selected && (
        <div className="detail-sheet" role="dialog" aria-label="Signal details">
          <DetailPanel
            signal={selected}
            candles={candles}
            backtest={backtest}
            onClose={() => setSelected(null)}
          />
        </div>
      )}
    </div>
  );
}
