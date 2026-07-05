"use client";

import { useEffect, useState } from "react";
import { SignalCard } from "@/components/SignalCard";
import { EconomicCalendar } from "@/components/EconomicCalendar";
import { Heatmap } from "@/components/Heatmap";
import type { ScannerSignal, BacktestResult } from "@/lib/api";
import { fetchLiveScanner, fetchStats, fetchCalendar, fetchCandles, fetchBacktest } from "@/lib/api";
import { DetailPanel } from "@/components/DetailPanel";
import { PairSearch } from "@/components/PairSearch";
import { loadCustomPairs, addCustomPair, removeCustomPair } from "@/lib/watchlist";

interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

export default function Dashboard() {
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

  const loadSignals = async () => {
    setLoading(true);
    try {
      const [data, s, cal] = await Promise.all([
        fetchLiveScanner(minScore, customPairs),
        fetchStats(),
        fetchCalendar(),
      ]);
      setSignals(data);
      setStats(s);
      setEvents(cal.events || []);
      setLastScan(new Date().toLocaleTimeString());
    } catch (err) {
      console.error("Scanner fetch failed:", err);
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

  const buyCount = signals.filter((s) => s.direction === "buy").length;
  const sellCount = signals.filter((s) => s.direction === "sell").length;
  const eliteCount = signals.filter((s) => s.rating === "elite").length;

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
      </header>

      <main className="dashboard">
        <section className="stats-bar">
          <div className="stat-card">
            <span className="stat-value accent">{signals.length}</span>
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

        {signals.length > 0 && (
          <section className="panel heatmap-section">
            <div className="panel-header">
              <h2>Market heatmap</h2>
              <span className="panel-hint">{signals.length} pairs · click to inspect</span>
            </div>
            <Heatmap
              signals={signals}
              selectedSymbol={selected?.symbol}
              onSelect={setSelected}
            />
          </section>
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
              ) : signals.length === 0 ? (
                <div className="state-message empty-state">
                  <p>No setups above {minScore} points right now.</p>
                  <span>Try lowering the minimum score filter.</span>
                </div>
              ) : (
                signals.map((signal) => (
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
            {selected ? (
              <DetailPanel
                signal={selected}
                candles={candles}
                backtest={backtest}
                onClose={() => setSelected(null)}
              />
            ) : (
              <div className="calendar-panel panel">
                <div className="panel-header">
                  <h2>Economic calendar</h2>
                  <span className="panel-hint">Upcoming events</span>
                </div>
                <EconomicCalendar events={events} />
              </div>
            )}
          </aside>
        </div>
      </main>
    </div>
  );
}
