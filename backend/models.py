from pydantic import BaseModel, field_validator, model_validator
from typing import Literal
from datetime import datetime


class TelemetryPayload(BaseModel):
    deviceId: str
    timestamp: str
    temperature: float
    energyConsumption: float
    voltage: float
    current: float
    status: Literal["online", "offline", "error"]

    @field_validator("deviceId")
    @classmethod
    def device_id_not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("deviceId must not be empty")
        return v.strip()

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, v: str) -> str:
        try:
            datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("timestamp must be a valid ISO 8601 datetime string")
        return v

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, v: float) -> float:
        if not (-50 <= v <= 100):
            raise ValueError("temperature must be between -50 and 100 °C")
        return v

    @field_validator("energyConsumption")
    @classmethod
    def validate_energy(cls, v: float) -> float:
        if v < 0:
            raise ValueError("energyConsumption must be >= 0")
        return v

    @field_validator("voltage")
    @classmethod
    def validate_voltage(cls, v: float) -> float:
        if not (0 <= v <= 500):
            raise ValueError("voltage must be between 0 and 500 V")
        return v

    @field_validator("current")
    @classmethod
    def validate_current(cls, v: float) -> float:
        if v < 0:
            raise ValueError("current must be >= 0")
        return v
