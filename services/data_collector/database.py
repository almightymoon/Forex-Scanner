"""Database layer for the market data collector — PostgreSQL-compatible."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Generator, Optional

from services.data_collector.config import get_collector_config
from services.data_collector.models import (
    CollectedCandle,
    CollectedTick,
    CollectionLogEntry,
    ProviderHealthStatus,
)
from services.data_collector.symbols import SymbolInfo, SymbolRegistry
from shared.types.models import Timeframe

COLLECTOR_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dc_symbols (
    symbol          VARCHAR(16) PRIMARY KEY,
    name            VARCHAR(64) NOT NULL,
    category        VARCHAR(16) NOT NULL DEFAULT 'major',
    base_currency   VARCHAR(8) NOT NULL,
    quote_currency  VARCHAR(8) NOT NULL,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dc_candles (
    symbol          VARCHAR(16) NOT NULL,
    timeframe       VARCHAR(8) NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    open            DOUBLE PRECISION NOT NULL,
    high            DOUBLE PRECISION NOT NULL,
    low             DOUBLE PRECISION NOT NULL,
    close           DOUBLE PRECISION NOT NULL,
    volume          BIGINT NOT NULL DEFAULT 0,
    provider        VARCHAR(32) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (symbol, timeframe, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_dc_candles_lookup
    ON dc_candles (symbol, timeframe, timestamp DESC);

CREATE TABLE IF NOT EXISTS dc_ticks (
    symbol          VARCHAR(16) NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    bid             DOUBLE PRECISION NOT NULL,
    ask             DOUBLE PRECISION NOT NULL,
    volume          BIGINT NOT NULL DEFAULT 0,
    provider        VARCHAR(32) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (symbol, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_dc_ticks_lookup
    ON dc_ticks (symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS dc_provider_status (
    provider            VARCHAR(32) PRIMARY KEY,
    state               VARCHAR(16) NOT NULL DEFAULT 'disconnected',
    connected           BOOLEAN NOT NULL DEFAULT FALSE,
    last_update         TIMESTAMPTZ,
    last_successful_sync TIMESTAMPTZ,
    rows_collected      BIGINT NOT NULL DEFAULT 0,
    rows_rejected       BIGINT NOT NULL DEFAULT 0,
    latency_ms          DOUBLE PRECISION,
    message             TEXT DEFAULT '',
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS dc_collection_logs (
    id              SERIAL PRIMARY KEY,
    provider        VARCHAR(32) NOT NULL,
    symbol          VARCHAR(16) NOT NULL,
    timeframe       VARCHAR(8) NOT NULL,
    job_type        VARCHAR(32) NOT NULL,
    duration_ms     DOUBLE PRECISION NOT NULL,
    rows_imported   INTEGER NOT NULL DEFAULT 0,
    rows_rejected   INTEGER NOT NULL DEFAULT 0,
    status          VARCHAR(16) NOT NULL,
    message         TEXT DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dc_collection_logs_created
    ON dc_collection_logs (created_at DESC);
"""

SQLITE_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dc_symbols (
    symbol          TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT NOT NULL DEFAULT 'major',
    base_currency   TEXT NOT NULL,
    quote_currency  TEXT NOT NULL,
    is_active       INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dc_candles (
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    open            REAL NOT NULL,
    high            REAL NOT NULL,
    low             REAL NOT NULL,
    close           REAL NOT NULL,
    volume          INTEGER NOT NULL DEFAULT 0,
    provider        TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, timeframe, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_dc_candles_lookup
    ON dc_candles (symbol, timeframe, timestamp DESC);

CREATE TABLE IF NOT EXISTS dc_ticks (
    symbol          TEXT NOT NULL,
    timestamp       TEXT NOT NULL,
    bid             REAL NOT NULL,
    ask             REAL NOT NULL,
    volume          INTEGER NOT NULL DEFAULT 0,
    provider        TEXT NOT NULL,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_dc_ticks_lookup
    ON dc_ticks (symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS dc_provider_status (
    provider            TEXT PRIMARY KEY,
    state               TEXT NOT NULL DEFAULT 'disconnected',
    connected           INTEGER NOT NULL DEFAULT 0,
    last_update         TEXT,
    last_successful_sync TEXT,
    rows_collected      INTEGER NOT NULL DEFAULT 0,
    rows_rejected       INTEGER NOT NULL DEFAULT 0,
    latency_ms          REAL,
    message             TEXT DEFAULT '',
    updated_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dc_collection_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    provider        TEXT NOT NULL,
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    job_type        TEXT NOT NULL,
    duration_ms     REAL NOT NULL,
    rows_imported   INTEGER NOT NULL DEFAULT 0,
    rows_rejected   INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL,
    message         TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dc_collection_logs_created
    ON dc_collection_logs (created_at DESC);
"""


class CollectorDatabase:
    """Normalized market data persistence — PostgreSQL primary, SQLite for tests."""

    def __init__(self, url: Optional[str] = None, *, force_sqlite: bool = False):
        cfg = get_collector_config()

        if force_sqlite or url in ("sqlite:", "sqlite"):
            self.url = ""
            self._use_postgres = False
        elif url is not None:
            self.url = url
            self._use_postgres = url.startswith("postgresql")
        else:
            self.url = cfg.database.url or os.getenv("DATABASE_URL", "")
            self._use_postgres = bool(self.url.startswith("postgresql"))

        self._sqlite_path: Optional[Path] = None

        if not self._use_postgres:
            self._sqlite_path = Path(
                os.getenv("COLLECTOR_SQLITE_PATH", "data/collector.db")
            )
            self._sqlite_path.parent.mkdir(parents=True, exist_ok=True)

        if cfg.database.auto_migrate:
            self._init_schema()

    @contextmanager
    def _connect(self) -> Generator[Any, None, None]:
        if self._use_postgres:
            import psycopg2
            from psycopg2.extras import RealDictCursor

            conn = psycopg2.connect(self.url, cursor_factory=RealDictCursor)
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(str(self._sqlite_path))
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

    def _init_schema(self) -> None:
        schema = COLLECTOR_SCHEMA_SQL if self._use_postgres else SQLITE_SCHEMA_SQL
        with self._connect() as conn:
            cursor = conn.cursor()
            for statement in schema.split(";"):
                stmt = statement.strip()
                if stmt:
                    cursor.execute(stmt)

    def upsert_symbol(self, info: SymbolInfo) -> None:
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            cur = conn.cursor()
            if self._use_postgres:
                cur.execute(
                    """INSERT INTO dc_symbols
                       (symbol, name, category, base_currency, quote_currency, is_active, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (symbol) DO UPDATE SET
                         name=EXCLUDED.name, category=EXCLUDED.category,
                         is_active=EXCLUDED.is_active""",
                    (info.symbol, info.name, info.category, info.base_currency,
                     info.quote_currency, info.is_active, now),
                )
            else:
                cur.execute(
                    """INSERT OR REPLACE INTO dc_symbols
                       (symbol, name, category, base_currency, quote_currency, is_active, created_at)
                       VALUES (?,?,?,?,?,?,?)""",
                    (info.symbol, info.name, info.category, info.base_currency,
                     info.quote_currency, int(info.is_active), now.isoformat()),
                )

    def sync_symbols(self, registry: Optional[SymbolRegistry] = None) -> int:
        registry = registry or SymbolRegistry()
        count = 0
        for info in registry.all():
            self.upsert_symbol(info)
            count += 1
        return count

    def insert_candles(self, candles: list[CollectedCandle]) -> int:
        if not candles:
            return 0
        inserted = 0
        with self._connect() as conn:
            cur = conn.cursor()
            for c in candles:
                if self._use_postgres:
                    cur.execute(
                        """INSERT INTO dc_candles
                           (symbol, timeframe, timestamp, open, high, low, close, volume, provider, created_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (symbol, timeframe, timestamp) DO UPDATE SET
                             open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                             close=EXCLUDED.close, volume=EXCLUDED.volume,
                             provider=EXCLUDED.provider, created_at=EXCLUDED.created_at""",
                        (c.symbol, c.timeframe.value, c.timestamp,
                         c.open, c.high, c.low, c.close, c.volume, c.provider, c.created_at),
                    )
                else:
                    cur.execute(
                        """INSERT OR REPLACE INTO dc_candles
                           (symbol, timeframe, timestamp, open, high, low, close, volume, provider, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (c.symbol, c.timeframe.value, c.timestamp.isoformat(),
                         c.open, c.high, c.low, c.close, c.volume, c.provider, c.created_at.isoformat()),
                    )
                inserted += 1
        return inserted

    def insert_ticks(self, ticks: list[CollectedTick]) -> int:
        if not ticks:
            return 0
        inserted = 0
        with self._connect() as conn:
            cur = conn.cursor()
            for t in ticks:
                if self._use_postgres:
                    cur.execute(
                        """INSERT INTO dc_ticks
                           (symbol, timestamp, bid, ask, volume, provider, created_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (symbol, timestamp) DO UPDATE SET
                             bid=EXCLUDED.bid, ask=EXCLUDED.ask, volume=EXCLUDED.volume,
                             provider=EXCLUDED.provider""",
                        (t.symbol, t.timestamp, t.bid, t.ask, t.volume, t.provider, t.created_at),
                    )
                else:
                    cur.execute(
                        """INSERT OR REPLACE INTO dc_ticks
                           (symbol, timestamp, bid, ask, volume, provider, created_at)
                           VALUES (?,?,?,?,?,?,?)""",
                        (t.symbol, t.timestamp.isoformat(), t.bid, t.ask, t.volume,
                         t.provider, t.created_at.isoformat()),
                    )
                inserted += 1
        return inserted

    def get_candles(
        self,
        symbol: str,
        timeframe: Timeframe,
        limit: int = 200,
        since: Optional[datetime] = None,
    ) -> list[CollectedCandle]:
        query = """SELECT symbol, timeframe, timestamp, open, high, low, close, volume, provider, created_at
                   FROM dc_candles WHERE symbol = ? AND timeframe = ?"""
        params: list[Any] = [symbol.upper(), timeframe.value]

        if since:
            query += " AND timestamp >= ?"
            params.append(since.isoformat() if not self._use_postgres else since)

        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        if self._use_postgres:
            query = query.replace("?", "%s")

        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()

        return [self._row_to_candle(row) for row in reversed(rows)]

    def get_latest_timestamp(
        self, symbol: str, timeframe: Timeframe
    ) -> Optional[datetime]:
        ph = "%s" if self._use_postgres else "?"
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT MAX(timestamp) AS ts FROM dc_candles WHERE symbol = {ph} AND timeframe = {ph}",
                (symbol.upper(), timeframe.value),
            )
            row = cur.fetchone()
        if not row:
            return None
        ts = row["ts"] if isinstance(row, dict) else row[0]
        if ts is None:
            return None
        if isinstance(ts, str):
            return datetime.fromisoformat(ts)
        return ts

    def update_provider_status(self, status: ProviderHealthStatus) -> None:
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            cur = conn.cursor()
            if self._use_postgres:
                cur.execute(
                    """INSERT INTO dc_provider_status
                       (provider, state, connected, last_update, last_successful_sync,
                        rows_collected, rows_rejected, latency_ms, message, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (provider) DO UPDATE SET
                         state=EXCLUDED.state, connected=EXCLUDED.connected,
                         last_update=EXCLUDED.last_update,
                         last_successful_sync=EXCLUDED.last_successful_sync,
                         rows_collected=EXCLUDED.rows_collected,
                         rows_rejected=EXCLUDED.rows_rejected,
                         latency_ms=EXCLUDED.latency_ms, message=EXCLUDED.message,
                         updated_at=EXCLUDED.updated_at""",
                    (status.provider, status.state.value, status.connected,
                     status.last_update, status.last_successful_sync,
                     status.rows_collected, status.rows_rejected,
                     status.latency_ms, status.message, now),
                )
            else:
                cur.execute(
                    """INSERT OR REPLACE INTO dc_provider_status
                       (provider, state, connected, last_update, last_successful_sync,
                        rows_collected, rows_rejected, latency_ms, message, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (status.provider, status.state.value, int(status.connected),
                     status.last_update.isoformat() if status.last_update else None,
                     status.last_successful_sync.isoformat() if status.last_successful_sync else None,
                     status.rows_collected, status.rows_rejected,
                     status.latency_ms, status.message, now.isoformat()),
                )

    def get_provider_status(self, provider: str) -> Optional[ProviderHealthStatus]:
        ph = "%s" if self._use_postgres else "?"
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM dc_provider_status WHERE provider = {ph}",
                (provider,),
            )
            row = cur.fetchone()
        if not row:
            return None
        return self._row_to_provider_status(row)

    def get_all_provider_statuses(self) -> list[ProviderHealthStatus]:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM dc_provider_status ORDER BY provider")
            rows = cur.fetchall()
        return [self._row_to_provider_status(r) for r in rows]

    def log_collection(self, entry: CollectionLogEntry) -> int:
        created = entry.created_at or datetime.now(timezone.utc)
        with self._connect() as conn:
            cur = conn.cursor()
            if self._use_postgres:
                cur.execute(
                    """INSERT INTO dc_collection_logs
                       (provider, symbol, timeframe, job_type, duration_ms,
                        rows_imported, rows_rejected, status, message, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (entry.provider, entry.symbol, entry.timeframe, entry.job_type,
                     entry.duration_ms, entry.rows_imported, entry.rows_rejected,
                     entry.status, entry.message, created),
                )
                row = cur.fetchone()
                return row["id"]
            cur.execute(
                """INSERT INTO dc_collection_logs
                   (provider, symbol, timeframe, job_type, duration_ms,
                    rows_imported, rows_rejected, status, message, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (entry.provider, entry.symbol, entry.timeframe, entry.job_type,
                 entry.duration_ms, entry.rows_imported, entry.rows_rejected,
                 entry.status, entry.message, created.isoformat()),
            )
            return cur.lastrowid or 0

    def _row_to_candle(self, row: Any) -> CollectedCandle:
        if isinstance(row, sqlite3.Row):
            row = dict(row)
        ts = row["timestamp"]
        created = row["created_at"]
        if isinstance(ts, str):
            ts = datetime.fromisoformat(ts)
        if isinstance(created, str):
            created = datetime.fromisoformat(created)
        return CollectedCandle(
            symbol=row["symbol"],
            timeframe=Timeframe(row["timeframe"]),
            timestamp=ts,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"]),
            provider=row["provider"],
            created_at=created,
        )

    def _row_to_provider_status(self, row: Any) -> ProviderHealthStatus:
        from services.data_collector.models import ProviderState

        if isinstance(row, sqlite3.Row):
            row = dict(row)

        def _parse_ts(val: Any) -> Optional[datetime]:
            if val is None:
                return None
            if isinstance(val, str):
                return datetime.fromisoformat(val)
            return val

        return ProviderHealthStatus(
            provider=row["provider"],
            state=ProviderState(row["state"]),
            connected=bool(row["connected"]),
            last_update=_parse_ts(row.get("last_update")),
            last_successful_sync=_parse_ts(row.get("last_successful_sync")),
            rows_collected=int(row.get("rows_collected", 0)),
            rows_rejected=int(row.get("rows_rejected", 0)),
            latency_ms=row.get("latency_ms"),
            message=row.get("message", "") or "",
        )

_db: Optional[CollectorDatabase] = None


def get_collector_database(url: Optional[str] = None) -> CollectorDatabase:
    global _db
    if url is not None:
        return CollectorDatabase(url)
    if _db is None:
        _db = CollectorDatabase()
    return _db

def reset_collector_database() -> None:
    global _db
    _db = None
