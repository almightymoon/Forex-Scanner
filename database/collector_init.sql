-- FX Navigators — Collector tables (PostgreSQL-compatible)
-- Mounted after main schema.sql in docker-compose

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

CREATE INDEX IF NOT EXISTS idx_dc_candles_lookup ON dc_candles (symbol, timeframe, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_dc_candles_symbol ON dc_candles (symbol);
CREATE INDEX IF NOT EXISTS idx_dc_candles_timeframe ON dc_candles (timeframe);
CREATE INDEX IF NOT EXISTS idx_dc_candles_timestamp ON dc_candles (timestamp DESC);

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
