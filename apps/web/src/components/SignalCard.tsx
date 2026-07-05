"use client";

import type { CSSProperties } from "react";
import type { ScannerSignal } from "@/lib/api";
import { getSymbol, getCategoryLabel } from "@/lib/symbols";

const RATING_COLORS: Record<string, string> = {
  elite: "#34d399",
  strong: "#60a5fa",
  good: "#a78bfa",
  moderate: "#fbbf24",
  ignore: "#64748b",
};

const BREAKDOWN_LABELS: Record<string, string> = {
  trend: "Trend",
  smc: "SMC",
  momentum: "Momentum",
  support_resistance: "S / R",
  volume_volatility: "Volume",
  mtf_alignment: "MTF",
  news_risk: "News",
};

interface SignalCardProps {
  signal: ScannerSignal;
  selected?: boolean;
  onSelect?: (signal: ScannerSignal) => void;
}

export function SignalCard({ signal, selected, onSelect }: SignalCardProps) {
  const ratingColor = RATING_COLORS[signal.rating] || "#64748b";
  const info = getSymbol(signal.symbol);
  const isGold = signal.symbol === "XAUUSD";
  const isMetal = info.category === "metal" || info.category === "energy";
  const isBuy = signal.direction === "buy";
  const isSell = signal.direction === "sell";

  return (
    <article
      className={[
        "signal-card",
        isMetal ? "signal-card-gold" : "",
        selected ? "signal-card-selected" : "",
      ].filter(Boolean).join(" ")}
      onClick={() => onSelect?.(signal)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === "Enter" && onSelect?.(signal)}
    >
      <div className="signal-card-top">
        <div className="signal-pair-block">
          <div className="signal-pair-row">
            {isGold && <span className="pair-icon gold-icon" aria-hidden>●</span>}
            <div className="pair-names">
              <span className="symbol">{info.name}</span>
              <span className="symbol-code">{info.short} · {getCategoryLabel(info.category)}</span>
            </div>
            <span className="timeframe-pill">{signal.timeframe}</span>
          </div>
          <div className="signal-badges">
            <span className={`dir-pill ${isBuy ? "dir-buy" : isSell ? "dir-sell" : "dir-neutral"}`}>
              {isBuy ? "↑ Buy" : isSell ? "↓ Sell" : "— Neutral"}
            </span>
            <span className="rating-pill" style={{ color: ratingColor, borderColor: `${ratingColor}40`, background: `${ratingColor}15` }}>
              {signal.rating}
            </span>
            <span className="risk-pill">{signal.risk_level} risk</span>
          </div>
        </div>

        <div className="score-ring" style={{ "--score-color": ratingColor } as CSSProperties}>
          <span className="score-value">{signal.score}</span>
          <span className="score-max">/100</span>
        </div>
      </div>

      <div className="score-breakdown">
        {Object.entries(signal.score_breakdown).map(([key, value]) => {
          const max = getMaxForCategory(key);
          const pct = (value / max) * 100;
          return (
            <div key={key} className="breakdown-item">
              <span className="breakdown-label">{BREAKDOWN_LABELS[key] || key}</span>
              <div className="breakdown-bar">
                <div className="breakdown-fill" style={{ width: `${pct}%`, background: ratingColor }} />
              </div>
              <span className="breakdown-value">{value}</span>
            </div>
          );
        })}
      </div>

      {signal.risk_reward && (
        <div className="signal-levels">
          <span className="level-chip"><em>R:R</em> {signal.risk_reward}</span>
          {signal.stop_loss && <span className="level-chip sl"><em>SL</em> {signal.stop_loss}</span>}
          {signal.take_profit_1 && <span className="level-chip tp"><em>TP</em> {signal.take_profit_1}</span>}
        </div>
      )}
    </article>
  );
}

function getMaxForCategory(key: string): number {
  const maxes: Record<string, number> = {
    trend: 20, smc: 25, momentum: 15, support_resistance: 10,
    volume_volatility: 10, mtf_alignment: 10, news_risk: 10,
  };
  return maxes[key] || 10;
}
