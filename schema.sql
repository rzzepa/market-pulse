-- ═══════════════════════════════════════════════════════
--  MARKET PULSE — schemat bazy
-- ═══════════════════════════════════════════════════════

-- ─────────────── SŁOWNIKI ───────────────

CREATE TABLE regions (
    region_id   SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,   -- Europa, Azja, Bliski Wschód
    description TEXT
);

CREATE TABLE countries (
    country_id      SERIAL PRIMARY KEY,
    iso_code        CHAR(2)      NOT NULL UNIQUE,  -- PL, US, DE
    name            VARCHAR(100) NOT NULL UNIQUE,
    region_id       INT          REFERENCES regions(region_id),
    currency_code   VARCHAR(10),                   -- główna waluta ISO 4217
    languages       TEXT,                          -- "pl,en"
    gdp_influence   SMALLINT CHECK (gdp_influence BETWEEN 1 AND 5)
                    -- 1=lokalne, 5=globalne (USA, Chiny)
);

CREATE TABLE news_categories (
    category_id SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,   -- Geopolityka, Finanse, Militaria
    description TEXT
);

-- ─────────────── DANE HISTORYCZNE KRAJÓW ───────────────

CREATE TABLE country_indicators (
    indicator_id    SERIAL PRIMARY KEY,
    country_id      INT      NOT NULL REFERENCES countries(country_id),
    year            SMALLINT NOT NULL,
    population      BIGINT,
    gdp_usd         NUMERIC(20, 2),
    gdp_per_capita  NUMERIC(12, 2),
    inflation_pct   NUMERIC(6, 3),
    UNIQUE (country_id, year)
);

CREATE INDEX idx_indicators_country ON country_indicators(country_id);
CREATE INDEX idx_indicators_year    ON country_indicators(year);

-- ─────────────── RYNKI FINANSOWE ───────────────

CREATE TABLE exchange_rates (
    rate_id         SERIAL PRIMARY KEY,
    date            DATE        NOT NULL,
    currency_code   VARCHAR(10) NOT NULL,        -- EUR, USD, CHF
    rate            NUMERIC(12, 6) NOT NULL,     -- kurs średni
    source          VARCHAR(50) DEFAULT 'NBP',
    UNIQUE (date, currency_code)
);

CREATE INDEX idx_rates_date     ON exchange_rates(date);
CREATE INDEX idx_rates_currency ON exchange_rates(currency_code);

CREATE TABLE stock_prices (
    price_id    SERIAL PRIMARY KEY,
    date        DATE           NOT NULL,
    ticker      VARCHAR(20)    NOT NULL,         -- CDR.WA, AAPL, SPY
    open        NUMERIC(12, 4),
    high        NUMERIC(12, 4),
    low         NUMERIC(12, 4),
    close       NUMERIC(12, 4) NOT NULL,
    volume      BIGINT,
    adj_close   NUMERIC(12, 4),
    currency    VARCHAR(10),                     -- PLN, USD
    UNIQUE (date, ticker)
);

CREATE INDEX idx_stocks_date   ON stock_prices(date);
CREATE INDEX idx_stocks_ticker ON stock_prices(ticker);

-- ─────────────── NEWSY: WARSTWA RAW (Bronze) ───────────────

CREATE TABLE news_raw (
    raw_id          SERIAL PRIMARY KEY,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),  -- kiedy scraper złapał
    published_at    TIMESTAMPTZ,                         -- data z artykułu
    headline        VARCHAR(500) NOT NULL,
    content         TEXT,                                -- pełna treść (tymczasowo)
    url             TEXT UNIQUE,
    content_hash    CHAR(64),
    source_name     VARCHAR(200),
    status          VARCHAR(20) DEFAULT 'pending',       -- pending/processed/skipped
    processed_at    TIMESTAMPTZ
);

CREATE INDEX idx_raw_status ON news_raw(status);
CREATE UNIQUE INDEX idx_raw_hash
    ON news_raw(content_hash) WHERE content_hash IS NOT NULL;

-- ─────────────── NEWSY: WARSTWA CURATED (Silver) ───────────────

CREATE TABLE news_events (
    event_id        SERIAL PRIMARY KEY,
    published_at    TIMESTAMPTZ  NOT NULL,       -- data publikacji artykułu
    event_date      DATE,                        -- data faktycznego wydarzenia
    headline        VARCHAR(500) NOT NULL,
    summary         TEXT,                        -- streszczenie AI
    url             TEXT UNIQUE,
    content_hash    CHAR(64),
    source_name     VARCHAR(200),
    importance      SMALLINT CHECK (importance BETWEEN 1 AND 5),
    sentiment       NUMERIC(4, 3) CHECK (sentiment BETWEEN -1 AND 1),
    is_duplicate    BOOLEAN DEFAULT FALSE,
    duplicate_of    INT REFERENCES news_events(event_id),
    ai_analysed_at  TIMESTAMPTZ
);

CREATE UNIQUE INDEX idx_news_hash
    ON news_events(content_hash) WHERE content_hash IS NOT NULL;
CREATE INDEX idx_news_published  ON news_events(published_at);
CREATE INDEX idx_news_event_date ON news_events(event_date);
CREATE INDEX idx_news_importance ON news_events(importance);

-- ─────────────── TABELE ŁĄCZNIKOWE (wiele-do-wielu) ───────────────

CREATE TABLE news_countries (
    event_id    INT NOT NULL REFERENCES news_events(event_id),
    country_id  INT NOT NULL REFERENCES countries(country_id),
    PRIMARY KEY (event_id, country_id)
);

CREATE TABLE news_categories_map (
    event_id    INT NOT NULL REFERENCES news_events(event_id),
    category_id INT NOT NULL REFERENCES news_categories(category_id),
    PRIMARY KEY (event_id, category_id)
);

CREATE TABLE news_tickers (
    event_id    INT NOT NULL REFERENCES news_events(event_id),
    ticker      VARCHAR(20) NOT NULL,            -- AAPL, CDR.WA, EUR
    PRIMARY KEY (event_id, ticker)
);