# Low-Level Design (LLD) — IoT Telemetry System

## 1. Database Schema (SQLite — local dev)

### Table: `telemetry_readings`
Stores every ingested reading.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | Auto-increment |
| `device_id` | TEXT | Device identifier |
| `timestamp` | TEXT | ISO 8601 from device |
| `temperature` | REAL | °C |
| `energy` | REAL | kWh |
| `voltage` | REAL | V |
| `current` | REAL | A |
| `status` | TEXT | `online \| offline \| error` |
| `received_at` | TEXT | Server ingestion time (UTC) |

**Constraint**: `UNIQUE(device_id, timestamp)` — idempotency guard.
**Indexes**: `(device_id)`, `(timestamp)`.

---

### Table: `device_latest`
Latest reading snapshot per device — `O(1)` reads.

| Column | Type | Notes |
|---|---|---|
| `device_id` | TEXT PK | — |
| `timestamp` | TEXT | Latest reading timestamp |
| `temperature` | REAL | — |
| `energy` | REAL | — |
| `voltage` | REAL | — |
| `current` | REAL | — |
| `status` | TEXT | — |
| `updated_at` | TEXT | Last upsert time |

Updated via `INSERT OR REPLACE` / `ON CONFLICT DO UPDATE WHERE timestamp >= existing.timestamp` — prevents late events from overwriting newer data.

---

### Table: `alerts`
Alert event log.

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | — |
| `device_id` | TEXT | — |
| `alert_type` | TEXT | `HIGH_TEMPERATURE \| ENERGY_SPIKE \| DEVICE_OFFLINE \| SUSPICIOUS_READING` |
| `message` | TEXT | Human-readable description |
| `reading_ts` | TEXT | Timestamp of triggering reading |
| `created_at` | TEXT | Server time |

**Index**: `(device_id)`.

---

## 2. API Contract

### `POST /telemetry`

**Request body**:
```json
{
  "deviceId":           "AC-1001",
  "timestamp":          "2026-06-10T10:30:00Z",
  "temperature":        29.5,
  "energyConsumption":  4.8,
  "voltage":            230,
  "current":            6.2,
  "status":             "online"
}
```

**Validation rules**:
| Field | Rule |
|---|---|
| `deviceId` | Required, non-empty string |
| `timestamp` | Required, valid ISO 8601 |
| `temperature` | Required, float, −50 to 100 |
| `energyConsumption` | Required, float ≥ 0 |
| `voltage` | Required, float 0–500 |
| `current` | Required, float ≥ 0 |
| `status` | Required, one of `online / offline / error` |

**Responses**:

| Code | Meaning |
|---|---|
| `201` | Stored successfully |
| `409` | Duplicate (same deviceId + timestamp) |
| `422` | Validation error — body contains `validation_errors` |
| `503` | Kafka / DB unavailable (production) |

**201 Response**:
```json
{
  "status": "ok",
  "deviceId": "AC-1001",
  "timestamp": "2026-06-10T10:30:00Z",
  "alertsTriggered": 1,
  "alerts": [{ "type": "HIGH_TEMPERATURE", "message": "..." }]
}
```

---

### `GET /devices/{deviceId}/latest`

**Response 200**:
```json
{
  "status": "ok",
  "data": {
    "device_id": "AC-1001",
    "temperature": 29.5,
    "energy": 4.8,
    "voltage": 230,
    "current": 6.2,
    "status": "online",
    "timestamp": "2026-06-10T10:30:00Z",
    "updated_at": "2026-06-10T05:00:01"
  }
}
```

**Response 404**: Device not found.

---

### `GET /alerts`

Query params: `?deviceId=AC-1001&limit=50`

**Response 200**:
```json
{
  "status": "ok",
  "count": 2,
  "data": [
    {
      "id": 1,
      "device_id": "AC-1001",
      "alert_type": "HIGH_TEMPERATURE",
      "message": "Temperature 42°C exceeds threshold of 35°C",
      "reading_ts": "2026-06-10T10:31:00Z",
      "created_at": "2026-06-10T05:01:00"
    }
  ]
}
```

---

### `GET /devices/{deviceId}/summary`

**Response 200**:
```json
{
  "status": "ok",
  "data": {
    "device_id": "AC-1001",
    "total_readings": 50,
    "min_temp": 20.1, "max_temp": 42.0, "avg_temp": 29.8,
    "min_energy": 2.1, "max_energy": 12.3, "avg_energy": 5.0,
    "min_voltage": 220, "max_voltage": 240, "avg_voltage": 230,
    "min_current": 5.0, "max_current": 8.5, "avg_current": 6.2,
    "first_seen": "2026-06-10T08:00:00Z",
    "last_seen": "2026-06-10T10:31:00Z"
  }
}
```

---

## 3. Alert Engine Design

Alert rules are implemented as pure functions in `alerts.py`:

```python
def _check_temperature(payload) -> list[tuple[str, str]]:
    # returns [(alert_type, message)] or []
```

**Rules table**:

| Rule | Condition | Alert Type |
|---|---|---|
| Temperature threshold | `temperature > 35 °C` | `HIGH_TEMPERATURE` |
| Energy spike | `energyConsumption > 10 kWh` | `ENERGY_SPIKE` |
| Device offline | `status != "online"` | `DEVICE_OFFLINE` |
| Suspicious reading | `voltage ∉ [180, 270]` or `current > 20 A` | `SUSPICIOUS_READING` |

Rules are registered in a list and iterated on every ingestion. Adding a new rule = appending a function.

---

## 4. WebSocket Fan-out Mechanism

```
POST /telemetry
    │
    ├─► validate → store → alert
    │
    └─► ConnectionManager.broadcast(payload)
            │
            ├─► ws_client_1.send_json(...)
            ├─► ws_client_2.send_json(...)
            └─► ws_client_N.send_json(...)
```

- `ConnectionManager` holds a plain `list[WebSocket]`.
- `broadcast()` is `async` — sends to all clients concurrently within the request handler.
- Dead connections are cleaned up silently during broadcast.
- **Production**: Replace with a Redis Pub/Sub channel so WebSocket workers on separate pods still get all messages.

---

## 5. Data Flow — End to End

```
Device
  │  POST /telemetry JSON
  ▼
FastAPI (main.py)
  │  Pydantic validation
  ├─ 422 → return error
  │
  │  db.insert_reading() ── UNIQUE conflict ──► 409 return
  │
  │  db.upsert_latest()
  │
  │  alert_engine.evaluate()
  │    ├─ rules fire → db.insert_alert() → log
  │    └─ rules pass → no alert
  │
  │  manager.broadcast()
  │    └─ all WS clients receive JSON push
  │
  └─ 201 return { alertsTriggered, alerts }
```

---

## 6. Error Handling Strategy

| Layer | Strategy |
|---|---|
| Request | Pydantic ValidationError → `422` with field-level messages |
| Duplicate | `IntegrityError` on UNIQUE constraint → `409 Conflict` |
| DB unavailable | Unhandled exception → `500`; production: circuit breaker |
| WS broadcast failure | Individual client removed from list; others unaffected |
| Alert rule crash | Isolated try/except per rule; one failing rule doesn't block others |
