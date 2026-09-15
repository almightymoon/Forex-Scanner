-- Additive migration: validation outcome store (replaces file-backed JSON for multi-host safety).

CREATE TABLE IF NOT EXISTS validation_outcomes (
    id              VARCHAR(64) PRIMARY KEY,
    symbol          VARCHAR(16) NOT NULL,
    timeframe       VARCHAR(8) NOT NULL,
    direction       VARCHAR(16) NOT NULL,
    score           INTEGER NOT NULL,
    confidence      DOUBLE PRECISION NOT NULL,
    entry_price     DECIMAL(18, 8) NOT NULL,
    stop_loss       DECIMAL(18, 8) NOT NULL,
    take_profit     DECIMAL(18, 8) NOT NULL,
    patterns        JSONB NOT NULL DEFAULT '[]'::jsonb,
    outcome         VARCHAR(32),
    pnl_pips        DECIMAL(12, 4) NOT NULL DEFAULT 0,
    exit_price      DECIMAL(18, 8),
    created_at      TIMESTAMPTZ NOT NULL,
    closed_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_validation_outcomes_symbol_created
    ON validation_outcomes (symbol, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_validation_outcomes_open
    ON validation_outcomes (symbol, created_at DESC)
    WHERE outcome IS NULL;

CREATE INDEX IF NOT EXISTS idx_validation_outcomes_closed
    ON validation_outcomes (created_at DESC)
    WHERE outcome IS NOT NULL;
