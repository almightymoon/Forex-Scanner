"use client";

import { useEffect, useRef } from "react";
import { createChart, ColorType, IChartApi, ISeriesApi, CandlestickData, Time } from "lightweight-charts";

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
  stopLoss?: number;
  takeProfit?: number;
  tall?: boolean;
}

export function PriceChart({ candles, symbol, stopLoss, takeProfit, tall }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

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
      height: tall ? 420 : 260,
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

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
    };
  }, [candles, stopLoss, takeProfit, tall]);

  if (candles.length === 0) {
    return <div className="chart-loading">Loading chart...</div>;
  }

  return (
    <div className="chart-wrapper">
      <div className="chart-label">
        {getSymbolName(symbol)}
        <span className="chart-label-code">{getSymbolShort(symbol)}</span>
      </div>
      <div ref={containerRef} className="chart-container" />
    </div>
  );
}
