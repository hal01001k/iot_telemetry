import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError

import alerts as alert_engine
import database as db
from models import TelemetryPayload
from mqtt_subscriber import start_mqtt_subscriber

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("telemetry")


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------
class ConnectionManager:
    """Keeps track of all active WebSocket clients and broadcasts messages."""

    def __init__(self):
        self._clients: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.append(ws)
        logger.info("WS client connected — total: %d", len(self._clients))

    def disconnect(self, ws: WebSocket):
        self._clients.remove(ws)
        logger.info("WS client disconnected — total: %d", len(self._clients))

    async def broadcast(self, payload: dict[str, Any]):
        dead: list[WebSocket] = []
        for ws in list(self._clients):
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self._clients:
                self._clients.remove(ws)


manager = ConnectionManager()


# ---------------------------------------------------------------------------
# Core ingestion logic — shared by HTTP and MQTT paths
# ---------------------------------------------------------------------------
async def _process_telemetry(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Validate, store, alert, and broadcast a raw telemetry payload.
    Returns a result dict; raises HTTPException for HTTP callers.
    """
    try:
        payload = TelemetryPayload(**raw)
    except ValidationError as exc:
        errors = [{"field": e["loc"][-1], "error": e["msg"]} for e in exc.errors()]
        # Re-raise for HTTP; MQTT caller catches and logs
        raise ValidationError.from_exception_data(
            title="TelemetryPayload",
            input_type="python",
            line_errors=exc.errors(),
        ) from exc

    payload_dict = payload.model_dump()

    inserted = db.insert_reading(payload_dict)
    if not inserted:
        return {"status": "duplicate", "deviceId": payload.deviceId}

    db.upsert_latest(payload_dict)

    triggered = alert_engine.evaluate(payload_dict)
    stored_alerts = []
    for alert_type, message in triggered:
        db.insert_alert(
            device_id=payload.deviceId,
            alert_type=alert_type,
            message=message,
            reading_ts=payload.timestamp,
        )
        stored_alerts.append({"type": alert_type, "message": message})
        logger.warning("ALERT [%s] %s", alert_type, message)

    broadcast_payload = {
        "event": "telemetry",
        "data": payload_dict,
        "alerts": stored_alerts,
        "receivedAt": _now_iso(),
    }
    await manager.broadcast(broadcast_payload)

    logger.info(
        "Telemetry stored | device=%s ts=%s alerts=%d source=%s",
        payload.deviceId,
        payload.timestamp,
        len(stored_alerts),
        raw.get("_source", "http"),
    )

    return {
        "status": "ok",
        "deviceId": payload.deviceId,
        "timestamp": payload.timestamp,
        "alertsTriggered": len(stored_alerts),
        "alerts": stored_alerts,
    }


async def _mqtt_process(raw: dict[str, Any]):
    """Wrapper for MQTT path — swallows ValidationError and logs it."""
    raw["_source"] = "mqtt"
    try:
        await _process_telemetry(raw)
    except Exception as exc:
        logger.warning("MQTT ingestion skipped — %s", exc)


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    logger.info("Database initialised at %s", db.get_db_path())

    # Start MQTT subscriber as a background task
    mqtt_task = asyncio.create_task(
        start_mqtt_subscriber(_mqtt_process),
        name="mqtt-subscriber",
    )
    logger.info("MQTT subscriber task started")

    yield

    mqtt_task.cancel()
    try:
        await mqtt_task
    except asyncio.CancelledError:
        pass
    logger.info("MQTT subscriber task stopped")


app = FastAPI(
    title="IoT Telemetry API",
    description="Production-grade telemetry ingestion, alerting, and WebSocket broadcast.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/telemetry", status_code=201)
async def ingest_telemetry(request_body: dict[str, Any]):
    """
    Ingest a telemetry reading from an IoT device (HTTP path).

    - Validates all fields (type, range, required).
    - Rejects duplicates (same deviceId + timestamp) with 409.
    - Runs alert rules; stores any triggered alerts.
    - Broadcasts the reading + any new alerts over WebSocket.
    """
    try:
        payload = TelemetryPayload(**request_body)
    except ValidationError as exc:
        errors = [{"field": e["loc"][-1], "error": e["msg"]} for e in exc.errors()]
        raise HTTPException(status_code=422, detail={"validation_errors": errors})

    payload_dict = payload.model_dump()

    inserted = db.insert_reading(payload_dict)
    if not inserted:
        return JSONResponse(
            status_code=409,
            content={
                "status": "duplicate",
                "message": (
                    f"Reading for device '{payload.deviceId}' at "
                    f"'{payload.timestamp}' already exists."
                ),
            },
        )

    db.upsert_latest(payload_dict)

    triggered = alert_engine.evaluate(payload_dict)
    stored_alerts = []
    for alert_type, message in triggered:
        db.insert_alert(
            device_id=payload.deviceId,
            alert_type=alert_type,
            message=message,
            reading_ts=payload.timestamp,
        )
        stored_alerts.append({"type": alert_type, "message": message})
        logger.warning("ALERT [%s] %s", alert_type, message)

    broadcast_payload = {
        "event": "telemetry",
        "data": payload_dict,
        "alerts": stored_alerts,
        "receivedAt": _now_iso(),
    }
    await manager.broadcast(broadcast_payload)

    logger.info(
        "Telemetry stored | device=%s ts=%s alerts=%d source=http",
        payload.deviceId,
        payload.timestamp,
        len(stored_alerts),
    )

    return {
        "status": "ok",
        "deviceId": payload.deviceId,
        "timestamp": payload.timestamp,
        "alertsTriggered": len(stored_alerts),
        "alerts": stored_alerts,
    }


@app.get("/devices/{deviceId}/latest")
async def get_latest(deviceId: str):
    """Return the most recent telemetry reading for a device."""
    row = db.get_latest(deviceId)
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No readings found for device '{deviceId}'",
        )
    return {"status": "ok", "data": row}


@app.get("/alerts")
async def get_alerts(deviceId: str | None = None, limit: int = 100):
    """
    Return alert history. Optionally filter by deviceId.
    Query params: ?deviceId=AC-1001&limit=50
    """
    rows = db.get_alerts(device_id=deviceId, limit=limit)
    return {"status": "ok", "count": len(rows), "data": rows}


@app.get("/devices/{deviceId}/summary")
async def get_summary(deviceId: str):
    """Return aggregate statistics (min/max/avg) for a device."""
    row = db.get_summary(deviceId)
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"No readings found for device '{deviceId}'",
        )
    return {"status": "ok", "data": row}


@app.get("/health")
async def health():
    """Health check endpoint used by Docker healthcheck."""
    return {"status": "healthy"}


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/telemetry")
async def websocket_telemetry(ws: WebSocket):
    """
    WebSocket endpoint — ws://localhost:8000/ws/telemetry

    Clients receive a JSON push whenever POST /telemetry ingests a valid reading.
    Shape: { "event": "telemetry", "data": {...}, "alerts": [...], "receivedAt": "..." }
    """
    await manager.connect(ws)
    try:
        # Keep connection alive; we only push, never expect client messages.
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)
