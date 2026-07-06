"use client";

import { useEffect, useRef, useState } from "react";
import {
  createChart,
  ColorType,
  IChartApi,
  IPriceLine,
  ISeriesApi,
  CandlestickData,
  Time,
} from "lightweight-charts";

import { fetchLivePrices } from "@/lib/api";
import { formatPrice } from "@/lib/format";
import { getSymbolName, getSymbolShort } from "@/lib/symbols";

interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

interface PriceChartProps {
  candles: Candle[];
  symbol: string;
  timeframe: string;
  stopLoss?: number;
  takeProfit?: number;
  tall?: boolean;
  chartHeight?: number;
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

function formatTimeframe(tf: string): string {
  return TF_LABELS[tf] || tf;
}

export function PriceChart({
  candles,
  symbol,
  timeframe,
  stopLoss,
  takeProfit,
  tall,
  chartHeight,
}: PriceChartProps) {
  const height = chartHeight ?? (tall ? 420 : 260);
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const liveLineRef = useRef<IPriceLine | null>(null);
  const [livePrice, setLivePrice] = useState<number | null>(null);

  useEffect(() => {
    let active = true;

    const loadLive = async () => {
      try {
        const prices = await fetchLivePrices();
        if (active && prices[symbol] != null) {
          setLivePrice(prices[symbol]);
        }
      } catch {
        // keep last known price
      }
    };

    loadLive();
    const interval = setInterval(loadLive, 15_000);
    return () => {
      active = false;
      clearInterval(interval);
    };
  }, [symbol]);

  useEffect(() => {
    if (!containerRef.current || candles.length === 0) return;

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#94a3b8",
        fontFamily: "Inter, sans-serif",
      },
      grid: {
        vertLines: { color: "rgba(255,255,255,0.04)" },
        horzLines: { color: "rgba(255,255,255,0.04)" },
      },
      width: containerRef.current.clientWidth,
      height,
      timeScale: { borderColor: "rgba(255,255,255,0.08)" },
      rightPriceScale: { borderColor: "rgba(255,255,255,0.08)" },
    });

    const series = chart.addCandlestickSeries({
      upColor: "#34d399",
      downColor: "#f87171",
      borderUpColor: "#34d399",
      borderDownColor: "#f87171",
      wickUpColor: "#34d399",
      wickDownColor: "#f87171",
    });

    const data: CandlestickData<Time>[] = candles.map((c) => ({
      time: (new Date(c.timestamp).getTime() / 1000) as Time,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
    }));

    series.setData(data);

    if (stopLoss) {
      series.createPriceLine({
        price: stopLoss,
        color: "#ef4444",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "SL",
      });
    }
    if (takeProfit) {
      series.createPriceLine({
        price: takeProfit,
        color: "#10b981",
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "TP1",
      });
    }

    chart.timeScale().fitContent();
    chartRef.current = chart;
    seriesRef.current = series;
    liveLineRef.current = null;

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      liveLineRef.current = null;
    };
  }, [candles, stopLoss, takeProfit, height]);

  useEffect(() => {
    if (livePrice == null || !seriesRef.current || candles.length === 0) return;

    const last = candles[candles.length - 1];
    const time = (new Date(last.timestamp).getTime() / 1000) as Time;

    seriesRef.current.update({
      time,
      open: last.open,
      high: Math.max(last.high, livePrice),
      low: Math.min(last.low, livePrice),
      close: livePrice,
    });

    if (!liveLineRef.current) {
      liveLineRef.current = seriesRef.current.createPriceLine({
        price: livePrice,
        color: "#818cf8",
        lineWidth: 2,
        lineStyle: 0,
        axisLabelVisible: true,
        title: "Live",
      });
    } else {
      liveLineRef.current.applyOptions({ price: livePrice });
    }
  }, [livePrice, candles]);

  if (candles.length === 0) {
    return <div className="chart-loading">Loading chart…</div>;
  }

  const displayPrice = livePrice ?? candles[candles.length - 1]?.close;

  return (
    <div className="chart-wrapper">
      <div className="chart-label">
        <div className="chart-label-left">
          <span>{getSymbolName(symbol)}</span>
          <span className="chart-tf-badge">{formatTimeframe(timeframe)}</span>
        </div>
        <div className="chart-label-right">
          <span className="chart-label-code">{getSymbolShort(symbol)}</span>
          {displayPrice != null && (
            <span className="chart-live-price">
              <span className="live-dot-sm" aria-hidden />
              {formatPrice(symbol, displayPrice)}
            </span>
          )}
        </div>
      </div>
      <div ref={containerRef} className="chart-container" style={{ height }} />
    </div>
  );
}
