-- Additive migration: Liquidity Engine v1 pools and sweeps.

CREATE TABLE IF NOT EXISTS liquidity_pools (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    pool_id                 VARCHAR(256) NOT NULL,
    symbol                  VARCHAR(16) NOT NULL,
    timeframe               timeframe NOT NULL,
    source_timeframe        VARCHAR(8) NOT NULL,
    pool_type               VARCHAR(32) NOT NULL,
    side                    VARCHAR(16) NOT NULL,
    price                   DECIMAL(18, 8) NOT NULL,
    scope                   VARCHAR(32),
    status                  VARCHAR(16) NOT NULL,
    strength                VARCHAR(16) NOT NULL,
    strength_score          DECIMAL(8, 4),
    touches                 INTEGER NOT NULL DEFAULT 1,
    source_timestamp        TIMESTAMPTZ,
    available_timestamp     TIMESTAMPTZ,
    created_index           INTEGER,
    available_index         INTEGER,
    source_reference        VARCHAR(256),
    algorithm_version       VARCHAR(32) NOT NULL DEFAULT '1.0.0',
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (symbol, timeframe, pool_id, algorithm_version)
);

CREATE INDEX IF NOT EXISTS idx_liquidity_pools_lookup
    ON liquidity_pools (symbol, timeframe, status, price);

CREATE TABLE IF NOT EXISTS liquidity_sweeps (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    sweep_id                VARCHAR(256) NOT NULL,
    symbol                  VARCHAR(16) NOT NULL,
    timeframe               timeframe NOT NULL,
    kind                    VARCHAR(16) NOT NULL,
    pool_id                 VARCHAR(256) NOT NULL,
    pool_type               VARCHAR(32),
    level_price             DECIMAL(18, 8) NOT NULL,
    bar_index               INTEGER,
    timestamp               TIMESTAMPTZ,
    penetration             DECIMAL(18, 8),
    penetration_atr         DECIMAL(12, 6),
    rejection_pct           DECIMAL(8, 2),
    grade                   VARCHAR(16) NOT NULL,
    bias_quality            VARCHAR(16),
    algorithm_version       VARCHAR(32) NOT NULL DEFAULT '1.0.0',
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (symbol, timeframe, sweep_id, algorithm_version)
);

CREATE INDEX IF NOT EXISTS idx_liquidity_sweeps_lookup
    ON liquidity_sweeps (symbol, timeframe, timestamp DESC);
