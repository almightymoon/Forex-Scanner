"use client";

import type { CSSProperties } from "react";
import type { BacktestResult, HistoricalEvidence, ScannerSignal } from "@/lib/api";

const RATING_COLORS: Record<string, string> = {
  elite: "#34d399",
  strong: "#60a5fa",
  good: "#a78bfa",
  moderate: "#fbbf24",
  ignore: "#64748b",
};

interface CategoryRow {
  label: string;
  score: number;
  max_score: number;
}

interface ExplainabilityDashboardProps {
  signal: ScannerSignal;
  backtest: BacktestResult | null;
}

export function ExplainabilityDashboard({ signal, backtest }: ExplainabilityDashboardProps) {
  const color = RATING_COLORS[signal.rating] || "#64748b";
  const confidencePct = signal.explainability?.confidence_pct
    ?? Math.round((signal.confidence ?? signal.score / 100) * 100);

  const categories: CategoryRow[] =
    signal.explainability?.categories
    ?? signal.engine_outputs?.map((o) => ({
      label: o.name,
      score: o.score,
      max_score: o.max_score,
    }))
    ?? buildFallbackCategories(signal);

  const patterns = signal.explainability?.detected_patterns ?? signal.detected_patterns ?? [];
  const deltas = signal.explainability?.score_deltas ?? signal.score_deltas ?? [];
  const warnings = signal.warnings ?? [];

  return (
    <div className="explain-dashboard">
      <div className="explain-hero">
        <div className="explain-hero-left">
          <span className={`detail-dir ${signal.direction}`}>{signal.direction.toUpperCase()}</span>
          <div className="explain-confidence">
            <span className="explain-confidence-label">Confidence</span>
            <span className="explain-confidence-value" style={{ color }}>{confidencePct}</span>
          </div>
        </div>
        <div className="explain-hero-score">
          <span className="big-score" style={{ color }}>{signal.score}</span>
          <span className="score-meta">/ 100</span>
        </div>
      </div>

      {(signal.session || signal.trade_type) && (
        <p className="explain-session">
          {signal.session && <>Session: <strong>{formatSession(signal.session)}</strong></>}
          {signal.trade_type && <> · {signal.trade_type}</>}
          {signal.expected_duration && <> · ~{signal.expected_duration}</>}
        </p>
      )}

      <section className="explain-section">
        <h3>Score breakdown</h3>
        <div className="explain-categories">
          {categories.map((cat) => (
            <CategoryBar key={cat.label} category={cat} color={color} />
          ))}
        </div>
      </section>

      {patterns.length > 0 && (
        <section className="explain-section">
          <h3>Detected</h3>
          <ul className="explain-detected">
            {patterns.map((p) => (
              <li key={p.id ?? p.label}>
                <span className="check-icon" aria-hidden>✓</span>
                {p.label}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="explain-section">
        <h3>Historical performance</h3>
        <HistoricalStats
          backtest={backtest}
          evidence={signal.historical_evidence ?? signal.explainability?.historical}
        />
      </section>

      {deltas.length > 0 && (
        <section className="explain-section">
          <h3>Why this score changed</h3>
          <ul className="explain-deltas">
            {deltas.map((d, i) => (
              <li key={i} className={d.delta > 0 ? "delta-pos" : "delta-neg"}>
                <span className="delta-sign">{d.sign ?? (d.delta > 0 ? "+" : "−")}</span>
                <span className="delta-text">{d.text}</span>
                <span className="delta-pts">({d.delta > 0 ? "+" : ""}{d.delta})</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {warnings.length > 0 && (
        <section className="explain-section">
          <h3>Warnings</h3>
          <ul className="explain-warnings">
            {warnings.map((w, i) => (
              <li key={i}>• {w}</li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

function CategoryBar({ category, color }: { category: CategoryRow; color: string }) {
  const pct = category.max_score > 0 ? (category.score / category.max_score) * 100 : 0;
  return (
    <div className="explain-cat-row">
      <span className="explain-cat-label">{category.label}</span>
      <div className="explain-cat-bar">
        <div
          className="explain-cat-fill"
          style={{ width: `${pct}%`, background: color } as CSSProperties}
        />
      </div>
      <span className="explain-cat-value">
        {category.score} <span className="explain-cat-max">/ {category.max_score}</span>
      </span>
    </div>
  );
}

function HistoricalStats({
  backtest,
  evidence,
}: {
  backtest: BacktestResult | null;
  evidence?: HistoricalEvidence | null;
}) {
  if (evidence && evidence.sample_size > 0) {
    const winClass = evidence.win_rate >= 60 ? "win-good" : evidence.win_rate >= 50 ? "win-ok" : "win-low";
    const hours = evidence.avg_duration_hours ?? evidence.avg_duration_bars;
    return (
      <>
        <p className="explain-hist-searching">
          {evidence.sample_size} similar setups found in history
        </p>
        <div className="explain-hist-grid">
          <div className="explain-hist-stat">
            <span className="explain-hist-label">Win rate</span>
            <span className={`explain-hist-value ${winClass}`}>{evidence.win_rate}%</span>
          </div>
          <div className="explain-hist-stat">
            <span className="explain-hist-label">Average R:R</span>
            <span className="explain-hist-value">{evidence.avg_rr}</span>
          </div>
          <div className="explain-hist-stat">
            <span className="explain-hist-label">Avg duration</span>
            <span className="explain-hist-value">{hours}h</span>
          </div>
        </div>
        {(evidence.best_session || evidence.worst_session) && (
          <p className="explain-hist-sessions">
            {evidence.best_session && <>Best session: <strong>{formatSession(evidence.best_session)}</strong></>}
            {evidence.worst_session && <> · Weakest: <strong>{formatSession(evidence.worst_session)}</strong></>}
          </p>
        )}
      </>
    );
  }

  if (!backtest || backtest.total_trades === 0) {
    return (
      <p className="explain-hist-empty">
        Walk-forward backtest running — historical stats appear once enough similar setups are found.
      </p>
    );
  }

  const winClass = backtest.win_rate >= 60 ? "win-good" : backtest.win_rate >= 50 ? "win-ok" : "win-low";

  return (
    <div className="explain-hist-grid">
      <div className="explain-hist-stat">
        <span className="explain-hist-label">Win rate</span>
        <span className={`explain-hist-value ${winClass}`}>{backtest.win_rate}%</span>
      </div>
      <div className="explain-hist-stat">
        <span className="explain-hist-label">Average R:R</span>
        <span className="explain-hist-value">{backtest.avg_rr}</span>
      </div>
      <div className="explain-hist-stat">
        <span className="explain-hist-label">Sample size</span>
        <span className="explain-hist-value">{backtest.total_trades} setups</span>
      </div>
    </div>
  );
}

function formatSession(session: string): string {
  return session.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function buildFallbackCategories(signal: ScannerSignal): CategoryRow[] {
  const bd = signal.score_breakdown;
  if (!bd) return [];
  return [
    { label: "Trend", score: bd.trend, max_score: 20 },
    { label: "Momentum", score: bd.momentum, max_score: 15 },
    { label: "Market Structure", score: bd.smc + (bd.mtf_alignment ?? 0), max_score: 30 },
    { label: "Risk", score: bd.support_resistance + bd.volume_volatility, max_score: 15 },
    { label: "News", score: bd.news_risk, max_score: 10 },
  ];
}
