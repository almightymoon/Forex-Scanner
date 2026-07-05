"use client";

import { useState } from "react";
import type { CSSProperties } from "react";
import type { ScannerSignal, ScoreBreakdown } from "@/lib/api";

const RATING_COLORS: Record<string, string> = {
  elite: "#34d399",
  strong: "#60a5fa",
  good: "#a78bfa",
  moderate: "#fbbf24",
  ignore: "#64748b",
};

interface ScoreGroup {
  key: string;
  label: string;
  max: number;
  fields: (keyof ScoreBreakdown)[];
}

const SCORE_GROUPS: ScoreGroup[] = [
  { key: "trend", label: "Trend", max: 20, fields: ["trend"] },
  { key: "momentum", label: "Momentum", max: 15, fields: ["momentum"] },
  { key: "smc", label: "SMC", max: 25, fields: ["smc"] },
  { key: "risk", label: "Risk", max: 20, fields: ["support_resistance", "volume_volatility"] },
  { key: "news", label: "News", max: 20, fields: ["mtf_alignment", "news_risk"] },
];

interface ScoreBreakdownPanelProps {
  signal: ScannerSignal;
  compact?: boolean;
}

export function ScoreBreakdownPanel({ signal, compact = false }: ScoreBreakdownPanelProps) {
  const [expanded, setExpanded] = useState<string | null>(null);
  const color = RATING_COLORS[signal.rating] || "#64748b";
  const bd = signal.score_breakdown;

  const toggle = (key: string) => {
    setExpanded((prev) => (prev === key ? null : key));
  };

  return (
    <div className={`score-breakdown-panel${compact ? " compact" : ""}`}>
      <div className="breakdown-header">
        <span className="breakdown-total" style={{ color }}>{signal.score}</span>
        <span className="breakdown-total-meta">/ 100 confidence</span>
      </div>

      <div className="score-breakdown">
        {SCORE_GROUPS.map((group) => {
          const value = group.fields.reduce((sum, f) => sum + (bd[f] || 0), 0);
          const pct = (value / group.max) * 100;
          const reasons = getReasonsForGroup(group.key, signal);
          const isOpen = expanded === group.key;

          return (
            <div key={group.key} className={`breakdown-row${isOpen ? " open" : ""}`}>
              <button
                type="button"
                className="breakdown-trigger"
                onClick={() => toggle(group.key)}
                aria-expanded={isOpen}
              >
                <span className="breakdown-label">{group.label}</span>
                <div className="breakdown-bar">
                  <div
                    className="breakdown-fill"
                    style={{ width: `${pct}%`, background: color } as CSSProperties}
                  />
                </div>
                <span className="breakdown-value">{value}</span>
              </button>
              {isOpen && reasons.length > 0 && (
                <ul className="breakdown-reasons">
                  {reasons.map((r, i) => (
                    <li key={i}>{r}</li>
                  ))}
                </ul>
              )}
              {isOpen && reasons.length === 0 && (
                <p className="breakdown-empty">No detailed factors for this category.</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function getReasonsForGroup(groupKey: string, signal: ScannerSignal): string[] {
  const tech = signal.technical_reasons;

  switch (groupKey) {
    case "trend":
      return tech.filter((r) => /EMA|ADX|higher|VWAP/i.test(r));
    case "momentum":
      return tech.filter((r) => /MACD|RSI|ATR/i.test(r));
    case "smc":
      return signal.smc_reasons;
    case "risk":
      return tech.filter((r) => /support|resistance|volume|spread|level|pivot/i.test(r));
    case "news": {
      const fromTech = tech.filter((r) => /MTF|align|news|impact/i.test(r));
      const fromAi = (signal.ai_explanation || "")
        .split("\n")
        .filter((l) => /timeframe|news|impact|align/i.test(l));
      return [...fromTech, ...fromAi];
    }
    default:
      return [];
  }
}
