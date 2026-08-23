-- Additive migration: persist causal market-structure events for replay/audit.
-- Populated from StructureSnapshot.events — does not replace in-memory analysis.

CREATE TABLE IF NOT EXISTS market_structure_events (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    event_id                VARCHAR(128) NOT NULL,
    symbol                  VARCHAR(16) NOT NULL,
    timeframe               timeframe NOT NULL,
    event_type              VARCHAR(16) NOT NULL,  -- BOS | CHOCH
    direction               VARCHAR(16) NOT NULL,  -- bullish | bearish
    scope                   VARCHAR(16) NOT NULL,  -- EXTERNAL | INTERNAL
    timestamp               TIMESTAMPTZ NOT NULL,  -- break candle time
    price                   DECIMAL(18, 8) NOT NULL, -- broken level price
    break_close             DECIMAL(18, 8),
    break_index             INTEGER,
    related_swing_id        VARCHAR(128),
    related_event_id        VARCHAR(128),
    prior_bias              VARCHAR(16),
    resulting_bias          VARCHAR(16),
    pending_bias            VARCHAR(16),
    is_continuation         BOOLEAN NOT NULL DEFAULT FALSE,
    swing_engine_version    VARCHAR(32) NOT NULL,
    structure_engine_version VARCHAR(32) NOT NULL DEFAULT '1.0.0',
    metadata                JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (symbol, timeframe, event_id, swing_engine_version)
);

CREATE INDEX IF NOT EXISTS idx_market_structure_events_lookup
    ON market_structure_events (symbol, timeframe, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_market_structure_events_type
    ON market_structure_events (symbol, timeframe, event_type, direction);
