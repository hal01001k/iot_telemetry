"""
MQTT subscriber for IoT telemetry ingestion.

Devices publish readings to:  devices/{deviceId}/telemetry

The subscriber runs as a background asyncio task within the FastAPI process.
It validates, stores, and triggers the same pipeline as POST /telemetry.
"""

import asyncio
import json
import logging
import os
from typing import Callable

import aiomqtt

logger = logging.getLogger("mqtt")

MQTT_HOST  = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT  = int(os.environ.get("MQTT_PORT", "1883"))
TOPIC_PATTERN = "devices/+/telemetry"


async def start_mqtt_subscriber(process_fn: Callable[[dict], None]):
    """
    Connect to the MQTT broker and subscribe to device telemetry topics.
    Reconnects automatically on connection loss.

    :param process_fn: async coroutine that accepts a raw payload dict.
                       It should perform the same logic as POST /telemetry.
    """
    reconnect_interval = 5  # seconds

    while True:
        try:
            logger.info(
                "Connecting to MQTT broker at %s:%d …", MQTT_HOST, MQTT_PORT
            )
            async with aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT) as client:
                logger.info(
                    "MQTT connected — subscribing to '%s'", TOPIC_PATTERN
                )
                await client.subscribe(TOPIC_PATTERN, qos=1)

                async for message in client.messages:
                    topic = str(message.topic)
                    try:
                        raw = json.loads(message.payload.decode("utf-8"))
                        logger.info("MQTT message received on %s", topic)
                        await process_fn(raw)
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            "MQTT [%s] invalid JSON — %s", topic, exc
                        )
                    except Exception as exc:
                        logger.exception(
                            "MQTT [%s] processing error — %s", topic, exc
                        )

        except aiomqtt.MqttError as exc:
            logger.warning(
                "MQTT connection lost (%s). Reconnecting in %ds …",
                exc,
                reconnect_interval,
            )
            await asyncio.sleep(reconnect_interval)
        except asyncio.CancelledError:
            logger.info("MQTT subscriber task cancelled — shutting down.")
            break
        except Exception as exc:
            logger.exception(
                "Unexpected MQTT error: %s. Reconnecting in %ds …",
                exc,
                reconnect_interval,
            )
            await asyncio.sleep(reconnect_interval)
