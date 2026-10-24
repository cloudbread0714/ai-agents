-- Seed data for the practice database (compose and kind use this same file).
CREATE TABLE IF NOT EXISTS items (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL
);
INSERT INTO items (name) VALUES ('keyboard'), ('monitor'), ('mouse');

-- 200,000 orders over 5,000 customers, for the slow-query scenario (#19).
CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_id INT NOT NULL,
    amount INT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO orders (customer_id, amount, created_at)
SELECT (g % 5000) + 1, (g * 37) % 1000 + 1, now() - (g || ' minutes')::interval
FROM generate_series(1, 200000) AS g;
CREATE INDEX IF NOT EXISTS orders_customer_idx ON orders (customer_id);
ANALYZE orders;

-- Expensive-to-build "popular" list, cached by the API (#14).
CREATE TABLE IF NOT EXISTS popular (
    id INT PRIMARY KEY,
    title TEXT NOT NULL
);
INSERT INTO popular (id, title)
SELECT g, 'popular post ' || g FROM generate_series(1, 20) AS g;
