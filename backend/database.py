import sqlite3
import os
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "/app/data/telemetry.db")


def get_db_path() -> str:
    """Return DB path, ensuring directory exists."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    return DB_PATH


@contextmanager
def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    """Create tables if they don't exist."""
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS telemetry_readings (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id       TEXT    NOT NULL,
                timestamp       TEXT    NOT NULL,
                temperature     REAL    NOT NULL,
                energy          REAL    NOT NULL,
                voltage         REAL    NOT NULL,
                current         REAL    NOT NULL,
                status          TEXT    NOT NULL,
                received_at     TEXT    NOT NULL DEFAULT (datetime('now')),
                UNIQUE(device_id, timestamp)        -- idempotency guard
            );

            CREATE INDEX IF NOT EXISTS idx_readings_device
                ON telemetry_readings(device_id);
            CREATE INDEX IF NOT EXISTS idx_readings_ts
                ON telemetry_readings(timestamp);

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

            CREATE TABLE IF NOT EXISTS alerts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                device_id       TEXT    NOT NULL,
                alert_type      TEXT    NOT NULL,
                message         TEXT    NOT NULL,
                reading_ts      TEXT    NOT NULL,
                created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_alerts_device
                ON alerts(device_id);
        """)


def insert_reading(payload: dict) -> bool:
    """
    Insert a new telemetry reading. Returns True if inserted, False if duplicate.
    """
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO telemetry_readings
                    (device_id, timestamp, temperature, energy, voltage, current, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload["deviceId"],
                    payload["timestamp"],
                    payload["temperature"],
                    payload["energyConsumption"],
                    payload["voltage"],
                    payload["current"],
                    payload["status"],
                ),
            )
            return True
        except sqlite3.IntegrityError:
            return False  # duplicate (same device_id + timestamp)


def upsert_latest(payload: dict):
    """Keep track of the most recent reading per device."""
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO device_latest
                (device_id, timestamp, temperature, energy, voltage, current, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
            ON CONFLICT(device_id) DO UPDATE SET
                timestamp   = excluded.timestamp,
                temperature = excluded.temperature,
                energy      = excluded.energy,
                voltage     = excluded.voltage,
                current     = excluded.current,
                status      = excluded.status,
                updated_at  = excluded.updated_at
            WHERE excluded.timestamp >= device_latest.timestamp
            """,
            (
                payload["deviceId"],
                payload["timestamp"],
                payload["temperature"],
                payload["energyConsumption"],
                payload["voltage"],
                payload["current"],
                payload["status"],
            ),
        )


def insert_alert(device_id: str, alert_type: str, message: str, reading_ts: str):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO alerts (device_id, alert_type, message, reading_ts)
            VALUES (?, ?, ?, ?)
            """,
            (device_id, alert_type, message, reading_ts),
        )


def get_latest(device_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM device_latest WHERE device_id = ?", (device_id,)
        ).fetchone()
        return dict(row) if row else None


def get_alerts(device_id: str | None = None, limit: int = 100) -> list[dict]:
    with get_connection() as conn:
        if device_id:
            rows = conn.execute(
                "SELECT * FROM alerts WHERE device_id = ? ORDER BY created_at DESC LIMIT ?",
                (device_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM alerts ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]


def get_summary(device_id: str) -> dict | None:
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT
                device_id,
                COUNT(*)                   AS total_readings,
                MIN(temperature)           AS min_temp,
                MAX(temperature)           AS max_temp,
                AVG(temperature)           AS avg_temp,
                MIN(energy)                AS min_energy,
                MAX(energy)                AS max_energy,
                AVG(energy)                AS avg_energy,
                MIN(voltage)               AS min_voltage,
                MAX(voltage)               AS max_voltage,
                AVG(voltage)               AS avg_voltage,
                MIN(current)               AS min_current,
                MAX(current)               AS max_current,
                AVG(current)               AS avg_current,
                MIN(timestamp)             AS first_seen,
                MAX(timestamp)             AS last_seen
            FROM telemetry_readings
            WHERE device_id = ?
            GROUP BY device_id
            """,
            (device_id,),
        ).fetchone()
        return dict(row) if row else None
