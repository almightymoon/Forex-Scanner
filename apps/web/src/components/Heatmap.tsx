"use client";

import type { ScannerSignal } from "@/lib/api";
import { getSymbol } from "@/lib/symbols";

interface Props {
  signals: ScannerSignal[];
  selectedSymbol?: string;
  onSelect?: (signal: ScannerSignal) => void;
}

function scoreClass(score: number): string {
  if (score >= 90) return "hm-elite";
  if (score >= 80) return "hm-strong";
  if (score >= 70) return "hm-good";
  return "hm-moderate";
}

export function Heatmap({ signals, selectedSymbol, onSelect }: Props) {
  const sorted = [...signals].sort((a, b) => b.score - a.score);

  return (
    <div className="heatmap-scroll">
      <div className="heatmap-grid">
        {sorted.map((s) => {
          const info = getSymbol(s.symbol);
          const isMetal = info.category === "metal";
          const selected = selectedSymbol === s.symbol;
          return (
            <button
              key={s.symbol}
              type="button"
              className={[
                "heatmap-cell",
                isMetal ? "heatmap-gold" : scoreClass(s.score),
                selected ? "heatmap-selected" : "",
              ].filter(Boolean).join(" ")}
              onClick={() => onSelect?.(s)}
              title={`${info.name} (${info.short}) — ${s.score}/100 ${s.direction}`}
            >
              <span className="hm-symbol">{info.short}</span>
              <span className="hm-name">{info.name.split(" / ")[0]}</span>
              <span className="hm-score">{s.score}</span>
              <span className={`hm-dir ${s.direction}`}>
                {s.direction === "buy" ? "▲" : s.direction === "sell" ? "▼" : "–"}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
