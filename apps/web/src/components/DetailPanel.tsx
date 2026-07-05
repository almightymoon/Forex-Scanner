"use client";

import { useEffect, useState } from "react";
import type { ScannerSignal, BacktestResult } from "@/lib/api";
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

export function DetailPanel({ signal, candles, backtest, onClose }: DetailPanelProps) {
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => {
    setFullscreen(false);
  }, [signal.symbol]);

  useEffect(() => {
    if (!fullscreen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setFullscreen(false);
    };
    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", onKey);
    };
  }, [fullscreen]);

  const handleClose = () => {
    setFullscreen(false);
    onClose();
  };

  const content = (
    <>
      <div className="detail-toolbar">
        <button
          type="button"
          className="panel-action-btn"
          onClick={() => setFullscreen((f) => !f)}
          aria-label={fullscreen ? "Exit fullscreen" : "Fullscreen"}
          title={fullscreen ? "Exit fullscreen (Esc)" : "Fullscreen"}
        >
          {fullscreen ? "⤡" : "⤢"}
        </button>
        <button type="button" className="panel-action-btn close-btn" onClick={handleClose} aria-label="Close">
          ×
        </button>
      </div>

      <div className="detail-hero detail-hero-compact">
        <div>
          <h2>{getSymbolName(signal.symbol)}</h2>
          <span className="detail-tf">
            {getSymbolShort(signal.symbol)} · {getCategoryLabel(getSymbol(signal.symbol).category)} · {signal.timeframe}
          </span>
        </div>
        <span className={`rating-pill-inline ${signal.rating}`}>{signal.rating}</span>
      </div>

      <ExplainabilityDashboard signal={signal} backtest={backtest} />

      <PriceChart
        candles={candles}
        symbol={signal.symbol}
        stopLoss={signal.stop_loss}
        takeProfit={signal.take_profit_1}
        tall={fullscreen}
      />

      {signal.ai_explanation && (
        <div className="detail-section">
          <h3>AI summary</h3>
          <div className="explanation">{signal.ai_explanation}</div>
        </div>
      )}

      {signal.entry_zone_low && (
        <div className="detail-section">
          <h3>Trade levels</h3>
          <div className="levels-grid">
            <div className="level-item"><span>Entry</span><strong>{signal.entry_zone_low} – {signal.entry_zone_high}</strong></div>
            <div className="level-item sl"><span>Stop loss</span><strong>{signal.stop_loss}</strong></div>
            <div className="level-item tp"><span>TP 1</span><strong>{signal.take_profit_1}</strong></div>
            <div className="level-item tp"><span>TP 2</span><strong>{signal.take_profit_2}</strong></div>
            <div className="level-item"><span>R:R</span><strong>{signal.risk_reward}:1</strong></div>
          </div>
        </div>
      )}
    </>
  );

  if (fullscreen) {
    return (
      <div className="detail-fullscreen-overlay" onClick={() => setFullscreen(false)}>
        <div className="detail-panel detail-panel-fullscreen" onClick={(e) => e.stopPropagation()}>
          {content}
        </div>
      </div>
    );
  }

  return <div className="detail-panel">{content}</div>;
}
