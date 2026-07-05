"""PostgreSQL database adapter."""

import json
from datetime import datetime, timezone
from typing import Optional

from shared.configs.settings import get_settings
from shared.types.models import ScannerSignal, to_dict

settings = get_settings()


class PostgresDatabase:
    def __init__(self, url: Optional[str] = None):
        import psycopg2
        from psycopg2.extras import RealDictCursor

        self._psycopg2 = psycopg2
        self._RealDictCursor = RealDictCursor
        self.url = url or settings.DATABASE_URL
        self._init_schema()

    def _connect(self):
        return self._psycopg2.connect(self.url, cursor_factory=self._RealDictCursor)

    def _init_schema(self):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS scanner_results (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(16) NOT NULL,
                        timeframe VARCHAR(8) NOT NULL,
                        direction VARCHAR(16) NOT NULL,
                        score INTEGER NOT NULL,
                        rating VARCHAR(16) NOT NULL,
                        trend VARCHAR(16) NOT NULL,
                        risk_level VARCHAR(16) NOT NULL,
                        data JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE INDEX IF NOT EXISTS idx_pg_scanner_created ON scanner_results(created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_pg_scanner_symbol ON scanner_results(symbol, created_at DESC);

                    CREATE TABLE IF NOT EXISTS economic_events (
                        id SERIAL PRIMARY KEY,
                        currency VARCHAR(8) NOT NULL,
                        title VARCHAR(512) NOT NULL,
                        impact VARCHAR(16) NOT NULL,
                        forecast VARCHAR(64),
                        previous VARCHAR(64),
                        actual VARCHAR(64),
                        event_time TIMESTAMPTZ NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );

                    CREATE TABLE IF NOT EXISTS backtest_results (
                        id SERIAL PRIMARY KEY,
                        symbol VARCHAR(16) NOT NULL,
                        timeframe VARCHAR(8) NOT NULL,
                        min_score INTEGER NOT NULL,
                        total_trades INTEGER NOT NULL,
                        wins INTEGER NOT NULL,
                        losses INTEGER NOT NULL,
                        win_rate DECIMAL(6,2) NOT NULL,
                        avg_rr DECIMAL(6,2),
                        max_drawdown DECIMAL(6,2),
                        data JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                """)
            conn.commit()

    def save_scanner_result(self, signal: ScannerSignal) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO scanner_results
                       (symbol, timeframe, direction, score, rating, trend, risk_level, data, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (
                        signal.symbol, signal.timeframe.value, signal.direction.value,
                        signal.score, signal.rating.value, signal.trend.value,
                        signal.risk_level.value, json.dumps(to_dict(signal)),
                        datetime.now(timezone.utc),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]

    def save_scan_results(self, signals: list[ScannerSignal]) -> int:
        return sum(self.save_scanner_result(s) for s in signals)

    def get_recent_results(self, limit: int = 50, min_score: int = 0, symbol: Optional[str] = None) -> list[dict]:
        query = "SELECT data FROM scanner_results WHERE score >= %s"
        params: list = [min_score]
        if symbol:
            query += " AND symbol = %s"
            params.append(symbol.upper())
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return [row["data"] if isinstance(row["data"], dict) else json.loads(row["data"]) for row in rows]

    def save_economic_events(self, events: list[dict]) -> int:
        count = 0
        with self._connect() as conn:
            with conn.cursor() as cur:
                for e in events:
                    cur.execute(
                        """INSERT INTO economic_events
                           (currency, title, impact, forecast, previous, actual, event_time, created_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                        (
                            e["currency"], e["title"], e["impact"],
                            e.get("forecast"), e.get("previous"), e.get("actual"),
                            e["event_time"], datetime.now(timezone.utc),
                        ),
                    )
                    count += 1
            conn.commit()
        return count

    def get_upcoming_events(self, hours: int = 48) -> list[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT currency, title, impact, forecast, previous, actual, event_time
                       FROM economic_events WHERE event_time >= NOW()
                       ORDER BY event_time ASC LIMIT 50"""
                )
                rows = cur.fetchall()
        return [dict(r) for r in rows]

    def get_active_alerts(self) -> list[dict]:
        return []

    def save_notification(self, alert_id, symbol, title, body, method):
        pass

    def save_backtest_result(self, symbol: str, timeframe: str, min_score: int, result: dict) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO backtest_results
                       (symbol, timeframe, min_score, total_trades, wins, losses,
                        win_rate, avg_rr, max_drawdown, data, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (
                        symbol, timeframe, min_score,
                        result["total_trades"], result["wins"], result["losses"],
                        result["win_rate"], result.get("avg_rr"), result.get("max_drawdown"),
                        json.dumps(result), datetime.now(timezone.utc),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]

    def get_latest_backtest(self, symbol: str, timeframe: str = "H1") -> Optional[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT data FROM backtest_results
                       WHERE symbol = %s AND timeframe = %s
                       ORDER BY created_at DESC LIMIT 1""",
                    (symbol.upper(), timeframe),
                )
                row = cur.fetchone()
        if not row:
            return None
        data = row["data"]
        return data if isinstance(data, dict) else json.loads(data)

    def get_stats(self) -> dict:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS c FROM scanner_results")
                total = cur.fetchone()["c"]
                cur.execute("SELECT COUNT(*) AS c FROM scanner_results WHERE score >= 90")
                elite = cur.fetchone()["c"]
                cur.execute(
                    "SELECT COUNT(*) AS c FROM scanner_results WHERE created_at >= CURRENT_DATE"
                )
                today = cur.fetchone()["c"]
        return {"total_scans": total, "elite_setups": elite, "scans_today": today, "backend": "postgresql"}
