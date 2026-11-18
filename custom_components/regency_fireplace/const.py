"""Constants for the Regency Fireplace integration."""

from datetime import timedelta
from typing import Final

DOMAIN: Final = "regency_fireplace"

CONF_TRANSMITTER: Final = "transmitter"
CONF_FIRE_ID: Final = "fire_id"
CONF_TEMPERATURE_SOURCE: Final = "temperature_source"

# The handset re-broadcasts its state (and room temperature) on a ~52 s tick.
# While heating, do the same so the fire's thermostat never runs on a stale value.
REFRESH_INTERVAL: Final = timedelta(seconds=52)
# Coalesce rapid temperature-source updates into one refresh.
TEMPERATURE_DEBOUNCE: Final = 5.0

STORAGE_VERSION: Final = 1
