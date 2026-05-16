-- Price Monitor WebApp - Database initialization

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    username VARCHAR(255),
    is_vip BOOLEAN DEFAULT FALSE,
    vip_expires_at TIMESTAMP,
    interests TEXT DEFAULT '[]',
    referral_code VARCHAR(64) UNIQUE,
    fcm_token VARCHAR(512),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id SERIAL PRIMARY KEY,
    marketplace VARCHAR(50) NOT NULL,
    external_id VARCHAR(255) NOT NULL,
    name VARCHAR(512) NOT NULL,
    category VARCHAR(255),
    brand VARCHAR(255),
    url TEXT,
    image_url TEXT,
    rating FLOAT DEFAULT 0.0,
    reviews_summary TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS price_history (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    price FLOAT NOT NULL,
    old_price FLOAT,
    discount_percent FLOAT,
    is_fraud BOOLEAN DEFAULT FALSE,
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS alerts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    keyword VARCHAR(255) NOT NULL,
    max_price FLOAT,
    category VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS favorites (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    amount FLOAT NOT NULL,
    currency VARCHAR(10) DEFAULT 'RUB',
    status VARCHAR(50) DEFAULT 'pending',
    plan VARCHAR(50),
    provider VARCHAR(50) NOT NULL,
    provider_payment_id VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS clicks (
    id SERIAL PRIMARY KEY,
    short_id VARCHAR(32) NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id),
    partner_id INTEGER,
    timestamp TIMESTAMP DEFAULT NOW(),
    ip VARCHAR(45),
    user_agent TEXT,
    converted BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS posts (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    channel_id BIGINT NOT NULL,
    text TEXT NOT NULL,
    variant VARCHAR(50),
    impressions INTEGER DEFAULT 0,
    clicks INTEGER DEFAULT 0,
    ctr FLOAT DEFAULT 0.0,
    published_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS short_links (
    id SERIAL PRIMARY KEY,
    short_id VARCHAR(32) UNIQUE NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    affiliate_url TEXT NOT NULL,
    partner_id INTEGER,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS push_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    sent_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS partners (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel_name VARCHAR(255) NOT NULL,
    channel_url TEXT,
    widget_code VARCHAR(64) UNIQUE NOT NULL,
    commission_percent FLOAT DEFAULT 5.0,
    total_clicks INTEGER DEFAULT 0,
    total_conversions INTEGER DEFAULT 0,
    balance FLOAT DEFAULT 0.0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS arbitrage_results (
    id SERIAL PRIMARY KEY,
    product_wb_id INTEGER REFERENCES products(id),
    product_ozon_id INTEGER REFERENCES products(id),
    product_name VARCHAR(512) NOT NULL,
    brand VARCHAR(255),
    price_wb FLOAT NOT NULL,
    price_ozon FLOAT NOT NULL,
    diff_percent FLOAT NOT NULL,
    match_score FLOAT NOT NULL,
    found_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reviews (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    author VARCHAR(255),
    text TEXT NOT NULL,
    rating INTEGER,
    is_fake BOOLEAN DEFAULT FALSE,
    fake_score FLOAT DEFAULT 0.0,
    analyzed_at TIMESTAMP DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_products_marketplace ON products(marketplace);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_price_history_product ON price_history(product_id);
CREATE INDEX IF NOT EXISTS idx_price_history_timestamp ON price_history(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_user ON alerts(user_id);
CREATE INDEX IF NOT EXISTS idx_favorites_user ON favorites(user_id);
CREATE INDEX IF NOT EXISTS idx_clicks_short_id ON clicks(short_id);
CREATE INDEX IF NOT EXISTS idx_clicks_partner ON clicks(partner_id);
CREATE INDEX IF NOT EXISTS idx_short_links_short_id ON short_links(short_id);
CREATE INDEX IF NOT EXISTS idx_partners_widget_code ON partners(widget_code);
CREATE INDEX IF NOT EXISTS idx_arbitrage_results_found_at ON arbitrage_results(found_at);

CREATE TABLE IF NOT EXISTS niche_analyses (
    id SERIAL PRIMARY KEY,
    category VARCHAR(255) NOT NULL,
    growth_percent FLOAT NOT NULL,
    avg_price FLOAT,
    product_count INTEGER DEFAULT 0,
    recommendation TEXT,
    analyzed_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS seller_copies (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    title VARCHAR(512) NOT NULL,
    description TEXT NOT NULL,
    keywords TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS content_scripts (
    id SERIAL PRIMARY KEY,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    script_type VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_niche_analyses_category ON niche_analyses(category);
CREATE INDEX IF NOT EXISTS idx_seller_copies_product ON seller_copies(product_id);
CREATE INDEX IF NOT EXISTS idx_content_scripts_product ON content_scripts(product_id);
