"""
Alert rule engine.

Each rule is a function that receives the validated telemetry dict and
returns a list of (alert_type, message) tuples. An empty list means no alert.
"""

from typing import Any

TEMPERATURE_THRESHOLD = 35.0      # °C
ENERGY_SPIKE_THRESHOLD = 10.0     # kWh
VOLTAGE_MIN = 180.0               # V
VOLTAGE_MAX = 270.0               # V
CURRENT_MAX = 20.0                # A


def _check_temperature(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Rule 1: Temperature above threshold."""
    temp = payload["temperature"]
    if temp > TEMPERATURE_THRESHOLD:
        return [(
            "HIGH_TEMPERATURE",
            f"Temperature {temp}°C exceeds threshold of {TEMPERATURE_THRESHOLD}°C "
            f"for device {payload['deviceId']}",
        )]
    return []


def _check_energy_spike(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Rule 2: Abnormal energy consumption spike."""
    energy = payload["energyConsumption"]
    if energy > ENERGY_SPIKE_THRESHOLD:
        return [(
            "ENERGY_SPIKE",
            f"Energy consumption {energy} kWh exceeds spike threshold of "
            f"{ENERGY_SPIKE_THRESHOLD} kWh for device {payload['deviceId']}",
        )]
    return []


def _check_device_status(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Rule 3: Device offline or in error state."""
    status = payload["status"]
    if status != "online":
        return [(
            "DEVICE_OFFLINE",
            f"Device {payload['deviceId']} reported status '{status}'",
        )]
    return []


def _check_suspicious_readings(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """Rule 4: Voltage or current outside expected safe range."""
    results = []
    voltage = payload["voltage"]
    current = payload["current"]

    if not (VOLTAGE_MIN <= voltage <= VOLTAGE_MAX):
        results.append((
            "SUSPICIOUS_READING",
            f"Voltage {voltage}V is outside safe range "
            f"[{VOLTAGE_MIN}–{VOLTAGE_MAX}V] for device {payload['deviceId']}",
        ))

    if current > CURRENT_MAX:
        results.append((
            "SUSPICIOUS_READING",
            f"Current {current}A exceeds maximum safe limit of "
            f"{CURRENT_MAX}A for device {payload['deviceId']}",
        ))

    return results


_RULES = [
    _check_temperature,
    _check_energy_spike,
    _check_device_status,
    _check_suspicious_readings,
]


def evaluate(payload: dict[str, Any]) -> list[tuple[str, str]]:
    """
    Run all alert rules against the payload.
    Returns a flat list of (alert_type, message) tuples for every rule that fired.
    """
    results: list[tuple[str, str]] = []
    for rule in _RULES:
        results.extend(rule(payload))
    return results
