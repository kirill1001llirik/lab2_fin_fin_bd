PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cities (
    city_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    foundation_date TEXT NOT NULL,
    population INTEGER NOT NULL CHECK (population >= 0),
    area_km2 NUMERIC(12, 2) NOT NULL CHECK (CAST(area_km2 AS REAL) >= 0),
    description TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id INTEGER,
    name TEXT NOT NULL,
    inn TEXT NOT NULL,
    contract_date TEXT NOT NULL,
    employees_count INTEGER NOT NULL CHECK (employees_count >= 0),
    annual_budget NUMERIC(14, 2) NOT NULL CHECK (CAST(annual_budget AS REAL) >= 0),
    address TEXT NOT NULL,
    comment TEXT NOT NULL,
    is_deleted INTEGER NOT NULL DEFAULT 0 CHECK (is_deleted IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (city_id) REFERENCES cities(city_id) ON UPDATE CASCADE ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS city_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL CHECK (operation IN ('UPDATE', 'DELETE')),
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    city_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    country TEXT NOT NULL,
    foundation_date TEXT NOT NULL,
    population INTEGER NOT NULL,
    area_km2 NUMERIC(12, 2) NOT NULL,
    description TEXT NOT NULL,
    is_deleted INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS supplier_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL CHECK (operation IN ('UPDATE', 'DELETE')),
    changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    supplier_id INTEGER NOT NULL,
    city_id INTEGER,
    name TEXT NOT NULL,
    inn TEXT NOT NULL,
    contract_date TEXT NOT NULL,
    employees_count INTEGER NOT NULL,
    annual_budget NUMERIC(14, 2) NOT NULL,
    address TEXT NOT NULL,
    comment TEXT NOT NULL,
    is_deleted INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cities_active_name ON cities(is_deleted, name, country);
CREATE INDEX IF NOT EXISTS idx_suppliers_active_name ON suppliers(is_deleted, name);
CREATE INDEX IF NOT EXISTS idx_suppliers_city_id ON suppliers(city_id);
