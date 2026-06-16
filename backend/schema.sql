-- ============================================================
-- IoT Telemetry System — SQLite Schema Reference
-- ============================================================

-- All historical telemetry readings.
-- UNIQUE(device_id, timestamp) acts as an idempotency guard:
-- duplicate ingestion of the same event is silently ignored.
CREATE TABLE IF NOT EXISTS telemetry_readings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT    NOT NULL,
    timestamp       TEXT    NOT NULL,           -- ISO 8601 from device
    temperature     REAL    NOT NULL,           -- °C
    energy          REAL    NOT NULL,           -- kWh
    voltage         REAL    NOT NULL,           -- V
    current         REAL    NOT NULL,           -- A
    status          TEXT    NOT NULL,           -- online | offline | error
    received_at     TEXT    NOT NULL DEFAULT (datetime('now')),

    UNIQUE(device_id, timestamp)
);

CREATE INDEX IF NOT EXISTS idx_readings_device ON telemetry_readings(device_id);
CREATE INDEX IF NOT EXISTS idx_readings_ts     ON telemetry_readings(timestamp);

-- Latest snapshot per device (upserted on every valid reading).
-- Enables O(1) lookup of current device state.
CREATE TABLE IF NOT EXISTS device_latest (
    device_id       TEXT    PRIMARY KEY,
    timestamp       TEXT    NOT NULL,
    temperature     REAL    NOT NULL,
    energy          REAL    NOT NULL,
    voltage         REAL    NOT NULL,
    current         REAL    NOT NULL,
    status          TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- Alert log — one row per triggered alert rule.
CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id       TEXT    NOT NULL,
    alert_type      TEXT    NOT NULL,   -- HIGH_TEMPERATURE | ENERGY_SPIKE | DEVICE_OFFLINE | SUSPICIOUS_READING
    message         TEXT    NOT NULL,
    reading_ts      TEXT    NOT NULL,   -- timestamp of the reading that triggered this alert
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_alerts_device ON alerts(device_id);
