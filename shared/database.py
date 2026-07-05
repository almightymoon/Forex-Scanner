"""SQLite persistence layer (dev fallback when PostgreSQL unavailable)."""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from shared.types.models import ScannerSignal, to_dict

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "fxnav.db"


class Database:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self):
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS scanner_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    score INTEGER NOT NULL,
                    rating TEXT NOT NULL,
                    trend TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    data JSON NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_scanner_created
                    ON scanner_results(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_scanner_symbol
                    ON scanner_results(symbol, created_at DESC);

                CREATE TABLE IF NOT EXISTS economic_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    currency TEXT NOT NULL,
                    title TEXT NOT NULL,
                    impact TEXT NOT NULL,
                    forecast TEXT,
                    previous TEXT,
                    actual TEXT,
                    event_time TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT,
                    min_score INTEGER DEFAULT 80,
                    delivery_method TEXT DEFAULT 'push',
                    is_active INTEGER DEFAULT 1,
                    last_triggered TEXT,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id INTEGER,
                    symbol TEXT NOT NULL,
                    title TEXT NOT NULL,
                    body TEXT NOT NULL,
                    delivery_method TEXT NOT NULL,
                    status TEXT DEFAULT 'sent',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS backtest_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    min_score INTEGER NOT NULL,
                    total_trades INTEGER NOT NULL,
                    wins INTEGER NOT NULL,
                    losses INTEGER NOT NULL,
                    win_rate REAL NOT NULL,
                    avg_rr REAL,
                    max_drawdown REAL,
                    data JSON NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)

    def save_scanner_result(self, signal: ScannerSignal) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO scanner_results
                   (symbol, timeframe, direction, score, rating, trend, risk_level, data, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    signal.symbol,
                    signal.timeframe.value,
                    signal.direction.value,
                    signal.score,
                    signal.rating.value,
                    signal.trend.value,
                    signal.risk_level.value,
                    json.dumps(to_dict(signal)),
                    now,
                ),
            )
            return cur.lastrowid

    def save_scan_results(self, signals: list[ScannerSignal]) -> int:
        return sum(self.save_scanner_result(s) for s in signals)

    def get_recent_results(
        self, limit: int = 50, min_score: int = 0, symbol: Optional[str] = None
    ) -> list[dict]:
        query = "SELECT data FROM scanner_results WHERE score >= ?"
        params: list = [min_score]
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()
        return [json.loads(row["data"]) for row in rows]

    def save_economic_events(self, events: list[dict]) -> int:
        now = datetime.now(timezone.utc).isoformat()
        count = 0
        with self._connect() as conn:
            for e in events:
                conn.execute(
                    """INSERT INTO economic_events
                       (currency, title, impact, forecast, previous, actual, event_time, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        e["currency"], e["title"], e["impact"],
                        e.get("forecast"), e.get("previous"), e.get("actual"),
                        e["event_time"], now,
                    ),
                )
                count += 1
        return count

    def get_upcoming_events(self, hours: int = 48) -> list[dict]:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT currency, title, impact, forecast, previous, actual, event_time
                   FROM economic_events
                   WHERE event_time >= ?
                   ORDER BY event_time ASC LIMIT 50""",
                (now,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_active_alerts(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE is_active = 1"
            ).fetchall()
        return [dict(row) for row in rows]

    def save_notification(self, alert_id: Optional[int], symbol: str, title: str, body: str, method: str):
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO notifications
                   (alert_id, symbol, title, body, delivery_method, status, created_at)
                   VALUES (?, ?, ?, ?, ?, 'sent', ?)""",
                (alert_id, symbol, title, body, method, now),
            )

    def get_stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM scanner_results").fetchone()[0]
            elite = conn.execute(
                "SELECT COUNT(*) FROM scanner_results WHERE score >= 90"
            ).fetchone()[0]
            today = conn.execute(
                "SELECT COUNT(*) FROM scanner_results WHERE created_at >= date('now')"
            ).fetchone()[0]
        return {"total_scans": total, "elite_setups": elite, "scans_today": today, "backend": "sqlite"}

    def save_backtest_result(self, symbol: str, timeframe: str, min_score: int, result: dict) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            cur = conn.execute(
                """INSERT INTO backtest_results
                   (symbol, timeframe, min_score, total_trades, wins, losses,
                    win_rate, avg_rr, max_drawdown, data, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    symbol, timeframe, min_score,
                    result["total_trades"], result["wins"], result["losses"],
                    result["win_rate"], result.get("avg_rr"), result.get("max_drawdown"),
                    json.dumps(result), now,
                ),
            )
            return cur.lastrowid

    def get_latest_backtest(self, symbol: str, timeframe: str = "H1"):
        with self._connect() as conn:
            row = conn.execute(
                """SELECT data FROM backtest_results
                   WHERE symbol = ? AND timeframe = ?
                   ORDER BY created_at DESC LIMIT 1""",
                (symbol.upper(), timeframe),
            ).fetchone()
        return json.loads(row["data"]) if row else None
