-- Additive migration: persist versioned swing detections for replay/audit.
-- Safe to run on existing databases that already have schema.sql without swings.

CREATE TABLE IF NOT EXISTS swings (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol                  VARCHAR(16) NOT NULL,
    timeframe               timeframe NOT NULL,
    swing_type              VARCHAR(32) NOT NULL,
    direction               VARCHAR(8) NOT NULL,
    price                   DECIMAL(18, 8) NOT NULL,
    source_timestamp        TIMESTAMPTZ NOT NULL,
    confirmation_timestamp  TIMESTAMPTZ,
    pivot_index             INTEGER,
    confirmation_index      INTEGER,
    confirmation_delay      INTEGER,
    strength                INTEGER NOT NULL DEFAULT 1,
    score                   DECIMAL(12, 4),
    confidence              DECIMAL(8, 4),
    quality_score           DECIMAL(8, 4),
    confirmed               BOOLEAN NOT NULL DEFAULT FALSE,
    algorithm_version       VARCHAR(32) NOT NULL,
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (symbol, timeframe, algorithm_version, source_timestamp, direction)
);

CREATE INDEX IF NOT EXISTS idx_swings_lookup
    ON swings (symbol, timeframe, algorithm_version, source_timestamp DESC);
