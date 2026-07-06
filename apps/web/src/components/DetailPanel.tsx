"use client";

import type { ScannerSignal, BacktestResult } from "@/lib/api";
import { formatPrice, formatPriceRange, formatSession } from "@/lib/format";
import { getSymbolName, getSymbolShort, getSymbol, getCategoryLabel } from "@/lib/symbols";
import { PriceChart } from "./PriceChart";
import { ExplainabilityDashboard } from "./ExplainabilityDashboard";

interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface DetailPanelProps {
  signal: ScannerSignal;
  candles: Candle[];
  backtest: BacktestResult | null;
  onClose: () => void;
}

const TF_LABELS: Record<string, string> = {
  M1: "1 Min",
  M5: "5 Min",
  M15: "15 Min",
  M30: "30 Min",
  H1: "1 Hour",
  H4: "4 Hour",
  D1: "Daily",
};

const RATING_COLORS: Record<string, string> = {
  elite: "#34d399",
  strong: "#60a5fa",
  good: "#a78bfa",
  moderate: "#fbbf24",
  ignore: "#64748b",
};

export function DetailPanel({ signal, candles, backtest, onClose }: DetailPanelProps) {
  const scoreColor = RATING_COLORS[signal.rating] || "#64748b";
  const confidencePct =
    signal.explainability?.confidence_pct
    ?? Math.round((signal.confidence ?? signal.score / 100) * 100);

  return (
    <div className="detail-panel detail-panel-full">
      <header className="detail-top-bar">
        <button type="button" className="detail-back-btn" onClick={onClose}>
          ← Back to scanner
        </button>

        <div className="detail-top-info">
          <h2>{getSymbolName(signal.symbol)}</h2>
          <p className="detail-tf">
            {getSymbolShort(signal.symbol)} · {getCategoryLabel(getSymbol(signal.symbol).category)} ·{" "}
            <strong>{TF_LABELS[signal.timeframe] || signal.timeframe}</strong>
          </p>
        </div>

        <div className="detail-top-badges">
          <span className={`detail-dir ${signal.direction}`}>{signal.direction.toUpperCase()}</span>
          <span className="detail-score-chip" style={{ color: scoreColor }}>
            {signal.score}<span>/100</span>
          </span>
          <span className={`rating-pill-inline ${signal.rating}`}>{signal.rating}</span>
        </div>
      </header>

      <div className="detail-kpi-row">
        <div className="detail-kpi">
          <span className="detail-kpi-label">Confidence</span>
          <span className="detail-kpi-value" style={{ color: scoreColor }}>{confidencePct}</span>
        </div>
        <div className="detail-kpi">
          <span className="detail-kpi-label">Score</span>
          <span className="detail-kpi-value" style={{ color: scoreColor }}>{signal.score}</span>
        </div>
        {signal.risk_reward != null && (
          <div className="detail-kpi">
            <span className="detail-kpi-label">Risk : Reward</span>
            <span className="detail-kpi-value">{signal.risk_reward}:1</span>
          </div>
        )}
        <div className="detail-kpi">
          <span className="detail-kpi-label">Session</span>
          <span className="detail-kpi-value detail-kpi-value-sm">
            {signal.session ? formatSession(signal.session) : "—"}
          </span>
        </div>
      </div>

      <div className="detail-chart-section">
        <PriceChart
          candles={candles}
          symbol={signal.symbol}
          timeframe={signal.timeframe}
          stopLoss={signal.stop_loss}
          takeProfit={signal.take_profit_1}
          chartHeight={400}
        />
      </div>

      {signal.entry_zone_low != null && (
        <div className="detail-levels-strip">
          <div className="level-pill">
            <span>Entry</span>
            <strong>{formatPriceRange(signal.symbol, signal.entry_zone_low, signal.entry_zone_high!)}</strong>
          </div>
          <div className="level-pill sl">
            <span>Stop loss</span>
            <strong>{formatPrice(signal.symbol, signal.stop_loss!)}</strong>
          </div>
          <div className="level-pill tp">
            <span>TP 1</span>
            <strong>{formatPrice(signal.symbol, signal.take_profit_1!)}</strong>
          </div>
          {signal.take_profit_2 != null && (
            <div className="level-pill tp">
              <span>TP 2</span>
              <strong>{formatPrice(signal.symbol, signal.take_profit_2)}</strong>
            </div>
          )}
        </div>
      )}

      <ExplainabilityDashboard signal={signal} backtest={backtest} layout="bento" />

      {signal.ai_explanation && (
        <section className="detail-ai-block">
          <h3>AI summary</h3>
          <div className="explanation">{signal.ai_explanation}</div>
        </section>
      )}
    </div>
  );
}
