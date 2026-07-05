"use client";

import type { BacktestResult } from "@/lib/api";

interface Props {
  backtest: BacktestResult | null;
}

export function BacktestPanel({ backtest }: Props) {
  if (!backtest || backtest.total_trades === 0) {
    return (
      <div className="detail-section">
        <h3>Historical performance</h3>
        <p className="backtest-empty">Not enough data for backtest yet.</p>
      </div>
    );
  }

  const winClass = backtest.win_rate >= 60 ? "win-good" : backtest.win_rate >= 50 ? "win-ok" : "win-low";

  return (
    <div className="detail-section">
      <h3>Historical performance</h3>
      <div className="backtest-grid">
        <div className="bt-stat">
          <span className={`bt-value ${winClass}`}>{backtest.win_rate}%</span>
          <span className="bt-label">Win rate</span>
        </div>
        <div className="bt-stat">
          <span className="bt-value">{backtest.total_trades}</span>
          <span className="bt-label">Trades</span>
        </div>
        <div className="bt-stat">
          <span className="bt-value">{backtest.wins}W / {backtest.losses}L</span>
          <span className="bt-label">Record</span>
        </div>
        <div className="bt-stat">
          <span className="bt-value">{backtest.avg_rr}:1</span>
          <span className="bt-label">Avg R:R</span>
        </div>
        <div className="bt-stat">
          <span className="bt-value">{backtest.max_drawdown}</span>
          <span className="bt-label">Max DD (pips)</span>
        </div>
        <div className="bt-stat">
          <span className="bt-value">{backtest.avg_score}</span>
          <span className="bt-label">Avg Score</span>
        </div>
      </div>
      <p className="backtest-note">
        Walk-forward test on similar setups (score ≥70).
      </p>
    </div>
  );
}
