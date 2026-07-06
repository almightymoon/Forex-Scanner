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
    DataGap,
    GapStatus,
    ProviderHealthStatus,
    SyncStatus,
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
    sync_status         VARCHAR(32) NOT NULL DEFAULT 'unknown',
    connected           BOOLEAN NOT NULL DEFAULT FALSE,
    last_update         TIMESTAMPTZ,
    last_successful_sync TIMESTAMPTZ,
    last_candle_timestamp TIMESTAMPTZ,
    rows_collected      BIGINT NOT NULL DEFAULT 0,
    rows_downloaded     BIGINT NOT NULL DEFAULT 0,
    rows_rejected       BIGINT NOT NULL DEFAULT 0,
    rows_repaired       BIGINT NOT NULL DEFAULT 0,
    latency_ms          DOUBLE PRECISION,
    sync_latency_ms     DOUBLE PRECISION,
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

CREATE INDEX IF NOT EXISTS idx_dc_candles_symbol ON dc_candles (symbol);
CREATE INDEX IF NOT EXISTS idx_dc_candles_timeframe ON dc_candles (timeframe);
CREATE INDEX IF NOT EXISTS idx_dc_candles_timestamp ON dc_candles (timestamp DESC);

CREATE TABLE IF NOT EXISTS dc_gaps (
    id                  SERIAL PRIMARY KEY,
    symbol              VARCHAR(16) NOT NULL,
    timeframe           VARCHAR(8) NOT NULL,
    gap_type            VARCHAR(32) NOT NULL,
    expected_timestamp  TIMESTAMPTZ,
    gap_start           TIMESTAMPTZ,
    gap_end             TIMESTAMPTZ,
    status              VARCHAR(16) NOT NULL DEFAULT 'open',
    provider            VARCHAR(32) DEFAULT '',
    repaired_at         TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dc_gaps_lookup ON dc_gaps (symbol, timeframe, status);

CREATE TABLE IF NOT EXISTS dc_import_jobs (
    id              SERIAL PRIMARY KEY,
    symbol          VARCHAR(16) NOT NULL,
    timeframe       VARCHAR(8) NOT NULL,
    range_label     VARCHAR(16) NOT NULL,
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ NOT NULL,
    rows_imported   INTEGER NOT NULL DEFAULT 0,
    status          VARCHAR(16) NOT NULL DEFAULT 'completed',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
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
    sync_status         TEXT NOT NULL DEFAULT 'unknown',
    connected           INTEGER NOT NULL DEFAULT 0,
    last_update         TEXT,
    last_successful_sync TEXT,
    last_candle_timestamp TEXT,
    rows_collected      INTEGER NOT NULL DEFAULT 0,
    rows_downloaded     INTEGER NOT NULL DEFAULT 0,
    rows_rejected       INTEGER NOT NULL DEFAULT 0,
    rows_repaired       INTEGER NOT NULL DEFAULT 0,
    latency_ms          REAL,
    sync_latency_ms       REAL,
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

CREATE INDEX IF NOT EXISTS idx_dc_candles_symbol ON dc_candles (symbol);
CREATE INDEX IF NOT EXISTS idx_dc_candles_timeframe ON dc_candles (timeframe);
CREATE INDEX IF NOT EXISTS idx_dc_candles_timestamp ON dc_candles (timestamp DESC);

CREATE TABLE IF NOT EXISTS dc_gaps (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol              TEXT NOT NULL,
    timeframe           TEXT NOT NULL,
    gap_type            TEXT NOT NULL,
    expected_timestamp  TEXT,
    gap_start           TEXT,
    gap_end             TEXT,
    status              TEXT NOT NULL DEFAULT 'open',
    provider            TEXT DEFAULT '',
    repaired_at         TEXT,
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_dc_gaps_lookup ON dc_gaps (symbol, timeframe, status);

CREATE TABLE IF NOT EXISTS dc_import_jobs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol          TEXT NOT NULL,
    timeframe       TEXT NOT NULL,
    range_label     TEXT NOT NULL,
    start_time      TEXT NOT NULL,
    end_time        TEXT NOT NULL,
    rows_imported   INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'completed',
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
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

    def insert_candles_batch(
        self,
        candles: list[CollectedCandle],
        *,
        skip_existing: bool = True,
    ) -> int:
        """Batch insert with duplicate prevention."""
        if not candles:
            return 0
        inserted = 0
        with self._connect() as conn:
            cur = conn.cursor()
            for c in candles:
                if self._use_postgres:
                    conflict = "DO NOTHING" if skip_existing else "DO UPDATE SET open=EXCLUDED.open"
                    cur.execute(
                        f"""INSERT INTO dc_candles
                           (symbol, timeframe, timestamp, open, high, low, close, volume, provider, created_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (symbol, timeframe, timestamp) {conflict}""",
                        (c.symbol, c.timeframe.value, c.timestamp,
                         c.open, c.high, c.low, c.close, c.volume, c.provider, c.created_at),
                    )
                    if cur.rowcount > 0:
                        inserted += 1
                else:
                    if skip_existing:
                        cur.execute(
                            """INSERT OR IGNORE INTO dc_candles
                               (symbol, timeframe, timestamp, open, high, low, close, volume, provider, created_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (c.symbol, c.timeframe.value, c.timestamp.isoformat(),
                             c.open, c.high, c.low, c.close, c.volume, c.provider, c.created_at.isoformat()),
                        )
                    else:
                        cur.execute(
                            """INSERT OR REPLACE INTO dc_candles
                               (symbol, timeframe, timestamp, open, high, low, close, volume, provider, created_at)
                               VALUES (?,?,?,?,?,?,?,?,?,?)""",
                            (c.symbol, c.timeframe.value, c.timestamp.isoformat(),
                             c.open, c.high, c.low, c.close, c.volume, c.provider, c.created_at.isoformat()),
                        )
                    if cur.rowcount > 0:
                        inserted += 1
        return inserted

    @contextmanager
    def transaction(self) -> Generator[Any, None, None]:
        """Transactional import wrapper."""
        with self._connect() as conn:
            yield conn

    def get_existing_timestamps(
        self,
        symbol: str,
        timeframe: Timeframe,
        start: datetime,
        end: datetime,
    ) -> set[datetime]:
        ph = "%s" if self._use_postgres else "?"
        start_v = start if self._use_postgres else start.isoformat()
        end_v = end if self._use_postgres else end.isoformat()
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""SELECT timestamp FROM dc_candles
                    WHERE symbol = {ph} AND timeframe = {ph}
                    AND timestamp >= {ph} AND timestamp <= {ph}""",
                (symbol.upper(), timeframe.value, start_v, end_v),
            )
            rows = cur.fetchall()
        result: set[datetime] = set()
        for row in rows:
            ts = row["timestamp"] if isinstance(row, dict) else row[0]
            if isinstance(ts, str):
                ts = datetime.fromisoformat(ts)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            result.add(ts)
        return result

    def count_candles(self) -> int:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) AS cnt FROM dc_candles")
            row = cur.fetchone()
        return int(row["cnt"] if isinstance(row, dict) else row[0])

    def store_gaps(self, gaps: list[DataGap]) -> list[DataGap]:
        stored: list[DataGap] = []
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            cur = conn.cursor()
            for gap in gaps:
                exp = gap.expected_timestamp
                gs = gap.gap_start
                ge = gap.gap_end
                if self._use_postgres:
                    cur.execute(
                        """INSERT INTO dc_gaps
                           (symbol, timeframe, gap_type, expected_timestamp, gap_start, gap_end,
                            status, provider, created_at)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                        (gap.symbol, gap.timeframe.value, gap.gap_type.value,
                         exp, gs, ge, gap.status.value, gap.provider, now),
                    )
                    row = cur.fetchone()
                    gap.id = row["id"]
                else:
                    cur.execute(
                        """INSERT INTO dc_gaps
                           (symbol, timeframe, gap_type, expected_timestamp, gap_start, gap_end,
                            status, provider, created_at)
                           VALUES (?,?,?,?,?,?,?,?,?)""",
                        (gap.symbol, gap.timeframe.value, gap.gap_type.value,
                         exp.isoformat() if exp else None,
                         gs.isoformat() if gs else None,
                         ge.isoformat() if ge else None,
                         gap.status.value, gap.provider, now.isoformat()),
                    )
                    gap.id = cur.lastrowid
                gap.created_at = now
                stored.append(gap)
        return stored

    def get_open_gaps(
        self,
        symbol: Optional[str] = None,
        timeframe: Optional[Timeframe] = None,
        limit: int = 100,
    ) -> list[DataGap]:
        query = "SELECT * FROM dc_gaps WHERE status = ?"
        params: list[Any] = [GapStatus.OPEN.value]
        if symbol:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        if timeframe:
            query += " AND timeframe = ?"
            params.append(timeframe.value)
        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        if self._use_postgres:
            query = query.replace("?", "%s")
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
        return [self._row_to_gap(r) for r in rows]

    def update_gap_status(self, gap: DataGap, status: GapStatus) -> None:
        now = datetime.now(timezone.utc)
        ph = "%s" if self._use_postgres else "?"
        repaired = now if status == GapStatus.REPAIRED else None
        with self._connect() as conn:
            cur = conn.cursor()
            if gap.id:
                cur.execute(
                    f"UPDATE dc_gaps SET status = {ph}, repaired_at = {ph} WHERE id = {ph}",
                    (status.value, repaired, gap.id),
                )
            elif gap.expected_timestamp:
                exp = gap.expected_timestamp if self._use_postgres else gap.expected_timestamp.isoformat()
                cur.execute(
                    f"""UPDATE dc_gaps SET status = {ph}, repaired_at = {ph}
                        WHERE symbol = {ph} AND timeframe = {ph}
                        AND expected_timestamp = {ph} AND status = {ph}""",
                    (status.value, repaired, gap.symbol, gap.timeframe.value, exp, GapStatus.OPEN.value),
                )
        gap.status = status
        gap.repaired_at = repaired

    def log_import_job(
        self,
        symbol: str,
        timeframe: Timeframe,
        range_label: str,
        start: datetime,
        end: datetime,
        rows_imported: int,
        status: str,
    ) -> int:
        now = datetime.now(timezone.utc)
        with self._connect() as conn:
            cur = conn.cursor()
            if self._use_postgres:
                cur.execute(
                    """INSERT INTO dc_import_jobs
                       (symbol, timeframe, range_label, start_time, end_time, rows_imported, status, created_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (symbol.upper(), timeframe.value, range_label, start, end, rows_imported, status, now),
                )
                return cur.fetchone()["id"]
            cur.execute(
                """INSERT INTO dc_import_jobs
                   (symbol, timeframe, range_label, start_time, end_time, rows_imported, status, created_at)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (symbol.upper(), timeframe.value, range_label,
                 start.isoformat(), end.isoformat(), rows_imported, status, now.isoformat()),
            )
            return cur.lastrowid or 0

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
                       (provider, state, sync_status, connected, last_update, last_successful_sync,
                        last_candle_timestamp, rows_collected, rows_downloaded, rows_rejected,
                        rows_repaired, latency_ms, sync_latency_ms, message, updated_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (provider) DO UPDATE SET
                         state=EXCLUDED.state, sync_status=EXCLUDED.sync_status,
                         connected=EXCLUDED.connected, last_update=EXCLUDED.last_update,
                         last_successful_sync=EXCLUDED.last_successful_sync,
                         last_candle_timestamp=EXCLUDED.last_candle_timestamp,
                         rows_collected=EXCLUDED.rows_collected,
                         rows_downloaded=EXCLUDED.rows_downloaded,
                         rows_rejected=EXCLUDED.rows_rejected,
                         rows_repaired=EXCLUDED.rows_repaired,
                         latency_ms=EXCLUDED.latency_ms, sync_latency_ms=EXCLUDED.sync_latency_ms,
                         message=EXCLUDED.message, updated_at=EXCLUDED.updated_at""",
                    (status.provider, status.state.value, status.sync_status.value,
                     status.connected, status.last_update, status.last_successful_sync,
                     status.last_candle_timestamp, status.rows_collected, status.rows_downloaded,
                     status.rows_rejected, status.rows_repaired, status.latency_ms,
                     status.sync_latency_ms, status.message, now),
                )
            else:
                cur.execute(
                    """INSERT OR REPLACE INTO dc_provider_status
                       (provider, state, sync_status, connected, last_update, last_successful_sync,
                        last_candle_timestamp, rows_collected, rows_downloaded, rows_rejected,
                        rows_repaired, latency_ms, sync_latency_ms, message, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (status.provider, status.state.value, status.sync_status.value,
                     int(status.connected),
                     status.last_update.isoformat() if status.last_update else None,
                     status.last_successful_sync.isoformat() if status.last_successful_sync else None,
                     status.last_candle_timestamp.isoformat() if status.last_candle_timestamp else None,
                     status.rows_collected, status.rows_downloaded, status.rows_rejected,
                     status.rows_repaired, status.latency_ms, status.sync_latency_ms,
                     status.message, now.isoformat()),
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

    def _row_to_gap(self, row: Any) -> DataGap:
        from services.data_collector.models import GapType

        if isinstance(row, sqlite3.Row):
            row = dict(row)

        def _ts(val: Any) -> Optional[datetime]:
            if val is None:
                return None
            if isinstance(val, str):
                return datetime.fromisoformat(val)
            return val

        return DataGap(
            id=row.get("id"),
            symbol=row["symbol"],
            timeframe=Timeframe(row["timeframe"]),
            gap_type=GapType(row["gap_type"]),
            expected_timestamp=_ts(row.get("expected_timestamp")),
            gap_start=_ts(row.get("gap_start")),
            gap_end=_ts(row.get("gap_end")),
            status=GapStatus(row.get("status", GapStatus.OPEN.value)),
            provider=row.get("provider", "") or "",
            created_at=_ts(row.get("created_at")),
            repaired_at=_ts(row.get("repaired_at")),
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

        sync_raw = row.get("sync_status", SyncStatus.UNKNOWN.value)
        try:
            sync_status = SyncStatus(sync_raw)
        except ValueError:
            sync_status = SyncStatus.UNKNOWN

        return ProviderHealthStatus(
            provider=row["provider"],
            state=ProviderState(row["state"]),
            connected=bool(row["connected"]),
            sync_status=sync_status,
            last_update=_parse_ts(row.get("last_update")),
            last_successful_sync=_parse_ts(row.get("last_successful_sync")),
            last_candle_timestamp=_parse_ts(row.get("last_candle_timestamp")),
            rows_collected=int(row.get("rows_collected", 0)),
            rows_downloaded=int(row.get("rows_downloaded", 0)),
            rows_rejected=int(row.get("rows_rejected", 0)),
            rows_repaired=int(row.get("rows_repaired", 0)),
            latency_ms=row.get("latency_ms"),
            sync_latency_ms=row.get("sync_latency_ms"),
            message=row.get("message", "") or "",
        )

_db: Optional[CollectorDatabase] = None


def get_collector_database(url: Optional[str] = None) -> CollectorDatabase:
    global _db
    if url is not None:
        return CollectorDatabase(url)
    if _db is not None:
        return _db

    cfg = get_collector_config()
    explicit = cfg.database.url or os.getenv("COLLECTOR_DATABASE_URL", "")

    candidates: list[str] = []
    if explicit and explicit not in ("sqlite:", "sqlite"):
        candidates.append(explicit)
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("postgresql") and db_url not in candidates:
        candidates.append(db_url)

    for candidate in candidates:
        if not candidate.startswith("postgresql"):
            continue
        try:
            _db = CollectorDatabase(url=candidate)
            return _db
        except Exception:
            continue

    _db = CollectorDatabase(force_sqlite=True)
    return _db

def reset_collector_database() -> None:
    global _db
    _db = None
