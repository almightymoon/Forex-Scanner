-- FX Navigators Scanner — Database Schema
-- PostgreSQL 16 + TimescaleDB

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- =============================================================================
-- ENUMS
-- =============================================================================

CREATE TYPE subscription_plan AS ENUM ('guest', 'free', 'pro', 'elite', 'admin');
CREATE TYPE signal_direction AS ENUM ('buy', 'sell', 'neutral');
CREATE TYPE trend_direction AS ENUM ('bullish', 'bearish', 'ranging');
CREATE TYPE risk_level AS ENUM ('low', 'medium', 'high', 'extreme');
CREATE TYPE confidence_rating AS ENUM ('ignore', 'moderate', 'good', 'strong', 'elite');
CREATE TYPE timeframe AS ENUM ('M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1');
CREATE TYPE alert_delivery AS ENUM ('push', 'email', 'telegram', 'discord', 'sms', 'webhook');
CREATE TYPE news_impact AS ENUM ('low', 'medium', 'high');
CREATE TYPE symbol_category AS ENUM ('major', 'minor', 'exotic', 'metal', 'commodity', 'index', 'crypto');

-- =============================================================================
-- USERS & AUTH
-- =============================================================================

CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            VARCHAR(255) NOT NULL,
    email           VARCHAR(255) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    subscription_plan subscription_plan NOT NULL DEFAULT 'free',
    timezone        VARCHAR(64) NOT NULL DEFAULT 'UTC',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    email_verified  BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE subscriptions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan            subscription_plan NOT NULL,
    stripe_customer_id VARCHAR(255),
    stripe_subscription_id VARCHAR(255),
    status          VARCHAR(32) NOT NULL DEFAULT 'active',
    current_period_start TIMESTAMPTZ,
    current_period_end   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE api_keys (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    key_hash        VARCHAR(255) NOT NULL,
    name            VARCHAR(128) NOT NULL,
    permissions     JSONB NOT NULL DEFAULT '[]',
    last_used_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE user_settings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    min_alert_score INTEGER NOT NULL DEFAULT 80,
    default_timeframe timeframe NOT NULL DEFAULT 'H1',
    alert_delivery  alert_delivery[] NOT NULL DEFAULT '{push}',
    telegram_chat_id VARCHAR(64),
    discord_webhook_url TEXT,
    theme           VARCHAR(16) NOT NULL DEFAULT 'dark',
    dashboard_layout JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- MARKET DATA
-- =============================================================================

CREATE TABLE symbols (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol          VARCHAR(16) UNIQUE NOT NULL,
    name            VARCHAR(64) NOT NULL,
    category        symbol_category NOT NULL DEFAULT 'major',
    base_currency   VARCHAR(8) NOT NULL,
    quote_currency  VARCHAR(8) NOT NULL,
    pip_size        DECIMAL(10, 8) NOT NULL DEFAULT 0.0001,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE candles (
    symbol          VARCHAR(16) NOT NULL,
    timeframe       timeframe NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    open            DECIMAL(18, 8) NOT NULL,
    high            DECIMAL(18, 8) NOT NULL,
    low             DECIMAL(18, 8) NOT NULL,
    close           DECIMAL(18, 8) NOT NULL,
    volume          BIGINT NOT NULL DEFAULT 0,
    tick_volume     BIGINT NOT NULL DEFAULT 0,
    spread          DECIMAL(10, 5),
    PRIMARY KEY (symbol, timeframe, timestamp)
);

SELECT create_hypertable('candles', 'timestamp', if_not_exists => TRUE);

CREATE INDEX idx_candles_symbol_tf ON candles (symbol, timeframe, timestamp DESC);

CREATE TABLE ticks (
    symbol          VARCHAR(16) NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    bid             DECIMAL(18, 8) NOT NULL,
    ask             DECIMAL(18, 8) NOT NULL,
    volume          BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, timestamp)
);

SELECT create_hypertable('ticks', 'timestamp', if_not_exists => TRUE);

-- =============================================================================
-- INDICATORS
-- =============================================================================

CREATE TABLE indicators (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol          VARCHAR(16) NOT NULL,
    timeframe       timeframe NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    ema_20          DECIMAL(18, 8),
    ema_50          DECIMAL(18, 8),
    ema_200         DECIMAL(18, 8),
    sma_20          DECIMAL(18, 8),
    rsi_14          DECIMAL(8, 4),
    macd_line       DECIMAL(18, 8),
    macd_signal     DECIMAL(18, 8),
    macd_histogram  DECIMAL(18, 8),
    atr_14          DECIMAL(18, 8),
    adx_14          DECIMAL(8, 4),
    vwap            DECIMAL(18, 8),
    bb_upper        DECIMAL(18, 8),
    bb_middle       DECIMAL(18, 8),
    bb_lower        DECIMAL(18, 8),
    stoch_k         DECIMAL(8, 4),
    stoch_d         DECIMAL(8, 4),
    supertrend      DECIMAL(18, 8),
    supertrend_direction signal_direction,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (symbol, timeframe, timestamp)
);

CREATE INDEX idx_indicators_lookup ON indicators (symbol, timeframe, timestamp DESC);

-- =============================================================================
-- SMC (Smart Money Concepts)
-- =============================================================================

CREATE TABLE smc_patterns (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol          VARCHAR(16) NOT NULL,
    timeframe       timeframe NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    pattern_type    VARCHAR(32) NOT NULL, -- bos, choch, order_block, fvg, liquidity_sweep, etc.
    direction       signal_direction NOT NULL,
    price_high      DECIMAL(18, 8),
    price_low       DECIMAL(18, 8),
    strength        DECIMAL(5, 2) NOT NULL DEFAULT 0,
    metadata        JSONB NOT NULL DEFAULT '{}',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_smc_patterns_lookup ON smc_patterns (symbol, timeframe, timestamp DESC);

-- =============================================================================
-- SCANNER & SIGNALS
-- =============================================================================

CREATE TABLE scanner_results (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol          VARCHAR(16) NOT NULL,
    timeframe       timeframe NOT NULL,
    score           INTEGER NOT NULL CHECK (score >= 0 AND score <= 100),
    rating          confidence_rating NOT NULL,
    direction       signal_direction NOT NULL,
    trend           trend_direction NOT NULL,
    risk_level      risk_level NOT NULL,
    score_breakdown JSONB NOT NULL,
    technical_reasons JSONB NOT NULL DEFAULT '[]',
    smc_reasons     JSONB NOT NULL DEFAULT '[]',
    news_impact     JSONB,
    mtf_alignment   JSONB,
    entry_zone_low  DECIMAL(18, 8),
    entry_zone_high DECIMAL(18, 8),
    stop_loss       DECIMAL(18, 8),
    take_profit_1   DECIMAL(18, 8),
    take_profit_2   DECIMAL(18, 8),
    take_profit_3   DECIMAL(18, 8),
    risk_reward     DECIMAL(6, 2),
    ai_explanation  TEXT,
    is_active       BOOLEAN NOT NULL DEFAULT true,
    expires_at      TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_scanner_results_live ON scanner_results (created_at DESC) WHERE is_active = true;
CREATE INDEX idx_scanner_results_symbol ON scanner_results (symbol, timeframe, created_at DESC);

CREATE TABLE signals (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    scanner_result_id UUID REFERENCES scanner_results(id) ON DELETE SET NULL,
    symbol          VARCHAR(16) NOT NULL,
    timeframe       timeframe NOT NULL,
    direction       signal_direction NOT NULL,
    score           INTEGER NOT NULL,
    entry_price     DECIMAL(18, 8),
    stop_loss       DECIMAL(18, 8),
    take_profit     DECIMAL(18, 8),
    status          VARCHAR(32) NOT NULL DEFAULT 'active',
    outcome         VARCHAR(32), -- win, loss, breakeven, expired
    pnl_pips        DECIMAL(10, 2),
    closed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- NEWS & ECONOMIC CALENDAR
-- =============================================================================

CREATE TABLE economic_events (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    external_id     VARCHAR(128),
    currency        VARCHAR(8) NOT NULL,
    country         VARCHAR(64),
    title           VARCHAR(512) NOT NULL,
    impact          news_impact NOT NULL DEFAULT 'low',
    forecast        VARCHAR(64),
    previous        VARCHAR(64),
    actual          VARCHAR(64),
    event_time      TIMESTAMPTZ NOT NULL,
    source          VARCHAR(64) NOT NULL DEFAULT 'forexfactory',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_economic_events_time ON economic_events (event_time);
CREATE INDEX idx_economic_events_currency ON economic_events (currency, event_time);

-- =============================================================================
-- WATCHLISTS & ALERTS
-- =============================================================================

CREATE TABLE watchlists (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name            VARCHAR(128) NOT NULL DEFAULT 'Default',
    symbols         VARCHAR(16)[] NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE alerts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    symbol          VARCHAR(16),
    timeframe       timeframe,
    min_score       INTEGER NOT NULL DEFAULT 80,
    direction       signal_direction,
    rule            JSONB NOT NULL DEFAULT '{}',
    delivery_method alert_delivery[] NOT NULL DEFAULT '{push}',
    is_active       BOOLEAN NOT NULL DEFAULT true,
    last_triggered  TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE notifications (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    alert_id        UUID REFERENCES alerts(id) ON DELETE SET NULL,
    scanner_result_id UUID REFERENCES scanner_results(id) ON DELETE SET NULL,
    title           VARCHAR(255) NOT NULL,
    body            TEXT NOT NULL,
    delivery_method alert_delivery NOT NULL,
    status          VARCHAR(32) NOT NULL DEFAULT 'pending',
    sent_at         TIMESTAMPTZ,
    read_at         TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- AUDIT & ANALYTICS
-- =============================================================================

CREATE TABLE audit_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID REFERENCES users(id) ON DELETE SET NULL,
    action          VARCHAR(128) NOT NULL,
    resource_type   VARCHAR(64),
    resource_id     UUID,
    metadata        JSONB NOT NULL DEFAULT '{}',
    ip_address      INET,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE trade_history (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    signal_id       UUID REFERENCES signals(id) ON DELETE SET NULL,
    symbol          VARCHAR(16) NOT NULL,
    direction       signal_direction NOT NULL,
    entry_price     DECIMAL(18, 8) NOT NULL,
    exit_price      DECIMAL(18, 8),
    stop_loss       DECIMAL(18, 8),
    take_profit     DECIMAL(18, 8),
    lot_size        DECIMAL(10, 4),
    pnl             DECIMAL(18, 8),
    pnl_pips        DECIMAL(10, 2),
    notes           TEXT,
    opened_at       TIMESTAMPTZ NOT NULL,
    closed_at       TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =============================================================================
-- UPDATED_AT TRIGGER
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_updated_at BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER subscriptions_updated_at BEFORE UPDATE ON subscriptions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER user_settings_updated_at BEFORE UPDATE ON user_settings
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER watchlists_updated_at BEFORE UPDATE ON watchlists
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
CREATE TRIGGER alerts_updated_at BEFORE UPDATE ON alerts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
