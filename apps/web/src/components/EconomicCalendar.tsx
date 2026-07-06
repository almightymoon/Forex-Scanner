"use client";

import { useState } from "react";

export interface EconomicEvent {
  currency: string;
  title: string;
  impact: string;
  event_time: string;
  forecast?: string;
  previous?: string;
  actual?: string;
}

interface Props {
  events: EconomicEvent[];
  activeCurrency?: string | null;
  onFilterCurrency?: (currency: string | null) => void;
}

const IMPACT_COLORS: Record<string, string> = {
  high: "#ef4444",
  medium: "#f59e0b",
  low: "#6b7280",
};

function formatEventTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function timeUntil(iso: string): string {
  const diffMs = new Date(iso).getTime() - Date.now();
  if (diffMs <= 0) return "Started / passed";
  const hours = Math.floor(diffMs / 3_600_000);
  const mins = Math.floor((diffMs % 3_600_000) / 60_000);
  if (hours >= 24) return `In ${Math.floor(hours / 24)}d ${hours % 24}h`;
  if (hours > 0) return `In ${hours}h ${mins}m`;
  return `In ${mins}m`;
}

export function EconomicCalendar({ events, activeCurrency, onFilterCurrency }: Props) {
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);

  if (events.length === 0) {
    return <div className="calendar-empty">No upcoming events</div>;
  }

  return (
    <div className="calendar-list">
      {events.slice(0, 8).map((event, index) => {
        const impactColor = IMPACT_COLORS[event.impact] || "#6b7280";
        const isOpen = selectedIndex === index;
        const isFiltered = activeCurrency === event.currency;

        return (
          <div
            key={`${event.title}-${event.event_time}-${index}`}
            className={`calendar-item${isOpen ? " calendar-item-open" : ""}${isFiltered ? " calendar-item-active" : ""}`}
          >
            <button
              type="button"
              className="calendar-item-trigger"
              onClick={() => setSelectedIndex(isOpen ? null : index)}
              aria-expanded={isOpen}
            >
              <span className="cal-impact" style={{ backgroundColor: impactColor }} />
              <div className="cal-info">
                <span className="cal-title">{event.title}</span>
                <span className="cal-meta">
                  {event.currency} · {formatEventTime(event.event_time)}
                </span>
              </div>
              <span className="cal-badge" style={{ color: impactColor }}>
                {event.impact}
              </span>
            </button>

            {isOpen && (
              <div className="calendar-detail">
                <div className="calendar-detail-row">
                  <span className="calendar-detail-label">When</span>
                  <span>{formatEventTime(event.event_time)} · {timeUntil(event.event_time)}</span>
                </div>
                {event.forecast && (
                  <div className="calendar-detail-row">
                    <span className="calendar-detail-label">Forecast</span>
                    <span>{event.forecast}</span>
                  </div>
                )}
                {event.previous && (
                  <div className="calendar-detail-row">
                    <span className="calendar-detail-label">Previous</span>
                    <span>{event.previous}</span>
                  </div>
                )}
                {event.actual && (
                  <div className="calendar-detail-row">
                    <span className="calendar-detail-label">Actual</span>
                    <span>{event.actual}</span>
                  </div>
                )}
                {onFilterCurrency && (
                  <button
                    type="button"
                    className="calendar-filter-btn"
                    onClick={() =>
                      onFilterCurrency(isFiltered ? null : event.currency)
                    }
                  >
                    {isFiltered
                      ? `Clear ${event.currency} pair filter`
                      : `Show ${event.currency} pairs in scanner`}
                  </button>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
