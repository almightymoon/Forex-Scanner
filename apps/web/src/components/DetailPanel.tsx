"use client";

import { useEffect, useState } from "react";
import type { ScannerSignal, BacktestResult } from "@/lib/api";
import { getSymbolName, getSymbolShort, getSymbol, getCategoryLabel } from "@/lib/symbols";
import { PriceChart } from "./PriceChart";
import { BacktestPanel } from "./BacktestPanel";
import { ScoreBreakdownPanel } from "./ScoreBreakdownPanel";

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

      <div className="detail-hero">
        <div>
          <span className={`detail-dir ${signal.direction}`}>{signal.direction}</span>
          <h2>{getSymbolName(signal.symbol)}</h2>
          <span className="detail-tf">
            {getSymbolShort(signal.symbol)} · {getCategoryLabel(getSymbol(signal.symbol).category)} · {signal.timeframe}
          </span>
        </div>
        <div className="detail-score-block">
          <span className="big-score">{signal.score}</span>
          <span className="score-meta">/ 100 · {signal.rating}</span>
        </div>
      </div>

      <div className="detail-section">
        <h3>Score breakdown</h3>
        <p className="section-hint">Click a category to see why points were awarded</p>
        <ScoreBreakdownPanel signal={signal} />
      </div>

      <PriceChart
        candles={candles}
        symbol={signal.symbol}
        stopLoss={signal.stop_loss}
        takeProfit={signal.take_profit_1}
        tall={fullscreen}
      />

      <div className="detail-section">
        <h3>AI analysis</h3>
        <div className="explanation">{signal.ai_explanation}</div>
      </div>

      <BacktestPanel backtest={backtest} />

      {signal.technical_reasons.length > 0 && (
        <div className="detail-section">
          <h3>Technical</h3>
          <ul className="reason-list">
            {signal.technical_reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {signal.smc_reasons.length > 0 && (
        <div className="detail-section">
          <h3>Smart money</h3>
          <ul className="reason-list">
            {signal.smc_reasons.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
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
