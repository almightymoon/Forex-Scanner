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
                    -- Full schema (database/schema.sql) omits payload JSON; adapters need it for round-trip.
                    ALTER TABLE scanner_results ADD COLUMN IF NOT EXISTS data JSONB;
                    ALTER TABLE scanner_results ADD COLUMN IF NOT EXISTS score_breakdown JSONB;
                    ALTER TABLE scanner_results ADD COLUMN IF NOT EXISTS technical_reasons JSONB DEFAULT '[]'::jsonb;
                    ALTER TABLE scanner_results ADD COLUMN IF NOT EXISTS smc_reasons JSONB DEFAULT '[]'::jsonb;
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

                    CREATE TABLE IF NOT EXISTS validation_outcomes (
                        id VARCHAR(64) PRIMARY KEY,
                        symbol VARCHAR(16) NOT NULL,
                        timeframe VARCHAR(8) NOT NULL,
                        direction VARCHAR(16) NOT NULL,
                        score INTEGER NOT NULL,
                        confidence DOUBLE PRECISION NOT NULL,
                        entry_price DECIMAL(18, 8) NOT NULL,
                        stop_loss DECIMAL(18, 8) NOT NULL,
                        take_profit DECIMAL(18, 8) NOT NULL,
                        patterns JSONB NOT NULL DEFAULT '[]'::jsonb,
                        outcome VARCHAR(32),
                        pnl_pips DECIMAL(12, 4) NOT NULL DEFAULT 0,
                        exit_price DECIMAL(18, 8),
                        created_at TIMESTAMPTZ NOT NULL,
                        closed_at TIMESTAMPTZ
                    );
                    CREATE INDEX IF NOT EXISTS idx_pg_validation_outcomes_symbol
                        ON validation_outcomes (symbol, created_at DESC);
                    CREATE INDEX IF NOT EXISTS idx_pg_validation_outcomes_open
                        ON validation_outcomes (symbol, created_at DESC)
                        WHERE outcome IS NULL;
                """)
            conn.commit()

    def save_scanner_result(self, signal: ScannerSignal) -> int:
        payload = to_dict(signal)
        score_breakdown = payload.get("score_breakdown") or {}
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO scanner_results
                       (symbol, timeframe, direction, score, rating, trend, risk_level,
                        score_breakdown, technical_reasons, smc_reasons, news_impact, mtf_alignment,
                        entry_zone_low, entry_zone_high, stop_loss, take_profit_1, take_profit_2,
                        take_profit_3, risk_reward, ai_explanation, data, created_at)
                       VALUES (
                         %s,%s,%s,%s,%s,%s,%s,
                         %s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,
                         %s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s
                       ) RETURNING id""",
                    (
                        signal.symbol,
                        signal.timeframe.value,
                        signal.direction.value,
                        signal.score,
                        signal.rating.value,
                        signal.trend.value,
                        signal.risk_level.value,
                        json.dumps(score_breakdown),
                        json.dumps(payload.get("technical_reasons") or []),
                        json.dumps(payload.get("smc_reasons") or []),
                        json.dumps(payload["news_impact"]) if payload.get("news_impact") is not None else None,
                        json.dumps(payload["mtf_alignment"]) if payload.get("mtf_alignment") is not None else None,
                        signal.entry_zone_low,
                        signal.entry_zone_high,
                        signal.stop_loss,
                        signal.take_profit_1,
                        signal.take_profit_2,
                        signal.take_profit_3,
                        signal.risk_reward,
                        signal.ai_explanation,
                        json.dumps(payload),
                        datetime.now(timezone.utc),
                    ),
                )
                row = cur.fetchone()
            conn.commit()
            return row["id"]

    def save_scan_results(self, signals: list[ScannerSignal]) -> int:
        saved = 0
        for signal in signals:
            self.save_scanner_result(signal)
            saved += 1
        return saved

    def get_recent_results(self, limit: int = 50, min_score: int = 0, symbol: Optional[str] = None) -> list[dict]:
        query = """SELECT COALESCE(data, jsonb_build_object(
                        'symbol', symbol,
                        'timeframe', timeframe,
                        'direction', direction,
                        'score', score,
                        'rating', rating,
                        'trend', trend,
                        'risk_level', risk_level,
                        'score_breakdown', COALESCE(score_breakdown, '{}'::jsonb),
                        'technical_reasons', COALESCE(technical_reasons, '[]'::jsonb),
                        'smc_reasons', COALESCE(smc_reasons, '[]'::jsonb)
                    )) AS data
                   FROM scanner_results WHERE score >= %s"""
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

    def upsert_validation_outcome(self, row: dict) -> str:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO validation_outcomes (
                           id, symbol, timeframe, direction, score, confidence,
                           entry_price, stop_loss, take_profit, patterns, outcome,
                           pnl_pips, exit_price, created_at, closed_at
                       ) VALUES (
                           %s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s
                       )
                       ON CONFLICT (id) DO UPDATE SET
                           symbol = EXCLUDED.symbol,
                           timeframe = EXCLUDED.timeframe,
                           direction = EXCLUDED.direction,
                           score = EXCLUDED.score,
                           confidence = EXCLUDED.confidence,
                           entry_price = EXCLUDED.entry_price,
                           stop_loss = EXCLUDED.stop_loss,
                           take_profit = EXCLUDED.take_profit,
                           patterns = EXCLUDED.patterns,
                           outcome = EXCLUDED.outcome,
                           pnl_pips = EXCLUDED.pnl_pips,
                           exit_price = EXCLUDED.exit_price,
                           created_at = EXCLUDED.created_at,
                           closed_at = EXCLUDED.closed_at
                    """,
                    (
                        row["id"],
                        row["symbol"],
                        row["timeframe"],
                        row["direction"],
                        row["score"],
                        row["confidence"],
                        row["entry_price"],
                        row["stop_loss"],
                        row["take_profit"],
                        json.dumps(row.get("patterns") or []),
                        row.get("outcome"),
                        row.get("pnl_pips") or 0.0,
                        row.get("exit_price"),
                        row["created_at"],
                        row.get("closed_at"),
                    ),
                )
            conn.commit()
        return row["id"]

    def get_validation_outcome(self, signal_id: str) -> Optional[dict]:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM validation_outcomes WHERE id = %s",
                    (signal_id,),
                )
                row = cur.fetchone()
        return self._validation_row_to_dict(row) if row else None

    def list_validation_outcomes(
        self,
        symbol: Optional[str] = None,
        closed_only: bool = False,
        limit: int = 5000,
    ) -> list[dict]:
        query = "SELECT * FROM validation_outcomes WHERE 1=1"
        params: list = []
        if symbol:
            query += " AND symbol = %s"
            params.append(symbol.upper())
        if closed_only:
            query += " AND outcome IS NOT NULL"
        query += " ORDER BY created_at DESC LIMIT %s"
        params.append(limit)
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params)
                rows = cur.fetchall()
        return [self._validation_row_to_dict(r) for r in rows]

    @staticmethod
    def _validation_row_to_dict(row) -> dict:
        patterns = row["patterns"]
        if isinstance(patterns, str):
            patterns = json.loads(patterns or "[]")
        elif patterns is None:
            patterns = []
        created_at = row["created_at"]
        closed_at = row["closed_at"]
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        if hasattr(closed_at, "isoformat"):
            closed_at = closed_at.isoformat()
        return {
            "id": row["id"],
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "direction": row["direction"],
            "score": int(row["score"]),
            "confidence": float(row["confidence"]),
            "entry_price": float(row["entry_price"]),
            "stop_loss": float(row["stop_loss"]),
            "take_profit": float(row["take_profit"]),
            "patterns": list(patterns),
            "outcome": row["outcome"],
            "pnl_pips": float(row["pnl_pips"] or 0),
            "exit_price": float(row["exit_price"]) if row["exit_price"] is not None else None,
            "created_at": created_at,
            "closed_at": closed_at,
        }
