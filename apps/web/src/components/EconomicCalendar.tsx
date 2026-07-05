"use client";

interface EconomicEvent {
  currency: string;
  title: string;
  impact: string;
  event_time: string;
  forecast?: string;
  previous?: string;
}

interface Props {
  events: EconomicEvent[];
}

const IMPACT_COLORS: Record<string, string> = {
  high: "#ef4444",
  medium: "#f59e0b",
  low: "#6b7280",
};

export function EconomicCalendar({ events }: Props) {
  if (events.length === 0) {
    return <div className="calendar-empty">No upcoming events</div>;
  }

  return (
    <div className="calendar-list">
      {events.slice(0, 8).map((e, i) => {
        const time = new Date(e.event_time).toLocaleString(undefined, {
          month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
        });
        return (
          <div key={i} className="calendar-item">
            <span className="cal-impact" style={{ backgroundColor: IMPACT_COLORS[e.impact] || "#6b7280" }} />
            <div className="cal-info">
              <span className="cal-title">{e.title}</span>
              <span className="cal-meta">{e.currency} · {time}</span>
            </div>
            <span className="cal-badge" style={{ color: IMPACT_COLORS[e.impact] }}>
              {e.impact}
            </span>
          </div>
        );
      })}
    </div>
  );
}
