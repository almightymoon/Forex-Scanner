"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { ScannerSignal, BacktestResult } from "@/lib/api";
import { fetchSignal, fetchCandles, fetchBacktest } from "@/lib/api";
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
  /** Keep parent selection in sync when TF reload returns a new signal. */
  onSignalChange?: (signal: ScannerSignal) => void;
}

/** Interactive timeframes for detail analysis. */
const DETAIL_TIMEFRAMES = ["M15", "M30", "H1", "H4", "D1"] as const;

const TF_LABELS: Record<string, string> = {
  M1: "1m",
  M5: "5m",
  M15: "15m",
  M30: "30m",
  H1: "1H",
  H4: "4H",
  D1: "D1",
};

const RATING_COLORS: Record<string, string> = {
  elite: "#34d399",
  strong: "#60a5fa",
  good: "#a78bfa",
  moderate: "#fbbf24",
  ignore: "#64748b",
};

export function DetailPanel({
  signal: initialSignal,
  candles: initialCandles,
  backtest: initialBacktest,
  onClose,
  onSignalChange,
}: DetailPanelProps) {
  const alertTimeframe = useRef(initialSignal.timeframe);
  const requestId = useRef(0);

  const [signal, setSignal] = useState(initialSignal);
  const [candles, setCandles] = useState(initialCandles);
  const [backtest, setBacktest] = useState(initialBacktest);
  const [timeframe, setTimeframe] = useState(initialSignal.timeframe);
  const [loadingTf, setLoadingTf] = useState(false);
  const [tfError, setTfError] = useState<string | null>(null);

  // New symbol from scanner — reset local analysis state.
  useEffect(() => {
    alertTimeframe.current = initialSignal.timeframe;
    setSignal(initialSignal);
    setCandles(initialCandles);
    setBacktest(initialBacktest);
    setTimeframe(initialSignal.timeframe);
    setTfError(null);
    setLoadingTf(false);
    requestId.current += 1;
  }, [initialSignal.symbol]);

  // Parent finished loading candles/backtest for the alert TF.
  useEffect(() => {
    if (
      initialSignal.symbol === signal.symbol &&
      initialSignal.timeframe === timeframe &&
      !loadingTf
    ) {
      setSignal(initialSignal);
      setCandles(initialCandles);
      setBacktest(initialBacktest);
    }
  }, [initialSignal, initialCandles, initialBacktest, signal.symbol, timeframe, loadingTf]);

  const changeTimeframe = useCallback(
    async (tf: string) => {
      if (tf === timeframe || loadingTf) return;
      const id = ++requestId.current;
      setLoadingTf(true);
      setTfError(null);
      setTimeframe(tf);

      try {
        const [nextSignal, nextCandles, nextBacktest] = await Promise.all([
          fetchSignal(signal.symbol, tf),
          fetchCandles(signal.symbol, tf),
          fetchBacktest(signal.symbol, tf),
        ]);

        if (id !== requestId.current) return;

        const { backtest: embedded, ...rest } = nextSignal;
        const resolved = rest as ScannerSignal;
        const resolvedBacktest = nextBacktest ?? embedded ?? null;

        setSignal(resolved);
        setCandles(nextCandles);
        setBacktest(resolvedBacktest);
        onSignalChange?.(resolved);
      } catch (err) {
        if (id !== requestId.current) return;
        setTfError(err instanceof Error ? err.message : `Failed to load ${tf}`);
        setTimeframe(signal.timeframe);
      } finally {
        if (id === requestId.current) setLoadingTf(false);
      }
    },
    [timeframe, loadingTf, signal.symbol, signal.timeframe, onSignalChange],
  );

  const scoreColor = RATING_COLORS[signal.rating] || "#64748b";
  const confidencePct =
    signal.explainability?.confidence_pct
    ?? Math.round((signal.confidence ?? signal.score / 100) * 100);
  const alertTf = alertTimeframe.current;

  return (
    <div className={`detail-panel detail-panel-full${loadingTf ? " is-tf-loading" : ""}`}>
      <header className="detail-top-bar">
        <button type="button" className="detail-back-btn" onClick={onClose}>
          ← Back to scanner
        </button>

        <div className="detail-top-info">
          <h2>{getSymbolName(signal.symbol)}</h2>
          <p className="detail-tf">
            {getSymbolShort(signal.symbol)} · {getCategoryLabel(getSymbol(signal.symbol).category)}
            {alertTf ? (
              <>
                {" "}
                · Alert on <strong>{TF_LABELS[alertTf] || alertTf}</strong>
              </>
            ) : null}
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

      <div className="detail-tf-bar" role="group" aria-label="Analysis timeframe">
        <span className="detail-tf-label">Timeframe</span>
        <div className="detail-tf-pills">
          {DETAIL_TIMEFRAMES.map((tf) => {
            const active = timeframe === tf;
            const isAlert = alertTf === tf;
            return (
              <button
                key={tf}
                type="button"
                className={`detail-tf-pill${active ? " active" : ""}${isAlert ? " alert-tf" : ""}`}
                aria-pressed={active}
                disabled={loadingTf}
                onClick={() => changeTimeframe(tf)}
                title={isAlert ? `${tf} — scanner alert timeframe` : `Analyze on ${tf}`}
              >
                {TF_LABELS[tf] || tf}
                {isAlert ? <span className="detail-tf-alert-dot" aria-hidden /> : null}
              </button>
            );
          })}
        </div>
        {loadingTf ? (
          <span className="detail-tf-status">
            <span className="btn-spinner" /> Scanning {TF_LABELS[timeframe] || timeframe}…
          </span>
        ) : null}
        {tfError && !loadingTf ? (
          <span className="detail-tf-status detail-tf-error">{tfError}</span>
        ) : null}
      </div>

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
            <strong>
              {formatPriceRange(signal.symbol, signal.entry_zone_low, signal.entry_zone_high!)}
            </strong>
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
