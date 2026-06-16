# IoT Telemetry System

A production-grade IoT telemetry backend with real-time WebSocket broadcasting, a pluggable alert engine, and a React live-data dashboard with an MQTT device simulator.

---

## Quick Start (Docker — Recommended)

> **Prerequisites**: Docker Engine + Docker Compose installed.

```bash
# 1. Clone / enter the project
cd iot_telemetry

# 2. Build and start all services
sudo docker compose up --build

# 3. Open the frontend
#    → http://localhost:3000
#
# 4. API is available at
#    → http://localhost:8000
#    → Interactive docs: http://localhost:8000/docs
```

To stop:
```bash
sudo docker compose down
```

To wipe data and restart fresh:
```bash
sudo docker compose down -v   # removes the telemetry_data volume
sudo docker compose up --build
```

---

## Running Locally (Without Docker)

### Prerequisites
- Python 3.12+
- `pip`

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

The SQLite database file is created automatically at `/app/data/telemetry.db` (Docker) or the path set by the `DB_PATH` environment variable.

To override locally:
```bash
DB_PATH=./telemetry.db uvicorn main:app --reload --port 8000
```

### MQTT Broker

You will need an MQTT broker (e.g., Mosquitto) for the device simulator. You can use the provided configuration:
```bash
mosquitto -c mosquitto/mosquitto.conf
```
*(Requires Mosquitto installed locally)*

### Frontend

The frontend is built with React and Vite.

```bash
cd frontend
npm install
npm run dev
```

> **Note**: The frontend connects to `ws://localhost:8000/ws/telemetry` for live data and expects an MQTT broker supporting WebSockets on `ws://localhost:9001`. Make sure the backend and broker are running.

---

## Database

SQLite is used for local development. The schema is initialised automatically on startup.

- **Schema reference**: [`backend/schema.sql`](backend/schema.sql)
- **Tables**:
  - `telemetry_readings` — all ingested readings (idempotency via `UNIQUE(device_id, timestamp)`)
  - `device_latest` — latest snapshot per device
  - `alerts` — alert event log

---

## API Reference

### `POST /telemetry` — Ingest a reading

```bash
curl -s -X POST http://localhost:8000/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "deviceId": "AC-1001",
    "timestamp": "2026-06-10T10:30:00Z",
    "temperature": 29.5,
    "energyConsumption": 4.8,
    "voltage": 230,
    "current": 6.2,
    "status": "online"
  }' | python3 -m json.tool
```

**Trigger alerts** (temperature > 35 °C):
```bash
curl -s -X POST http://localhost:8000/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "deviceId": "AC-1001",
    "timestamp": "2026-06-10T10:31:00Z",
    "temperature": 42.0,
    "energyConsumption": 4.8,
    "voltage": 230,
    "current": 6.2,
    "status": "online"
  }' | python3 -m json.tool
```

**Invalid payload** (missing required field):
```bash
curl -s -X POST http://localhost:8000/telemetry \
  -H "Content-Type: application/json" \
  -d '{"deviceId": "AC-1001", "temperature": 29.5}' | python3 -m json.tool
```

**Offline device** (triggers DEVICE_OFFLINE alert):
```bash
curl -s -X POST http://localhost:8000/telemetry \
  -H "Content-Type: application/json" \
  -d '{
    "deviceId": "AC-1002",
    "timestamp": "2026-06-10T10:32:00Z",
    "temperature": 28.0,
    "energyConsumption": 3.1,
    "voltage": 230,
    "current": 5.0,
    "status": "offline"
  }' | python3 -m json.tool
```

---

### `GET /devices/{deviceId}/latest` — Latest reading

```bash
curl -s http://localhost:8000/devices/AC-1001/latest | python3 -m json.tool
```

---

### `GET /alerts` — All alerts

```bash
curl -s http://localhost:8000/alerts | python3 -m json.tool
```

Filter by device:
```bash
curl -s "http://localhost:8000/alerts?deviceId=AC-1001&limit=10" | python3 -m json.tool
```

---

### `GET /devices/{deviceId}/summary` — Aggregate statistics

```bash
curl -s http://localhost:8000/devices/AC-1001/summary | python3 -m json.tool
```

---

### WebSocket — `ws://localhost:8000/ws/telemetry`

Connect with any WebSocket client. New telemetry events are pushed automatically.

Example message shape:
```json
{
  "event": "telemetry",
  "data": {
    "deviceId": "AC-1001",
    "timestamp": "2026-06-10T10:30:00Z",
    "temperature": 29.5,
    "energyConsumption": 4.8,
    "voltage": 230,
    "current": 6.2,
    "status": "online"
  },
  "alerts": [],
  "receivedAt": "2026-06-16T05:00:01.234567+00:00"
}
```

Quick test with `websocat`:
```bash
websocat ws://localhost:8000/ws/telemetry
```

---

## Alert Rules

| Alert Type | Condition |
|---|---|
| `HIGH_TEMPERATURE` | Temperature > 35 °C |
| `ENERGY_SPIKE` | Energy > 10 kWh |
| `DEVICE_OFFLINE` | Status is `offline` or `error` |
| `SUSPICIOUS_READING` | Voltage outside 180–270 V or Current > 20 A |

---

## Project Structure

```
iot_telemetry/
├── backend/
│   ├── main.py              # FastAPI app, all routes, WebSocket
│   ├── database.py          # SQLite init + CRUD helpers
│   ├── models.py            # Pydantic validation models
│   ├── alerts.py            # Pluggable alert rule engine
│   ├── schema.sql           # Schema reference (DDL)
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/                 # React source code (Dashboard & Simulator)
│   ├── package.json         # Dependencies (React, MQTT, etc.)
│   ├── vite.config.js       # Vite configuration
│   └── Dockerfile
├── mosquitto/
│   └── mosquitto.conf       # MQTT broker config with WebSockets
├── docs/
│   ├── HLD.md               # High-Level Design
│   ├── LLD.md               # Low-Level Design
│   └── TECHNICAL_DESIGN.md  # Technical Design + AI disclosure
├── docker-compose.yml
└── README.md
```

---

## Interactive API Docs

FastAPI auto-generates OpenAPI documentation:
- Swagger UI: **http://localhost:8000/docs**
- ReDoc: **http://localhost:8000/redoc**
