# Technical Design Document — IoT Telemetry System

## 1. What Was Built

This document describes the **working vertical slice** of the IoT telemetry system. It is a self-contained, Dockerised backend + frontend that demonstrates the full data path: device → API → database → alert engine → WebSocket → browser.

---

## 2. Technology Choices

| Component | Choice | Rationale |
|---|---|---|
| **Language** | Python 3.12 | Strong async ecosystem; Pydantic for strict validation |
| **Framework** | FastAPI | Native async, built-in WebSocket, OpenAPI docs auto-generated |
| **Database** | SQLite (via `sqlite3`) | Zero-dependency local dev; same SQL semantics as PostgreSQL |
| **Containerisation** | Docker + Compose | Reproducible one-command setup |
| **Frontend** | React + Vite | Real-time dashboard and MQTT device simulator |

### Production Upgrade Path
- SQLite → **TimescaleDB** (time-series, compression, continuous aggregates)
- In-process WebSocket → **Redis Pub/Sub** fan-out (multi-pod WebSocket workers)
- HTTP ingestion → **MQTT broker (EMQX) bridging into Apache Kafka**

---

## 3. Implementation Summary

### 3.1 `POST /telemetry` flow

1. FastAPI deserialises JSON body into a `dict`.
2. Pydantic `TelemetryPayload` validates all fields (types, ranges, enum values).
3. SQLite `UNIQUE(device_id, timestamp)` — duplicate returns `409 Conflict`.
4. `device_latest` table is upserted (only if the new timestamp is ≥ current).
5. `alert_engine.evaluate()` runs all 4 rules; any fired alerts are persisted.
6. `ConnectionManager.broadcast()` pushes the reading + alerts to all WebSocket clients.
7. `201 Created` returned with alert summary.

### 3.2 Idempotency

The `UNIQUE(device_id, timestamp)` constraint on `telemetry_readings` makes `POST /telemetry` safe to retry. An exact duplicate returns `409` without re-inserting or re-alerting or re-broadcasting.

### 3.3 Late Event Handling

`upsert_latest` uses `WHERE excluded.timestamp >= device_latest.timestamp` — a late-arriving event (older timestamp) will NOT overwrite the more recent snapshot.

### 3.4 Alert Engine

Four stateless pure functions evaluated in sequence. Each returns `[(alert_type, message)]` or `[]`. Isolated: one rule crash cannot affect others. New rules = append a function to `_RULES`.

### 3.5 WebSocket

`ConnectionManager` holds a `list[WebSocket]`. On `broadcast()`, dead connections are pruned automatically. Clients automatically reconnect using React hooks on the frontend.

---

## 4. Alert Rules

| # | Rule | Threshold | Alert Type |
|---|---|---|---|
| 1 | Temperature threshold | > 35 °C | `HIGH_TEMPERATURE` |
| 2 | Energy spike | > 10 kWh | `ENERGY_SPIKE` |
| 3 | Device not online | `status != online` | `DEVICE_OFFLINE` |
| 4 | Suspicious readings | Voltage ∉ [180, 270] V or Current > 20 A | `SUSPICIOUS_READING` |

---

## 5. Project Structure

```
iot_telemetry/
├── backend/
│   ├── main.py          ← FastAPI app, routes, WebSocket manager
│   ├── database.py      ← SQLite init, CRUD helpers
│   ├── models.py        ← Pydantic validation models
│   ├── alerts.py        ← Pluggable alert rule engine
│   ├── schema.sql       ← Schema reference (DDL)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/             ← React source code (Dashboard & Simulator)
│   ├── package.json     ← Dependencies (React, MQTT, etc.)
│   ├── vite.config.js   ← Vite configuration
│   └── Dockerfile
├── mosquitto/
│   └── mosquitto.conf   ← MQTT broker config with WebSockets
├── docs/
│   ├── HLD.md           ← High-Level Design
│   ├── LLD.md           ← Low-Level Design
│   └── TECHNICAL_DESIGN.md (this file)
├── docker-compose.yml
└── README.md
```

---

## 6. AI-Assisted Coding

AI (Antigravity / Gemini) was used throughout this implementation. The following table documents where AI was used, what was generated, and how it was validated.

| Area | AI Contribution | Review / Validation |
|---|---|---|
| `database.py` | Generated SQLite context manager, WAL pragma, all CRUD helpers | Reviewed UNIQUE constraint placement; verified `WHERE excluded.timestamp >= device_latest.timestamp` for correct late-event semantics |
| `models.py` | Generated Pydantic v2 field validators with `@field_validator` | Cross-checked validator syntax against Pydantic v2 docs; tested edge cases (negative energy, temp > 100) |
| `alerts.py` | Generated 4 rule functions and the `evaluate()` dispatcher | Verified each threshold is configurable via constants at the top of the file |
| `main.py` | Generated `ConnectionManager`, all route handlers, lifespan hook | Reviewed broadcast error handling (dead socket pruning); verified 409 duplicate path |
| `docker-compose.yml` | Generated healthcheck + named volume config | Verified healthcheck command works with Python stdlib only (no curl dependency) |
| React UI | Generated WebSocket client and MQTT simulator with `mqtt.js` | Manually tested reconnect behaviour; verified simulator can publish correctly |
| HLD / LLD / README | Generated architecture diagrams, API contracts, setup instructions | Reviewed for accuracy against actual implementation; corrected any drift |

**Validation methodology**: Each generated code block was tested by running the Docker stack end-to-end and exercising all API endpoints with the sample `curl` commands in the README.

---

## 7. Production Roadmap

| Priority | Enhancement |
|---|---|
| High | Replace SQLite with TimescaleDB; add Alembic migrations |
| High | Transition Mosquitto to EMQX cluster + Kafka bridge setup |
| High | JWT/API-key authentication on all endpoints |
| Medium | Redis Pub/Sub for cross-pod WebSocket fan-out |
| Medium | Prometheus `/metrics` endpoint + Grafana dashboard |
| Medium | Rate limiting per device (1 reading/sec) |
| Low | Alert deduplication (suppress repeat alerts within 5 min) |
| Low | Historical chart UI (Chart.js) |
